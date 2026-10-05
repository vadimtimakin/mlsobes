#!/usr/bin/env python3
"""Пайплайн обработки загруженного собеса:
  медиа -> ffmpeg(аудио) -> нарезка -> gpt-4o-transcribe -> склейка
  текст -> LLM извлекает нормализованные вопросы + теги
  -> матч компании/сектора по каталогу -> запись в БД.
Сырьё (аудио/транскрипт) не сохраняем — после обработки удаляем.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unicodedata
from pathlib import Path

import db
from build import make_md, slugify  # переиспользуем рендер и slug

ROOT = Path(__file__).resolve().parent
VAULT = ROOT / "Собесы"

OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o")
TRANSCRIBE_MODEL = os.environ.get("OPENAI_TRANSCRIBE_MODEL", "gpt-4o-transcribe")
SEGMENT_SECONDS = 1200  # 20 минут на кусок (<<25МБ при 16k mono 32k mp3)

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma"}
VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _client():
    from openai import OpenAI
    return OpenAI()


# --- каталог (компании с алиасами, пулы, домены, секторы) -------------------
_catalog = None


def load_catalog():
    global _catalog
    if _catalog is not None:
        return _catalog
    nav = json.loads((VAULT / "ML Clan — навигатор" / "data" / "navigator-data.json")
                     .read_text(encoding="utf-8"))
    cat = nav["catalog"]
    try:
        cc = json.loads((VAULT / "ML Clan — навигатор" / "config" / "company-catalog.json")
                        .read_text(encoding="utf-8"))
        companies = cc.get("companies", cat["companies"])
    except Exception:
        companies = cat["companies"]
    _catalog = {
        "sectors": cat["sectors"],
        "sector_label": {s["id"]: s["label"] for s in cat["sectors"]},
        "pools": cat["pools"],
        "domains": cat["domains"],
        "companies": companies,
    }
    return _catalog


# --- транскрибация ----------------------------------------------------------
def _run(cmd):
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def media_to_audio_chunks(src: Path, workdir: Path):
    """Извлекает моно-16k mp3 и режет на куски ~20 мин. Возвращает список путей."""
    mono = workdir / "audio.mp3"
    _run(["ffmpeg", "-y", "-i", str(src), "-vn", "-ac", "1", "-ar", "16000",
          "-b:a", "32k", "-f", "mp3", str(mono)])
    if mono.stat().st_size <= 24 * 1024 * 1024:
        return [mono]
    _run(["ffmpeg", "-y", "-i", str(mono), "-f", "segment",
          "-segment_time", str(SEGMENT_SECONDS), "-c", "copy",
          str(workdir / "seg_%03d.mp3")])
    chunks = sorted(workdir.glob("seg_*.mp3"))
    return chunks or [mono]


def transcribe_media(src: Path) -> str:
    client = _client()
    with tempfile.TemporaryDirectory() as td:
        chunks = media_to_audio_chunks(src, Path(td))
        parts = []
        for ch in chunks:
            with open(ch, "rb") as f:
                resp = client.audio.transcriptions.create(
                    model=TRANSCRIBE_MODEL, file=f, language="ru",
                    response_format="text")
            parts.append(resp if isinstance(resp, str) else getattr(resp, "text", str(resp)))
        return "\n".join(parts).strip()


# --- извлечение вопросов LLM ------------------------------------------------
def extract_questions(text: str) -> list[dict]:
    cat = load_catalog()
    pools = "\n".join(f'  "{p["id"]}" — {p["label"]}' for p in cat["pools"])
    domains = "\n".join(f'  "{d["id"]}" — {d["label"]}' for d in cat["domains"])
    system = (
        "Ты обрабатываешь материалы технических собеседований ML-инженеров на русском. "
        "На вход — транскрипт собеседования ИЛИ готовый список вопросов. "
        "Верни JSON-объект {\"questions\": [...]}. Каждый элемент: "
        "{\"text\": нормализованная самодостаточная формулировка вопроса на русском, "
        "\"pool_ids\": [подходящие id пулов], \"domains\": [подходящие id доменов]}.\n"
        "Правила: выдели ТОЛЬКО содержательные вопросы (технические/поведенческие), "
        "убери организационный диалог, приветствия, обрывки ASR. Склей дубли. "
        "Переформулируй в понятный самодостаточный вид, сохраняя смысл. "
        "Если вход уже список вопросов — просто нормализуй и размечай.\n"
        "АНОНИМИЗАЦИЯ (обязательно): полностью вырежи любые персональные данные "
        "кандидата и интервьюеров — имена, фамилии, ники/@-юзернеймы, телефоны, "
        "email, ссылки на соцсети, названия текущего/прошлого работодателя кандидата "
        "и названия его личных проектов/команд, города и прочие детали, по которым "
        "можно опознать человека. Убери обращения по имени («Иван, расскажите…» → "
        "«Расскажите…»). В итоговых формулировках вопросов НЕ должно остаться ничего, "
        "что выдаёт конкретного ученика; при этом технический смысл вопроса сохраняй.\n"
        f"Пулы (pool_ids):\n{pools}\nДомены (domains):\n{domains}"
    )
    client = _client()
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        response_format={"type": "json_object"},
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": text[:200000]}],
        temperature=0.2,
    )
    data = json.loads(resp.choices[0].message.content)
    valid_pools = {p["id"] for p in cat["pools"]}
    valid_domains = {d["id"] for d in cat["domains"]}
    out = []
    for q in data.get("questions", []):
        t = (q.get("text") or "").strip()
        if not t:
            continue
        out.append({
            "text": t,
            "pool_ids": [p for p in q.get("pool_ids", []) if p in valid_pools],
            "domains": [d for d in q.get("domains", []) if d in valid_domains],
        })
    return out


# --- матч компании ----------------------------------------------------------
def _norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s or "").lower().strip()
    return re.sub(r"[^\w]+", "", s)


def match_company(name: str, sector: str):
    """-> (company_id, canonical_name, sector). Если нет в каталоге — новая."""
    cat = load_catalog()
    key = _norm(name)
    if key:
        for c in cat["companies"]:
            names = [c.get("name", "")] + list(c.get("aliases", []))
            if any(_norm(n) == key for n in names):
                return c["id"], c.get("name", name), c.get("sector", sector) or sector
    cid = slugify(name) or ("company_" + key[:8] if key else "company")
    return cid, name.strip(), sector


# --- генерация заметки -------------------------------------------------------
def build_note_md(company_name, date, comment, questions) -> str:
    cat = load_catalog()
    pool_label = {p["id"]: p["label"] for p in cat["pools"]}
    head = f"# {company_name}" + (f" — {date}" if date else "")
    lines = [head, ""]
    if comment and comment.strip():
        lines += [comment.strip(), ""]
    lines.append("## Вопросы с собеседования")
    lines.append("")
    # группируем по первому пулу
    groups: dict[str, list[str]] = {}
    for q in questions:
        key = (q.get("pool_ids") or ["__"])[0]
        groups.setdefault(key, []).append(q["text"])
    for key in sorted(groups, key=lambda k: (k == "__", k)):
        if key != "__":
            lines.append(f"### {pool_label.get(key, key)}")
        for t in groups[key]:
            lines.append(f"- {t}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_note_html(note_md: str) -> str:
    return make_md().convert(note_md)


# --- оркестрация ------------------------------------------------------------
def process(job_id: str, *, src_path, pasted_text, company, sector, department,
            interview_date, comment, contributor):
    """Фоновая обработка. src_path ИЛИ pasted_text. Пишет статус в jobs."""
    try:
        if pasted_text and pasted_text.strip():
            db.update_job(job_id, status="extracting", stage="Извлекаю вопросы")
            transcript = pasted_text
        else:
            db.update_job(job_id, status="transcribing", stage="Транскрибирую аудио/видео")
            transcript = transcribe_media(Path(src_path))
            db.update_job(job_id, status="extracting", stage="Извлекаю вопросы")

        questions = extract_questions(transcript)
        if not questions:
            db.update_job(job_id, status="error",
                          message="Не удалось извлечь ни одного вопроса из материала.")
            return

        company_id, company_name, sector_final = match_company(company, sector)
        note_md = build_note_md(company_name, interview_date, comment, questions)

        db.update_job(job_id, status="saving", stage="Сохраняю")
        upload_id = db.insert_upload(
            company_id=company_id, company_name=company_name, sector=sector_final,
            department=(department or None), interview_date=interview_date,
            comment=comment, note_md=note_md, contributor=contributor,
            questions=questions)
        db.update_job(job_id, status="done", stage="Готово",
                      message=f"Добавлено вопросов: {len(questions)}", upload_id=upload_id)
    except Exception as e:  # noqa: BLE001
        db.update_job(job_id, status="error", message=f"{type(e).__name__}: {e}")
    finally:
        try:
            if src_path and os.path.exists(src_path):
                os.remove(src_path)  # сырьё не храним
        except Exception:
            pass
