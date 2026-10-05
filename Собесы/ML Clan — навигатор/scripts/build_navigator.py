from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


NAV_ROOT = Path(__file__).resolve().parents[1]
VAULT_ROOT = NAV_ROOT.parents[1]
DEFAULT_POOL_ROOT = NAV_ROOT.parent / "Пулы вопросов ML-клана"
DEFAULT_EXPORT_ROOT = Path.home() / "Documents" / "ML Clan Export"
DEFAULT_OUTPUT = NAV_ROOT / "data" / "navigator-data.json"

POOL_LABELS = {
    "01": "Опыт, проекты и HR",
    "02": "Продуктовые и ML-кейсы",
    "03": "Математика, тервер и статистика",
    "04": "A/B, uplift и эксперименты",
    "05": "Данные, EDA и feature engineering",
    "06": "Classic ML",
    "07": "Деревья и ансамбли",
    "08": "RecSys, ranking и search",
    "09": "Временные ряды",
    "10": "Deep Learning, NLP, CV и LLM",
    "11": "Python",
    "12": "SQL, базы и Spark",
    "13": "Алгоритмы и структуры данных",
    "14": "ML System Design и MLOps",
    "15": "Метрики",
    "16": "Лайвкодинг"
}

BASE_DOMAINS = {
    "01": ["experience_hr"],
    "02": ["product_cases"],
    "03": ["math_stats"],
    "04": ["experiments"],
    "05": ["data"],
    "06": ["classic_ml"],
    "07": ["classic_ml"],
    "08": ["recsys"],
    "09": ["time_series"],
    "10": ["deep_learning"],
    "11": ["python"],
    "12": ["sql_data"],
    "13": ["algorithms"],
    "14": ["ml_system_design"],
    "15": ["metrics"],
    "16": ["livecoding"]
}

DOMAIN_LABELS = {
    "experience_hr": "Опыт и HR",
    "product_cases": "Продуктовые кейсы",
    "math_stats": "Математика и статистика",
    "experiments": "A/B и эксперименты",
    "data": "Данные и признаки",
    "classic_ml": "Classic ML",
    "recsys": "RecSys",
    "ranking": "Ranking",
    "search": "Search / retrieval",
    "time_series": "Временные ряды",
    "deep_learning": "Deep Learning",
    "nlp": "NLP",
    "llm": "LLM",
    "cv": "CV",
    "python": "Python",
    "sql_data": "SQL и базы",
    "algorithms": "Алгоритмы",
    "ml_system_design": "MLSD / MLOps",
    "metrics": "Метрики",
    "livecoding": "Лайвкодинг"
}

