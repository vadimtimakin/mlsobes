#!/usr/bin/env python3
"""Доступ к Postgres (загрузки собесов). Короткие соединения на операцию —
трафик низкий, пул не нужен. DATABASE_URL задаётся Railway."""
from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parent
DATABASE_URL = os.environ.get("DATABASE_URL", "")

# смещение id, чтобы не пересекаться с telegram-id (<100k) в пребилде навигатора
INTERVIEW_ID_BASE = 2_000_000_000


def enabled() -> bool:
    return bool(DATABASE_URL)


def _conn():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, autocommit=True)


def init_schema() -> None:
    if not enabled():
        return
    sql = (ROOT / "schema.sql").read_text(encoding="utf-8")
    # psycopg3 (расширенный протокол) не выполняет несколько команд за раз —
    # разбиваем скрипт по ';' и прогоняем по одной
    with _conn() as conn:
        for stmt in (s.strip() for s in sql.split(";")):
            if stmt:
                conn.execute(stmt)


# --- джобы ------------------------------------------------------------------
def create_job(job_id: str) -> None:
    with _conn() as conn:
        conn.execute("INSERT INTO jobs (id, status, stage) VALUES (%s,'queued','В очереди')",
                     (job_id,))


def update_job(job_id: str, *, status=None, stage=None, message=None, upload_id=None) -> None:
    sets, vals = ["updated_at = now()"], []
    for col, val in (("status", status), ("stage", stage),
                     ("message", message), ("upload_id", upload_id)):
        if val is not None:
            sets.append(f"{col} = %s")
            vals.append(val)
    vals.append(job_id)
    with _conn() as conn:
        conn.execute(f"UPDATE jobs SET {', '.join(sets)} WHERE id = %s", vals)


def get_job(job_id: str):
    with _conn() as conn:
        cur = conn.execute("SELECT * FROM jobs WHERE id = %s", (job_id,))
        return cur.fetchone()


# --- загрузки ---------------------------------------------------------------
def insert_upload(*, company_id, company_name, sector, department, interview_date,
                  comment, community_link, note_md, contributor, questions) -> int:
    """questions: список dict {text, pool_ids, domains}. Возвращает id загрузки."""
    with _conn() as conn:
        with conn.transaction():
            cur = conn.execute(
                """INSERT INTO uploads
                   (company_id, company_name, sector, department, interview_date,
                    comment, community_link, note_md, contributor)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (company_id, company_name, sector, department, interview_date or None,
                 comment, community_link or None, note_md, contributor))
            upload_id = cur.fetchone()["id"]
            for ord_, q in enumerate(questions):
                conn.execute(
                    """INSERT INTO upload_questions (upload_id, ord, text, pool_ids, domains)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (upload_id, ord_, q["text"],
                     json.dumps(q.get("pool_ids", []), ensure_ascii=False),
                     json.dumps(q.get("domains", []), ensure_ascii=False)))
    return upload_id


def list_uploads(include_hidden=False):
    q = "SELECT * FROM uploads"
    if not include_hidden:
        q += " WHERE status = 'live'"
    q += " ORDER BY created_at DESC"
    with _conn() as conn:
        return conn.execute(q).fetchall()


def get_upload(upload_id: int):
    with _conn() as conn:
        up = conn.execute("SELECT * FROM uploads WHERE id = %s", (upload_id,)).fetchone()
        if not up:
            return None
        qs = conn.execute(
            "SELECT * FROM upload_questions WHERE upload_id = %s ORDER BY ord",
            (upload_id,)).fetchall()
        up["questions"] = qs
        return up


def delete_upload(upload_id: int) -> None:
    with _conn() as conn:
        conn.execute("DELETE FROM uploads WHERE id = %s", (upload_id,))


# --- данные для навигатора (merge с пребилдом) ------------------------------
def navigator_additions(sector_label: dict):
    """Возвращает (companies, interviews, questions) в формате navigator-data
    для всех live-загрузок."""
    companies, interviews, questions = {}, [], []
    with _conn() as conn:
        ups = conn.execute("SELECT * FROM uploads WHERE status = 'live'").fetchall()
        for up in ups:
            iid = INTERVIEW_ID_BASE + up["id"]
            companies.setdefault(up["company_id"], {
                "id": up["company_id"], "name": up["company_name"], "sector": up["sector"],
            })
            interviews.append({
                "id": iid, "source_ids": [iid],
                "company": up["company_name"], "company_id": up["company_id"],
                "sector": up["sector"], "sector_label": sector_label.get(up["sector"], ""),
                "department": up["department"], "stage": None,
                "date": up["interview_date"].isoformat() if up["interview_date"] else "",
                "source_kind": "interview", "metadata_method": "upload",
            })
            qs = conn.execute(
                "SELECT * FROM upload_questions WHERE upload_id = %s ORDER BY ord",
                (up["id"],)).fetchall()
            for q in qs:
                questions.append({
                    "id": f"uq_{up['id']}_{q['ord']}",
                    "text": q["text"],
                    "pool_ids": q["pool_ids"] or [],
                    "domains": q["domains"] or [],
                    "evidence": [{"source_id": iid, "interview_id": iid}],
                })
    return list(companies.values()), interviews, questions
