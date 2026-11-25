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
import re
import threading
import time
import uuid
from collections import deque
from datetime import timedelta
from pathlib import Path

from flask import (
    Flask, Response, request, send_from_directory, jsonify,
    session, redirect,
)

import access
import db
import ingest
import navswap
import watermark
from build import make_md, page_html

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
UPLOAD_TMP = ROOT / "upload_tmp"

USER = os.environ.get("SITE_USER", "")
PASSWORD = os.environ.get("SITE_PASS", "mlclan")
ADMIN_PASS = os.environ.get("ADMIN_PASS", "")
# Секрет для подписи куки-сессии. Задаётся вместе с ACCESS_DB_URL при включении код-логина.
SESSION_SECRET = os.environ.get("SESSION_SECRET", "")

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 1024 * 1024 * 1024  # до 1 ГБ (видео)
app.secret_key = SESSION_SECRET or "dev-insecure-" + uuid.uuid4().hex
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=180)  # «ввёл код один раз»
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


def _code_login_enabled() -> bool:
    """Код-логин включён, когда задана БД кодов И секрет сессии. Иначе — старый Basic Auth."""
    return access.enabled() and bool(SESSION_SECRET)

# --- антивыкачка ------------------------------------------------------------
RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))  # запросов/мин на IP
RATE_WINDOW = 60
_SCRAPER_UA = re.compile(
    r"(?i)(curl|wget|python-requests|urllib|scrapy|httpx|aiohttp|go-http-client|"
    r"java/|libwww|okhttp|node-fetch|axios|httrack|mechanize|phantomjs|"
    r"headlesschrome|puppeteer|playwright|\bbot\b|spider|crawler|scrape)")
# объёмные JSON отдают весь корпус за один запрос — только из нашего фронта
BULK_JSON = {"/assets/navigator-data.json", "/assets/search-index.json"}
_hits: dict[str, deque] = {}
_hits_lock = threading.Lock()


def _client_ip() -> str:
    xff = request.headers.get("X-Forwarded-For", "")  # за прокси Railway
    return xff.split(",")[0].strip() if xff else (request.remote_addr or "?")


def _same_origin() -> bool:
    sfs = request.headers.get("Sec-Fetch-Site")
    if sfs is not None:  # современные браузеры всегда шлют
        return sfs in ("same-origin", "same-site", "none")
    ref = request.headers.get("Referer", "")
    return bool(request.host) and request.host in ref

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
def anti_scrape():
    """Защита от массовой выкачки: блок скрипт-UA, гейт объёмных JSON, rate-limit."""
    if request.path == "/healthz":
        return None
    ua = request.headers.get("User-Agent", "")
    if not ua or _SCRAPER_UA.search(ua):
        return Response("Доступ запрещён", 403)
    if request.path in BULK_JSON and not _same_origin():
        return Response("Доступ запрещён", 403)
    ip = _client_ip()
    now = time.time()
    with _hits_lock:
        dq = _hits.get(ip)
        if dq is None:
            dq = _hits[ip] = deque()
        while dq and now - dq[0] > RATE_WINDOW:
            dq.popleft()
        if len(dq) >= RATE_LIMIT:
            retry = int(RATE_WINDOW - (now - dq[0])) + 1
            return Response("Слишком много запросов, подождите",
                            429, {"Retry-After": str(retry)})
        dq.append(now)
        if len(_hits) > 5000:  # лёгкая уборка памяти
            for k in [k for k, v in _hits.items() if not v]:
                _hits.pop(k, None)
    return None


def _admin_auth_or_challenge():
    """Админка — всегда по Basic Auth (ADMIN_PASS), независимо от код-логина."""
    if not ADMIN_PASS:
        return Response("Админка не настроена (нет ADMIN_PASS)", 503)
    auth = request.authorization
    if auth and _check(auth.username or "", auth.password or "", ADMIN_PASS):
        return None
    return Response("Требуется авторизация", 401,
                    {"WWW-Authenticate": 'Basic realm="ML Clan Admin"'})


@app.before_request
def require_auth():
    if request.path == "/healthz":
        return None
    is_admin = request.path.startswith("/admin")
    if is_admin:
        return _admin_auth_or_challenge()

    # Новый режим: персональный код + сессия (когда задан ACCESS_DB_URL + SESSION_SECRET).
    if _code_login_enabled():
        if request.path in ("/login", "/logout"):
            return None
        if session.get("uid"):
            return None
        return redirect("/login")

    # Старый режим: общий пароль по Basic Auth.
    auth = request.authorization
    if auth and _check(auth.username or "", auth.password or "", PASSWORD):
        return None
    return Response("Требуется авторизация", 401,
                    {"WWW-Authenticate": 'Basic realm="ML Clan Sobesy"'})


