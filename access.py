#!/usr/bin/env python3
"""Доступ к таблице access_codes (живёт в Postgres mlbot). Только чтение.

Коды генерит mlbot (кнопка «Получить код доступа»), сайт лишь валидирует их и по
user_id строит персональный watermark. Подключение — по ACCESS_DB_URL (public-URL
боевой БД mlbot). Если env не задан — модуль выключен, сайт работает по старому
Basic Auth (безопасный rollout)."""
from __future__ import annotations

import os

import psycopg
from psycopg.rows import dict_row

ACCESS_DB_URL = os.environ.get("ACCESS_DB_URL", "")


def enabled() -> bool:
    return bool(ACCESS_DB_URL)


def _conn():
    return psycopg.connect(ACCESS_DB_URL, row_factory=dict_row, autocommit=True)


def lookup_by_code(code: str):
    """{'user_id', 'nick'} по коду или None. Код нормализуем (upper, без пробелов)."""
    code = (code or "").strip().upper()
    if not code or not enabled():
        return None
    try:
        with _conn() as conn:
            return conn.execute(
                "SELECT user_id, nick FROM access_codes WHERE code = %s", (code,)
            ).fetchone()
    except Exception as e:  # noqa: BLE001 — БД недоступна не должна ронять сайт
        # Без str(e): текст исключения psycopg может содержать строку подключения.
        print("access.lookup_by_code failed:", type(e).__name__, flush=True)
        return None


def lookup_nick(user_id: int):
    """Ник по user_id (для декодера watermark). None если нет/выключено."""
    if not enabled():
        return None
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT nick FROM access_codes WHERE user_id = %s", (user_id,)
            ).fetchone()
            return row["nick"] if row else None
    except Exception as e:  # noqa: BLE001
        print("access.lookup_nick failed:", type(e).__name__, flush=True)
        return None