SPECIALIZED_KEYWORDS = {
    "llm": [
        r"\bllm\b", r"\brag\b", r"\bgpt\b", r"\blora\b", r"\bdpo\b",
        r"prompt", r"промпт", r"kv[- ]?к[эе]ш", r"instruction tuning",
        r"language model", r"языков(?:ая|ой|ые) модел"
    ],
    "nlp": [
        r"\bnlp\b", r"bert", r"word2vec", r"fasttext", r"токенизац",
        r"лемматизац", r"стемминг", r"named entity", r"\bner\b",
        r"текстов", r"язык(?:а|ов)"
    ],
    "cv": [
        r"\bcv\b", r"computer vision", r"компьютерн(?:ое|ого) зрени",
        r"\bcnn\b", r"resnet", r"\byolo\b", r"сегментац", r"детекц",
        r"изображен", r"\bclip\b"
    ],
    "ranking": [
        r"ранжирован", r"\brank(?:er|ing)?\b", r"\bndcg\b", r"\bmap@?k?\b",
        r"precision@", r"recall@", r"learning[- ]to[- ]rank", r"pairwise", r"listwise"
    ],
    "search": [
        r"поисков(?:ая|ой|ую) выдач", r"информационн(?:ый|ого) поиск",
        r"\bretrieval\b", r"candidate generation", r"\bann\b", r"faiss",
        r"hnsw", r"векторн(?:ый|ого) поиск"
    ],
    "recsys": [
        r"рекомендац", r"\brecsys\b", r"коллаборативн", r"\bals\b",
        r"lightfm", r"user[–-]item", r"item[–-]item", r"cold start"
    ]
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(flatten_text(v) for v in value)
    return str(value)


def normalize_question(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[`*_~=]", "", text)
    text = re.sub(r"[^\w\s@+.-]", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip(" .-")


def clean_question(line: str) -> tuple[str, list[int]] | None:
    ids = [int(value) for value in re.findall(r"#(\d+)", line)]
    if not ids:
        return None
    body = re.sub(r"^\s*[-*]\s+", "", line).strip()
    citation = re.search(r"\s+[—–]\s+(?:†\s*)?#\d+", body)
    if citation:
        body = body[: citation.start()]
    else:
        first_id = re.search(r"(?:†\s*)?#\d+", body)
        if first_id:
            body = body[: first_id.start()]
    body = body.strip().strip("=").strip()
    body = body.replace("==", "")
    if not body:
        return None
    return body, list(dict.fromkeys(ids))


def pool_id_from_name(name: str) -> str | None:
    match = re.match(r"(\d{2})_", name)
    return match.group(1) if match else None


def parse_pools(pool_root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(pool_root.glob("*.md")):
        pool_id = pool_id_from_name(path.name)
        if not pool_id or pool_id == "00":
            continue
        section = "Без раздела"
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.startswith("## "):
                section = line[3:].strip().replace("==", "")
                continue
            if not re.match(r"^\s*[-*]\s+", line):
                continue
            parsed = clean_question(line)
            if not parsed:
                continue
            question, source_ids = parsed
            rows.append({
                "text": question,
                "normalized": normalize_question(question),
                "source_ids": source_ids,
                "pool_id": pool_id,
                "pool_label": POOL_LABELS.get(pool_id, path.stem),
                "section": section,
                "file": path.name,
                "line": line_number
            })
    return rows


def question_domains(text: str, pool_ids: Iterable[str]) -> list[str]:
    pool_ids = list(pool_ids)
    domains = {domain for pool_id in pool_ids for domain in BASE_DOMAINS.get(pool_id, [])}
    lowered = text.lower().replace("ё", "е")
    for domain, patterns in SPECIALIZED_KEYWORDS.items():
        if any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in patterns):
            domains.add(domain)
    return sorted(domains)


def source_override_maps(config: dict[str, Any]) -> tuple[dict[int, str], dict[int, int], dict[int, dict[str, Any]]]:
    company_by_source: dict[int, str] = {}
    for group in config.get("company_groups", []):
        for source_id in group["ids"]:
            if source_id in company_by_source:
                raise ValueError(f"Source #{source_id} указан в нескольких company_groups")
            company_by_source[source_id] = group["company"]

    interview_by_source: dict[int, int] = {}
    for bundle in config.get("bundles", []):
        interview_id = int(bundle["interview_id"])
        for source_id in bundle["ids"]:
            if source_id in interview_by_source:
                raise ValueError(f"Source #{source_id} указан в нескольких bundles")
            interview_by_source[source_id] = interview_id

    per_source = {int(key): value for key, value in config.get("source_overrides", {}).items()}
    return company_by_source, interview_by_source, per_source


def load_archive_records(db_path: Path, source_ids: set[int]) -> dict[int, dict[str, Any]]:
    if not db_path.exists():
        raise FileNotFoundError(f"Не найден архив ML Clan: {db_path}")
    records: dict[int, dict[str, Any]] = {}
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    try:
        ordered = sorted(source_ids)
        for start in range(0, len(ordered), 500):
            chunk = ordered[start : start + 500]
            marks = ",".join("?" for _ in chunk)
            query = f"SELECT message_id, message_date, record_json FROM messages WHERE message_id IN ({marks})"
            for row in connection.execute(query, chunk):
                raw = json.loads(row["record_json"] or "{}")
                records[int(row["message_id"])] = {
                    "date": (row["message_date"] or "")[:10] or None,
                    "text": " ".join(filter(None, [
                        flatten_text(raw.get("text")),
                        flatten_text(raw.get("caption")),
                        flatten_text(raw.get("content"))
                    ])).strip()
                }
    finally:
        connection.close()
    return records


def read_prefix(path: Path, limit: int = 16_000) -> str:
    if not path.exists():
        return ""
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return handle.read(limit)


def load_asset_prefixes(export_root: Path, source_ids: set[int]) -> dict[int, str]:
    result: dict[int, str] = {}
    transcript_root = export_root / "interviews" / "transcripts"
    for source_id in source_ids:
        text = read_prefix(transcript_root / f"{source_id}.txt")
        if text:
            result[source_id] = text

    ocr_root = export_root / "ocr" / "texts"
    if ocr_root.exists():
        wanted = {str(source_id) for source_id in source_ids if source_id not in result}
        for path in ocr_root.rglob("*.txt"):
            if path.stem in wanted:
                result[int(path.stem)] = read_prefix(path)
    return result


def detect_company(text: str, companies: list[dict[str, Any]]) -> str:
    lowered = text.lower().replace("ё", "е")
    candidates: list[tuple[int, int, str]] = []
    for company in companies:
        for alias in company.get("aliases", []):
            normalized_alias = alias.lower().replace("ё", "е")
            position = lowered.find(normalized_alias)
            if position >= 0:
                candidates.append((position, -len(normalized_alias), company["name"]))
    return min(candidates)[2] if candidates else "Не определено"


def build_interviews(
    source_ids: set[int],
    archive_records: dict[int, dict[str, Any]],
    asset_prefixes: dict[int, str],
    catalog: dict[str, Any],
    company_by_source: dict[int, str],
    interview_by_source: dict[int, int],
    per_source: dict[int, dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    companies = catalog["companies"]
    company_catalog = {company["name"]: company for company in companies}
    valid_companies = set(company_catalog)
    unknown_company_sources = source_ids - set(company_by_source)
    if unknown_company_sources:
        missing = ", ".join(f"#{value}" for value in sorted(unknown_company_sources))
        raise ValueError(f"Для source ID не задана компания: {missing}")
    invalid_companies = sorted(set(company_by_source.values()) - valid_companies)
    if invalid_companies:
        raise ValueError(f"Компании отсутствуют в company-catalog.json: {', '.join(invalid_companies)}")

    source_meta: dict[int, dict[str, Any]] = {}
    for source_id in sorted(source_ids):
        record = archive_records.get(source_id, {})
        combined_text = " ".join(filter(None, [record.get("text", ""), asset_prefixes.get(source_id, "")]))
        manual_company = company_by_source.get(source_id)
        company_name = manual_company or detect_company(combined_text, companies)
        override = per_source.get(source_id, {})
        company = company_catalog.get(company_name, company_catalog["Не определено"])
        source_meta[source_id] = {
            "source_id": source_id,
            "interview_id": interview_by_source.get(source_id, source_id),
            "company": company["name"],
            "company_id": company["id"],
            "sector": company["sector"],
            "department": override.get("department"),
            "stage": override.get("stage"),
            "date": record.get("date"),
            "source_kind": override.get("source_kind", "interview"),
            "metadata_method": "manual" if manual_company else "alias"
        }

    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for meta in source_meta.values():
        grouped[meta["interview_id"]].append(meta)

    sector_labels = {sector["id"]: sector["label"] for sector in catalog["sectors"]}
    interviews: list[dict[str, Any]] = []
    for interview_id, members in sorted(grouped.items()):
        company = Counter(member["company"] for member in members).most_common(1)[0][0]
        company_info = company_catalog[company]
        departments = sorted({member["department"] for member in members if member["department"]})
        stages = sorted({member["stage"] for member in members if member["stage"]})
        dates = sorted(member["date"] for member in members if member["date"])
        kinds = Counter(member["source_kind"] for member in members)
        interviews.append({
            "id": interview_id,
            "source_ids": sorted(member["source_id"] for member in members),
            "company": company,
            "company_id": company_info["id"],
            "sector": company_info["sector"],
            "sector_label": sector_labels[company_info["sector"]],
            "department": " / ".join(departments) or None,
            "stage": " / ".join(stages) or None,
            "date": dates[-1] if dates else None,
            "source_kind": kinds.most_common(1)[0][0],
            "metadata_method": "manual"
        })
    return interviews, {source_id: meta["interview_id"] for source_id, meta in source_meta.items()}


def stable_question_id(normalized: str) -> str:
    return "q_" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def build_questions(rows: list[dict[str, Any]], source_to_interview: dict[int, int]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["normalized"]].append(row)

    questions: list[dict[str, Any]] = []
    used_ids: dict[str, str] = {}
    for normalized, variants in grouped.items():
        question_id = stable_question_id(normalized)
        if question_id in used_ids and used_ids[question_id] != normalized:
            raise ValueError(f"Коллизия question ID: {question_id}")
        used_ids[question_id] = normalized
        pool_ids = sorted({variant["pool_id"] for variant in variants})
        source_ids = sorted({source_id for variant in variants for source_id in variant["source_ids"]})
        evidence = [
            {"source_id": source_id, "interview_id": source_to_interview[source_id]}
            for source_id in source_ids
        ]
        sections = sorted({variant["section"] for variant in variants})
        questions.append({
            "id": question_id,
            "text": variants[0]["text"],
            "pool_ids": pool_ids,
            "pool_labels": [POOL_LABELS.get(pool_id, pool_id) for pool_id in pool_ids],
            "sections": sections,
            "domains": question_domains(variants[0]["text"], pool_ids),
            "evidence": evidence
        })
    return sorted(questions, key=lambda question: (question["pool_ids"], question["text"].lower()))


def apply_manual_merges(questions: list[dict[str, Any]], config: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    by_id = {question["id"]: question for question in questions}
    removed: set[str] = set()
    merge_count = 0
    for group in config.get("merge_groups", []):
        ids = group.get("question_ids", [])
        if len(ids) < 2:
            continue
        missing = [question_id for question_id in ids if question_id not in by_id]
        if missing:
            raise ValueError(f"В manual-deduplication.json неизвестны ID: {', '.join(missing)}")
        target = by_id[ids[0]]
        evidence_by_source = {item["source_id"]: item for item in target["evidence"]}
        for source_id in ids[1:]:
            other = by_id[source_id]
            target["pool_ids"] = sorted(set(target["pool_ids"]) | set(other["pool_ids"]))
            target["pool_labels"] = [POOL_LABELS.get(pool_id, pool_id) for pool_id in target["pool_ids"]]
            target["sections"] = sorted(set(target["sections"]) | set(other["sections"]))
            target["domains"] = sorted(set(target["domains"]) | set(other["domains"]))
            for item in other["evidence"]:
                evidence_by_source[item["source_id"]] = item
            removed.add(source_id)
            merge_count += 1
        target["evidence"] = [evidence_by_source[key] for key in sorted(evidence_by_source)]
        if group.get("canonical_text"):
            target["text"] = group["canonical_text"]
    return [question for question in questions if question["id"] not in removed], merge_count


def build_dataset(pool_root: Path, export_root: Path) -> dict[str, Any]:
    catalog = load_json(NAV_ROOT / "config" / "company-catalog.json")
    overrides = load_json(NAV_ROOT / "config" / "interview-overrides.json")
    dedup = load_json(NAV_ROOT / "config" / "manual-deduplication.json")
    company_by_source, interview_by_source, per_source = source_override_maps(overrides)

    rows = parse_pools(pool_root)
    source_ids = {source_id for row in rows for source_id in row["source_ids"]}
    archive_records = load_archive_records(export_root / "archive.sqlite3", source_ids)
    missing_archive = source_ids - set(archive_records)
    if missing_archive:
        missing = ", ".join(f"#{value}" for value in sorted(missing_archive))
        raise ValueError(f"Source ID отсутствуют в archive.sqlite3: {missing}")
    asset_prefixes = load_asset_prefixes(export_root, source_ids)
    interviews, source_to_interview = build_interviews(
        source_ids,
        archive_records,
        asset_prefixes,
        catalog,
        company_by_source,
        interview_by_source,
        per_source
    )
    questions = build_questions(rows, source_to_interview)
    exact_merges = len(rows) - len(questions)
    questions, manual_merges = apply_manual_merges(questions, dedup)

    pool_ids = sorted({pool_id for question in questions for pool_id in question["pool_ids"]})
    domain_ids = sorted({domain for question in questions for domain in question["domains"]})
    interview_kinds = Counter(interview["source_kind"] for interview in interviews)
    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": {
            "pool_root": str(pool_root),
            "export_root": str(export_root),
            "policy": "Интервью ML Clan — единственный источник встречаемости; Markdown-пулы задают формулировки и темы."
        },
        "summary": {
            "question_rows": len(rows),
            "questions": len(questions),
            "source_ids": len(source_ids),
            "interviews": len(interviews),
            "exact_text_merges": exact_merges,
            "manual_semantic_merges": manual_merges,
            "interview_kinds": dict(sorted(interview_kinds.items()))
        },
        "catalog": {
            "sectors": catalog["sectors"],
            "companies": [
                {"id": company["id"], "name": company["name"], "sector": company["sector"]}
                for company in catalog["companies"]
            ],
            "pools": [{"id": pool_id, "label": POOL_LABELS.get(pool_id, pool_id)} for pool_id in pool_ids],
            "domains": [{"id": domain, "label": DOMAIN_LABELS.get(domain, domain)} for domain in domain_ids]
        },
        "interviews": interviews,
        "questions": questions
    }


def comparable(dataset: dict[str, Any]) -> dict[str, Any]:
    copy = dict(dataset)
    copy.pop("generated_at", None)
    return copy


def main() -> int:
    parser = argparse.ArgumentParser(description="Собирает данные для ML Clan Navigator")
    parser.add_argument("--pool-root", type=Path, default=DEFAULT_POOL_ROOT)
    parser.add_argument("--export-root", type=Path, default=DEFAULT_EXPORT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="Проверить, что JSON уже актуален")
    args = parser.parse_args()

    dataset = build_dataset(args.pool_root.resolve(), args.export_root.resolve())
    if args.check:
        if not args.output.exists():
            print(f"ERROR: отсутствует {args.output}", file=sys.stderr)
            return 1
        current = json.loads(args.output.read_text(encoding="utf-8"))
        if comparable(current) != comparable(dataset):
            print("ERROR: navigator-data.json устарел; запустите генератор без --check", file=sys.stderr)
            return 1
        print(json.dumps(dataset["summary"], ensure_ascii=False))
        return 0

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, separators=(",", ":")) + "\n",
        encoding="utf-8"
    )
    print(json.dumps(dataset["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
