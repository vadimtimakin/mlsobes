#!/usr/bin/env python3
"""Сервер сайта «ML Clan — Собесы».

Отдаёт статику из `site/` за HTTP Basic Auth (SITE_PASS; логин любой) и добавляет
динамический слой загрузок собесов:
  - /upload          форма загрузки (текст/аудио/видео + метаданные)
  - /api/upload      POST: запускает фоновую обработку, возвращает job_id
  - /api/job/<id>    статус обработки
  - /u/<id>          страница загруженного собеса
  - /api/catalog     компании/секторы для автозаполнения
  - /api/uploads     список загрузок (для сайдбара)
  - /admin           откат (список + удаление), пароль ADMIN_PASS
Навигатор и поиск отдаются динамически = пребилд ⊕ загрузки из БД.
"""
import hmac
import json
import os
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, request, send_from_directory, jsonify

import db
import ingest
from build import make_md, page_html

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
UPLOAD_TMP = ROOT / "upload_tmp"

USER = os.environ.get("SITE_USER", "")
PASSWORD = os.environ.get("SITE_PASS", "mlclan")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # до 1 ГБ (видео)

_base_nav = None     # пребилд navigator-data
_base_search = None  # пребилд search-index
_cache = {"nav": (0.0, None), "search": (0.0, None)}  # TTL-кэш merged
CACHE_TTL = 15


# --- авторизация ------------------------------------------------------------
def _check(username: str, password: str, required: str) -> bool:
    if USER and required == PASSWORD and not hmac.compare_digest(username, USER):
        return False
    return bool(required) and hmac.compare_digest(password, required)


@app.before_request
def require_auth():
    if request.path == "/healthz":
        return None
    is_admin = request.path.startswith("/admin")
    required = ADMIN_PASS if is_admin else PASSWORD
    realm = "ML Clan Admin" if is_admin else "ML Clan Sobesy"
    if is_admin and not ADMIN_PASS:
        return Response("Админка не настроена (нет ADMIN_PASS)", 503)
    auth = request.authorization
    if auth and _check(auth.username or "", auth.password or "", required):
        return None
    return Response("Требуется авторизация", 401,
                    {"WWW-Authenticate": f'Basic realm="{realm}"'})


# --- пребилд + merge --------------------------------------------------------
def _load_base():
    global _base_nav, _base_search
    try:
        _base_nav = json.loads((SITE / "assets" / "navigator-data.json").read_text("utf-8"))
    except Exception:
        _base_nav = {"catalog": {"sectors": [], "companies": [], "pools": [], "domains": []},
                     "interviews": [], "questions": []}
    try:
        _base_search = json.loads((SITE / "assets" / "search-index.json").read_text("utf-8"))
    except Exception:
        _base_search = []


def merged_nav():
    now = time.time()
    ts, val = _cache["nav"]
    if val is not None and now - ts < CACHE_TTL:
        return val
    data = json.loads(json.dumps(_base_nav))  # deep copy
    if db.enabled():
        sector_label = {s["id"]: s["label"] for s in data["catalog"]["sectors"]}
        comps, intvs, qs = db.navigator_additions(sector_label)
        have = {c["id"] for c in data["catalog"]["companies"]}
        data["catalog"]["companies"] += [c for c in comps if c["id"] not in have]
        data["interviews"] += intvs
        data["questions"] += qs
    out = json.dumps(data, ensure_ascii=False)
    _cache["nav"] = (now, out)
    return out


def merged_search():
    now = time.time()
    ts, val = _cache["search"]
    if val is not None and now - ts < CACHE_TTL:
        return val
    items = list(_base_search)
    if db.enabled():
        for up in db.list_uploads():
            items.append({
                "title": _upload_title(up),
                "url": f"u/{up['id']}",
                "folder": "🆕 Загруженные собесы",
                "text": (up.get("comment") or "") + " " + (up.get("note_md") or "")[:3000],
            })
    out = json.dumps(items, ensure_ascii=False)
    _cache["search"] = (now, out)
    return out


def _invalidate():
    _cache["nav"] = (0.0, None)
    _cache["search"] = (0.0, None)


def _upload_title(up) -> str:
    d = up.get("interview_date")
    d = d.isoformat() if hasattr(d, "isoformat") else (d or "")
    return f"{up['company_name']}" + (f" — {d}" if d else "")


# --- дин. навигатор/поиск (перекрывают статику) -----------------------------
@app.route("/assets/navigator-data.json")
def nav_data():
    return Response(merged_nav(), mimetype="application/json")


@app.route("/assets/search-index.json")
def search_data():
    return Response(merged_search(), mimetype="application/json")


# --- каталог + список загрузок ----------------------------------------------
@app.route("/api/catalog")
def api_catalog():
    cat = ingest.load_catalog()
    companies = sorted(
        ({"name": c.get("name"), "sector": c.get("sector")} for c in cat["companies"]),
        key=lambda x: (x["name"] or "").lower())
    return jsonify({"sectors": cat["sectors"], "companies": companies})


@app.route("/api/uploads")
def api_uploads():
    if not db.enabled():
        return jsonify([])
    return jsonify([{"id": up["id"], "title": _upload_title(up)} for up in db.list_uploads()])


# --- загрузка ---------------------------------------------------------------
@app.route("/upload")
def upload_page():
    return send_from_directory(ROOT / "web", "upload.html")


