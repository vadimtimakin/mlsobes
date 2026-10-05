#!/usr/bin/env python3
"""Лёгкий сервер для сайта «ML Clan — Собесы».

Отдаёт собранную статику из `site/` за HTTP Basic Auth. Логин/пароль берутся
из переменных окружения SITE_USER / SITE_PASS (задаются на Railway). Порт — из
$PORT (Railway прокидывает автоматически), локально по умолчанию 8000.

Перед запуском, если `site/` отсутствует, собирает сайт (`build.py`).
"""
import hmac
import os
import subprocess
import sys
from pathlib import Path

from flask import Flask, Response, request, send_from_directory

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"

USER = os.environ.get("SITE_USER", "mlclan")
PASSWORD = os.environ.get("SITE_PASS", "mlclan")

app = Flask(__name__, static_folder=None)


def _check(username: str, password: str) -> bool:
    # постоянное по времени сравнение, чтобы не течь по таймингам
    return (hmac.compare_digest(username, USER)
            and hmac.compare_digest(password, PASSWORD))


@app.before_request
def require_auth():
    if request.path == "/healthz":
        return None
    auth = request.authorization
    if auth and _check(auth.username or "", auth.password or ""):
        return None
    # realm должен быть latin-1 (HTTP-заголовки) — кириллицу сюда нельзя
    return Response(
        "Требуется авторизация", 401,
        {"WWW-Authenticate": 'Basic realm="ML Clan Sobesy"'},
    )


@app.route("/")
def index():
    return send_from_directory(SITE, "index.html")


@app.route("/<path:path>")
def static_files(path):
    target = SITE / path
    if target.is_dir():
        path = path.rstrip("/") + "/index.html"
    if not (SITE / path).exists():
        # SPA-подобный фолбэк не нужен — отдаём 404 через Flask
        return Response("Не найдено", 404)
    return send_from_directory(SITE, path)


@app.route("/healthz")
def healthz():
    return "ok"


def ensure_built():
    if not (SITE / "index.html").exists():
        print("site/ не найден — собираю…", flush=True)
        subprocess.run([sys.executable, str(ROOT / "build.py")], check=True)


if __name__ == "__main__":
    ensure_built()
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
