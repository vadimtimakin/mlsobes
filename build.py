#!/usr/bin/env python3
"""Статический генератор сайта ML Clan Собесы.

Читает Obsidian-волт `Собесы/`, конвертит все .md в HTML (`site/`):
  - frontmatter (YAML) парсится и отбрасывается;
  - callouts `> [!question|quote|info|note]` -> стилизованные блоки;
  - wikilinks `[[Имя]]`, `[[Имя|Алиас]]`, `[[Папка/Имя]]`, ссылки на .pdf;
  - dataviewjs-блок навигатора -> mount-точка standalone-виджета;
  - подсветка кода через pygments.
Плюс боковое дерево-навигация, клиентский поиск (search-index.json) и
страница навигатора (порт Obsidian view.js).
"""
from __future__ import annotations

import html
import json
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import markdown
import yaml
from pygments.formatters import HtmlFormatter

ROOT = Path(__file__).resolve().parent
VAULT = ROOT / "Собесы"
ASSETS_SRC = ROOT / "assets"
OUT = ROOT / "site"

SITE_TITLE = "ML Clan — Собесы"


def nfc(s: str) -> str:
    """macOS отдаёт имена файлов в NFD — приводим всё к NFC, иначе 'й'/'ё'
    в путях и в тексте wikilinks не совпадают при сравнении."""
    return unicodedata.normalize("NFC", s)

# Папки в порядке вывода в сайдбаре (остальные — по алфавиту после них).
FOLDER_ORDER = [
    "",  # корневые заметки
    "Пулы вопросов ML-клана",
    "Лайвкодинг ML Clan",
    "ML Clan — подготовка с контекстом",
    "Материалы собесов",
    "ML Clan — навигатор",
]

HOME_NOTE = "НАЧНИ ЗДЕСЬ"  # basename заметки, которая станет главной

CALLOUT_LABELS = {
    "question": "Вопрос",
    "quote": "Цитата",
    "info": "Инфо",
    "note": "Заметка",
    "warning": "Внимание",
    "tip": "Совет",
    "abstract": "Конспект",
    "example": "Пример",
}

# --- транслитерация для slug'ов --------------------------------------------
_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