@app.route("/api/upload", methods=["POST"])
def api_upload():
    if not db.enabled():
        return jsonify({"error": "База данных не настроена (нет DATABASE_URL)"}), 503
    company = (request.form.get("company") or "").strip()
    sector = (request.form.get("sector") or "other").strip()
    department = (request.form.get("department") or "").strip()
    date = (request.form.get("date") or "").strip()
    comment = (request.form.get("comment") or "").strip()
    pasted = (request.form.get("text") or "").strip()
    if not company:
        return jsonify({"error": "Укажите компанию"}), 400

    src_path = None
    file = request.files.get("file")
    if file and file.filename:
        ext = Path(file.filename).suffix.lower()
        if ext not in (ingest.AUDIO_EXT | ingest.VIDEO_EXT):
            return jsonify({"error": f"Неподдерживаемый формат: {ext}"}), 400
        UPLOAD_TMP.mkdir(exist_ok=True)
        src_path = str(UPLOAD_TMP / f"{uuid.uuid4().hex}{ext}")
        file.save(src_path)
    elif not pasted:
        return jsonify({"error": "Приложите файл или вставьте текст"}), 400

    job_id = uuid.uuid4().hex
    contributor = request.remote_addr or ""  # берём ДО потока: request жив только в запросе
    db.create_job(job_id)

    def run():
        try:
            ingest.process(job_id, src_path=src_path, pasted_text=pasted, company=company,
                           sector=sector, department=department, interview_date=date,
                           comment=comment, contributor=contributor)
        except Exception as e:  # noqa: BLE001 — иначе джоба молча зависнет в queued
            try:
                db.update_job(job_id, status="error", message=f"{type(e).__name__}: {e}")
            except Exception:
                pass
        finally:
            _invalidate()

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"job_id": job_id})


@app.route("/api/job/<job_id>")
def api_job(job_id):
    job = db.get_job(job_id) if db.enabled() else None
    if not job:
        return jsonify({"error": "not found"}), 404
    return jsonify({"status": job["status"], "stage": job.get("stage"),
                    "message": job.get("message"), "upload_id": job.get("upload_id")})


# --- страница загруженного собеса -------------------------------------------
@app.route("/u/<int:upload_id>")
def uploaded_note(upload_id):
    if not db.enabled():
        return Response("Не найдено", 404)
    up = db.get_upload(upload_id)
    if not up or up["status"] != "live":
        return Response("Не найдено", 404)
    content = make_md().convert(up["note_md"])
    sidebar = _sidebar_from_site()
    html = page_html(_upload_title(up), sidebar, content)
    return Response(html, mimetype="text/html")


def _sidebar_from_site():
    """Берём сайдбар из любой статической страницы, чтобы навигация совпадала."""
    try:
        import re
        t = (SITE / "index.html").read_text("utf-8")
        m = re.search(r'<nav class="sidebar-nav">.*?</nav>', t, re.DOTALL)
        return m.group(0) if m else ""
    except Exception:
        return ""


# --- админка (откат) --------------------------------------------------------
@app.route("/admin")
def admin():
    ups = db.list_uploads(include_hidden=True) if db.enabled() else []
    rows = []
    for up in ups:
        nq = len(db.get_upload(up["id"])["questions"])
        rows.append(
            f'<tr><td>{up["id"]}</td><td>{_h(_upload_title(up))}</td>'
            f'<td>{_h(up["sector"])}</td><td>{nq}</td>'
            f'<td>{up["created_at"]:%Y-%m-%d %H:%M}</td>'
            f'<td><a href="/u/{up["id"]}" target="_blank">открыть</a></td>'
            f'<td><form method="post" action="/admin/delete/{up["id"]}" '
            f'onsubmit="return confirm(\'Удалить запись #{up["id"]}?\')">'
            f'<button>удалить</button></form></td></tr>')
    body = (f"<h1>Загрузки собесов ({len(ups)})</h1>"
            "<table border=1 cellpadding=6 style='border-collapse:collapse'>"
            "<tr><th>#</th><th>Собес</th><th>Сектор</th><th>Вопросов</th>"
            "<th>Загружен</th><th></th><th></th></tr>" + "".join(rows) + "</table>")
    return Response(f"<!doctype html><meta charset=utf-8><title>Админка</title>"
                    f"<body style='font-family:sans-serif;max-width:1000px;margin:30px auto'>"
                    f"{body}</body>", mimetype="text/html")


@app.route("/admin/delete/<int:upload_id>", methods=["POST"])
def admin_delete(upload_id):
    db.delete_upload(upload_id)
    _invalidate()
    return Response("", 303, {"Location": "/admin"})


def _h(s):
    import html
    return html.escape(str(s))


# --- статика ----------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(SITE, "index.html")


@app.route("/<path:path>")
def static_files(path):
    if not (SITE / path).exists():
        return Response("Не найдено", 404)
    return send_from_directory(SITE, path)


@app.route("/healthz")
def healthz():
    return "ok"


def ensure_built():
    if not (SITE / "index.html").exists():
        import subprocess, sys
        print("site/ не найден — собираю…", flush=True)
        subprocess.run([sys.executable, str(ROOT / "build.py")], check=True)


def bootstrap():
    ensure_built()
    _load_base()
    try:
        db.init_schema()
    except Exception as e:
        print("init_schema failed:", e, flush=True)


bootstrap()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, threaded=True)