# --- код-логин (персональный код из бота) -----------------------------------
_LOGIN_HTML = """<!doctype html><html lang=ru><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>ML Clan — Собесы</title>
<style>
body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#0f1115;color:#e6e6e6;
display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}}
.card{{background:#191c22;padding:32px 28px;border-radius:14px;max-width:360px;width:90%;
box-shadow:0 10px 40px rgba(0,0,0,.4)}}
h1{{font-size:19px;margin:0 0 6px}} p{{color:#9aa0aa;font-size:14px;margin:0 0 18px;line-height:1.5}}
input{{width:100%;box-sizing:border-box;padding:12px 14px;font-size:16px;letter-spacing:2px;
text-align:center;text-transform:uppercase;background:#0f1115;border:1px solid #333;border-radius:9px;
color:#fff;margin-bottom:12px}}
button{{width:100%;padding:12px;font-size:15px;background:#3b82f6;color:#fff;border:0;border-radius:9px;
cursor:pointer}} button:hover{{background:#2f6fe0}}
.err{{color:#f87171;font-size:13px;margin-bottom:10px}}
</style></head><body><form class=card method=post action=/login>
<h1>🔑 Вход по персональному коду</h1>
<p>Открой бота ML Clan → «Получить код доступа» и введи код сюда. Один раз — дальше
браузер запомнит.</p>
{err}<input name=code placeholder="КОД" autofocus autocomplete=off maxlength=32>
<button type=submit>Войти</button></form></body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    if not _code_login_enabled():
        return redirect("/")
    if session.get("uid") and request.method == "GET":
        return redirect("/")
    err = ""
    if request.method == "POST":
        rec = access.lookup_by_code(request.form.get("code", ""))
        if rec:
            session.permanent = True
            session["uid"] = int(rec["user_id"])
            session["nick"] = rec.get("nick") or ""
            return redirect("/")
        err = '<div class=err>Код не найден. Проверь его в боте и попробуй ещё раз.</div>'
    return Response(_LOGIN_HTML.format(err=err), mimetype="text/html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# --- homoglyph-watermark: все text/html для залогиненного юзера --------------
@app.after_request
def _apply_watermark(resp: Response):
    try:
        uid = session.get("uid")
        if (uid and resp.status_code == 200 and resp.mimetype == "text/html"
                and not request.path.startswith("/admin")
                and request.path not in ("/login", "/logout")):
            resp.direct_passthrough = False  # статика (send_from_directory) идёт в passthrough
            body = resp.get_data(as_text=True)
            resp.set_data(watermark.embed(body, int(uid)))
    except Exception as e:  # noqa: BLE001 — watermark не должен ломать отдачу
        print("watermark apply failed:", e, flush=True)
    return resp


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
    raw = merged_nav()
    uid = session.get("uid") if _code_login_enabled() else None
    if uid:
        nav = navswap.permute(json.loads(raw), int(uid))
        return Response(json.dumps(nav, ensure_ascii=False), mimetype="application/json")
    return Response(raw, mimetype="application/json")


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
    community_link = (request.form.get("community_link") or "").strip()
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
                           comment=comment, community_link=community_link,
                           contributor=contributor)
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
            "<p><a href='/admin/decode'>🔎 Декодер watermark</a> — узнать по утёкшему тексту, чей экземпляр.</p>"
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


@app.route("/admin/decode", methods=["GET", "POST"])
def admin_decode():
    """Вставить утёкший текст/HTML → вычислить, чей это экземпляр (homoglyph-watermark)."""
    result = ""
    if request.method == "POST":
        sample = request.form.get("sample", "")
        uid, how = None, ""
        # Если вставили navigator-data.json — декодим перестановкой вопросов.
        try:
            parsed = json.loads(sample)
            if isinstance(parsed, dict) and parsed.get("questions"):
                uid = navswap.decode(parsed, json.loads(merged_nav()))
                how = " (по перестановке вопросов навигатора)"
        except (ValueError, TypeError):
            pass
        if uid is None:  # иначе — homoglyph по тексту/HTML
            uid = watermark.decode_user_id(sample)
            how = " (по homoglyph-метке текста)" if uid is not None else ""
        if uid is None:
            result = "<p style='color:#b00'>Сигнал не найден (возможно, текст перенабран или прогнан через LLM).</p>"
        else:
            nick = access.lookup_nick(uid) or "—"
            result = (f"<p style='color:#060'><b>Найдено{how}:</b> user_id <code>{uid}</code>, "
                      f"ник <b>{_h(nick)}</b></p>")
    return Response(
        "<!doctype html><meta charset=utf-8><title>Декодер watermark</title>"
        "<body style='font-family:sans-serif;max-width:800px;margin:30px auto'>"
        "<h1>🔎 Декодер watermark</h1>"
        "<p>Вставь утёкший текст или HTML-исходник страницы — покажу, чей это экземпляр.</p>"
        f"{result}"
        "<form method=post><textarea name=sample rows=14 style='width:100%' "
        "placeholder='Вставь сюда утёкший текст…'></textarea><br>"
        "<button style='margin-top:10px;padding:8px 16px'>Определить</button></form>"
        "<p><a href='/admin'>← к загрузкам</a></p></body>",
        mimetype="text/html")


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