def slugify(text: str) -> str:
    text = text.lower()
    out = []
    for ch in text:
        if ch in _CYR:
            out.append(_CYR[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        elif ch in ("/", "\\"):
            out.append("--")
        else:
            out.append("-")
    slug = "".join(out)
    slug = re.sub(r"-{3,}", "--", slug)
    slug = re.sub(r"(^-+)|(-+$)", "", slug)
    return slug or "note"


# --- модель заметки ---------------------------------------------------------
class Note:
    def __init__(self, path: Path):
        self.path = path
        self.rel = path.relative_to(VAULT)
        self.folder = nfc(str(self.rel.parent)) if str(self.rel.parent) != "." else ""
        self.basename = nfc(path.stem)
        raw = nfc(path.read_text(encoding="utf-8"))
        self.frontmatter, self.body = split_frontmatter(raw)
        self.title = self.detect_title()
        self.slug = slugify(nfc(str(self.rel.with_suffix(""))))
        # навигатор получает чистый адрес (на него ссылается сайдбар и wikilinks)
        self.is_navigator = "dataviewjs" in self.body
        self.out_name = "navigator.html" if self.is_navigator else self.slug + ".html"

    def detect_title(self) -> str:
        m = re.search(r"^#\s+(.+)$", self.body, re.MULTILINE)
        if m:
            return m.group(1).strip()
        fm_title = self.frontmatter.get("title")
        if fm_title:
            return str(fm_title)
        return self.basename


def split_frontmatter(raw: str):
    if raw.startswith("---"):
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", raw, re.DOTALL)
        if m:
            try:
                fm = yaml.safe_load(m.group(1)) or {}
            except Exception:
                fm = {}
            return (fm if isinstance(fm, dict) else {}), raw[m.end():]
    return {}, raw


# --- защита fenced code блоков во время препроцессинга ----------------------
def protect_code(text: str):
    blocks = []

    def repl(m):
        blocks.append(m.group(0))
        return f"\x00CODE{len(blocks) - 1}\x00"

    text = re.sub(r"```.*?\n.*?```", repl, text, flags=re.DOTALL)
    return text, blocks


def restore_code(text: str, blocks):
    for i, b in enumerate(blocks):
        text = text.replace(f"\x00CODE{i}\x00", b)
    return text


# --- wikilinks --------------------------------------------------------------
WIKILINK_RE = re.compile(r"\[\[([^\[\]|#]+?)(#[^\[\]|]+?)?(?:\|([^\[\]]+?))?\]\]")


def build_resolver(notes):
    by_rel = {}       # relpath без расширения (lower) -> Note
    by_base = {}      # basename (lower) -> [Note]
    for n in notes:
        by_rel[nfc(str(n.rel.with_suffix(""))).lower()] = n
        by_base.setdefault(n.basename.lower(), []).append(n)

    # не-md ассеты (pdf и т.п.), которые копируем в site/assets
    asset_map = {}    # basename.lower() -> asset filename
    for p in VAULT.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".pdf",):
            asset_map[nfc(p.stem).lower()] = p.name
            asset_map[nfc(str(p.relative_to(VAULT).with_suffix(""))).lower()] = p.name

    def resolve(target: str):
        """-> (href, is_pdf) либо None если не резолвится."""
        t = target.strip()
        tl = t.lower()
        if tl.endswith(".pdf"):
            tl = tl[:-4]
        # pdf-ассет
        if tl in asset_map:
            return (f"assets/{asset_map[tl]}", True)
        base = tl.split("/")[-1]
        if base in asset_map:
            return (f"assets/{asset_map[base]}", True)
        # md по относительному пути
        if tl in by_rel:
            return (by_rel[tl].out_name, False)
        # md по basename
        cand = by_base.get(base)
        if cand and len(cand) == 1:
            return (cand[0].out_name, False)
        if cand:  # неоднозначно -> берём первый, лучше чем ничего
            return (cand[0].out_name, False)
        return None

    return resolve


def convert_wikilinks(text: str, resolve) -> str:
    def repl(m):
        target, _heading, alias = m.group(1), m.group(2), m.group(3)
        label = alias if alias else target.split("/")[-1]
        res = resolve(target)
        if res is None:
            return m.group(0)  # не трогаем — это не ссылка (напр. [[4,3,2,1]])
        href, _is_pdf = res
        return f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>'

    return WIKILINK_RE.sub(repl, text)


# --- callouts ---------------------------------------------------------------
CALLOUT_HEAD_RE = re.compile(r"^>\s*\[!(\w+)\]([-+]?)\s*(.*)$")


def convert_callouts(text: str, md_render) -> str:
    lines = text.split("\n")
    out = []
    i = 0
    n = len(lines)
    while i < n:
        m = CALLOUT_HEAD_RE.match(lines[i])
        if not m:
            out.append(lines[i])
            i += 1
            continue
        ctype = m.group(1).lower()
        collapse = m.group(2)  # '', '-', '+'
        title = m.group(3).strip()
        body_lines = []
        i += 1
        while i < n and (lines[i].startswith(">")):
            stripped = re.sub(r"^>\s?", "", lines[i])
            body_lines.append(stripped)
            i += 1
        label = title or CALLOUT_LABELS.get(ctype, ctype.capitalize())
        body_html = md_render("\n".join(body_lines)) if body_lines else ""
        cls = f"callout callout-{ctype}"
        if collapse in ("-", "+"):
            open_attr = " open" if collapse == "+" else ""
            block = (
                f'<details class="{cls}"{open_attr}>'
                f'<summary class="callout-title">{html.escape(label)}</summary>'
                f'<div class="callout-body">{body_html}</div></details>'
            )
        else:
            block = (
                f'<div class="{cls}">'
                f'<div class="callout-title">{html.escape(label)}</div>'
                f'<div class="callout-body">{body_html}</div></div>'
            )
        # окружаем пустыми строками, чтобы markdown трактовал как raw-блок
        out.append("")
        out.append(block)
        out.append("")
    return "\n".join(out)


# --- рендер markdown --------------------------------------------------------
def make_md():
    return markdown.Markdown(
        extensions=[
            "fenced_code", "codehilite", "tables", "toc",
            "attr_list", "sane_lists", "md_in_html",
        ],
        extension_configs={
            "codehilite": {"guess_lang": False, "css_class": "codehilite"},
        },
    )


def render_markdown(body: str, resolve) -> str:
    # 1) защищаем код
    body, code_blocks = protect_code(body)
    # 2) wikilinks (вне кода)
    body = convert_wikilinks(body, resolve)
    # 3) возвращаем код
    body = restore_code(body, code_blocks)

    md = make_md()

    def sub_render(sub_text: str) -> str:
        sub_text, cb = protect_code(sub_text)
        sub_text = convert_wikilinks(sub_text, resolve)
        sub_text = restore_code(sub_text, cb)
        sub_md = make_md()
        return sub_md.convert(sub_text)

    # 4) callouts (их тело рендерится отдельным инстансом)
    body = convert_callouts(body, sub_render)
    # 5) финальный рендер
    return md.convert(body)


def strip_to_text(body: str) -> str:
    t = re.sub(r"```.*?```", " ", body, flags=re.DOTALL)
    t = re.sub(r"`[^`]*`", " ", t)
    t = WIKILINK_RE.sub(lambda m: m.group(3) or m.group(1), t)
    t = re.sub(r"[#>*_\[\]\-]+", " ", t)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# --- сборка сайдбара --------------------------------------------------------
def folder_sort_key(folder: str):
    try:
        return (FOLDER_ORDER.index(folder), folder)
    except ValueError:
        return (len(FOLDER_ORDER), folder)


def natural_key(s: str):
    return [int(x) if x.isdigit() else x.lower()
            for x in re.split(r"(\d+)", s)]


def build_sidebar(notes, active_slug: str, home_note) -> str:
    folders = {}
    for n in notes:
        folders.setdefault(n.folder, []).append(n)

    parts = ['<nav class="sidebar-nav">']
    parts.append(
        f'<a class="nav-home{" active" if home_note and active_slug == home_note.slug else ""}" '
        f'href="{home_note.out_name if home_note else "index.html"}">🏠 Главная</a>'
    )
    parts.append('<a class="nav-navigator" href="navigator.html">🔎 Навигатор вопросов</a>')

    for folder in sorted(folders, key=folder_sort_key):
        items = sorted(folders[folder], key=lambda x: natural_key(x.basename))
        label = folder if folder else "Общее"
        parts.append('<details class="nav-group" open>')
        parts.append(f"<summary>{html.escape(label)}</summary>")
        parts.append("<ul>")
        for n in items:
            active = " class=\"active\"" if n.slug == active_slug else ""
            parts.append(
                f'<li><a{active} href="{n.out_name}">{html.escape(n.title)}</a></li>'
            )
        parts.append("</ul></details>")
    parts.append("</nav>")
    return "\n".join(parts)


# --- HTML-шаблон ------------------------------------------------------------
def page_html(title: str, sidebar: str, content: str, *, extra_head="", extra_body="") -> str:
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{html.escape(title)} · {SITE_TITLE}</title>
<link rel="stylesheet" href="assets/style.css">
{extra_head}
</head>
<body>
<header class="topbar">
  <button id="menu-toggle" aria-label="Меню">☰</button>
  <a class="brand" href="index.html">{SITE_TITLE}</a>
  <div class="search-wrap">
    <input id="search" type="search" placeholder="Поиск по заметкам…" autocomplete="off">
    <div id="search-results"></div>
  </div>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar">
    {sidebar}
  </aside>
  <main class="content">
    <article class="note">
      {content}
    </article>
  </main>
</div>
<script src="assets/app.js"></script>
{extra_body}
</body>
</html>
"""


def main():
    notes = []
    for p in sorted(VAULT.rglob("*.md")):
        if any(part.startswith(".") for part in p.relative_to(VAULT).parts):
            continue
        notes.append(Note(p))

    resolve = build_resolver(notes)
    home_note = next((n for n in notes if n.basename == HOME_NOTE), None)

    # чистим и готовим выход
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "assets").mkdir(parents=True)

    # копируем статику-исходники
    for fn in ("style.css", "app.js", "navigator.js", "view.css"):
        src = ASSETS_SRC / fn
        if src.exists():
            shutil.copy(src, OUT / "assets" / fn)

    # pygments css -> дописываем в style.css
    pyg = HtmlFormatter(style="monokai").get_style_defs(".codehilite")
    with open(OUT / "assets" / "style.css", "a", encoding="utf-8") as f:
        f.write("\n\n/* pygments */\n" + pyg + "\n")

    # копируем pdf и прочие ассеты из волта
    for p in VAULT.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".pdf",):
            shutil.copy(p, OUT / "assets" / p.name)

    # навигатор-данные
    nav_data = VAULT / "ML Clan — навигатор" / "data" / "navigator-data.json"
    if nav_data.exists():
        shutil.copy(nav_data, OUT / "assets" / "navigator-data.json")

    search_index = []

    for n in notes:
        sidebar = build_sidebar(notes, n.slug, home_note)

        # навигатор: заменяем dataviewjs на mount-точку
        is_navigator = n.is_navigator
        body = n.body
        if is_navigator:
            body = re.sub(r"```dataviewjs.*?```",
                          '<div id="navigator-root" class="navigator-root"></div>',
                          body, flags=re.DOTALL)

        content = render_markdown(body, resolve)

        extra_head = extra_body = ""
        if is_navigator:
            extra_head = '<link rel="stylesheet" href="assets/view.css">'
            extra_body = '<script src="assets/navigator.js"></script>'

        out_html = page_html(n.title, sidebar, content,
                             extra_head=extra_head, extra_body=extra_body)
        (OUT / n.out_name).write_text(out_html, encoding="utf-8")

        search_index.append({
            "title": n.title,
            "url": n.out_name,
            "folder": n.folder or "Общее",
            "text": strip_to_text(n.body)[:4000],
        })

    # index.html -> копия главной заметки (или первой)
    if home_note:
        shutil.copy(OUT / home_note.out_name, OUT / "index.html")
    elif notes:
        shutil.copy(OUT / notes[0].out_name, OUT / "index.html")

    (OUT / "assets" / "search-index.json").write_text(
        json.dumps(search_index, ensure_ascii=False), encoding="utf-8")

    meta = {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "notes": len(notes),
    }
    (OUT / "assets" / "build-meta.json").write_text(
        json.dumps(meta, ensure_ascii=False), encoding="utf-8")

    print(f"Построено {len(notes)} заметок -> {OUT}")


if __name__ == "__main__":
    main()
