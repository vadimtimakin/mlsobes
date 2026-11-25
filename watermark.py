#!/usr/bin/env python3
"""Невидимый watermark по гомоглифам (кириллица ↔ латиница-двойники).

Идея: в русском тексте часть букв визуально идентична латинским (а/a, о/o, е/e,
р/p, с/c, у/y, х/x и ряд заглавных). Подменяя такие буквы на двойника, кодируем
биты прямо в текст — глазом не видно, но по странице можно восстановить, чей это
экземпляр. В каждую страницу зашиваем `user_id` (32 бита) много раз подряд; на
декоде majority-vote по повторам даёт устойчивость к частичной порче/обрезке.

ВАЖНО (честные границы): переживает копипаст сырого текста/HTML, НО умирает от
скриншота, перенабора руками и прогона через LLM (нейронка выдаёт чистый текст).
Для устойчивости к переформулировке есть отдельный слой (перестановка вопросов).

Чистый stdlib, без зависимостей. Один и тот же файл лежит в mlsobes и mlhandbook.
"""
from __future__ import annotations

import re

# Кириллица → латиница, визуально идентичные в типовых шрифтах.
_CYR_TO_LAT = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "У": "Y", "Х": "X",
}
_LAT_TO_CYR = {v: k for k, v in _CYR_TO_LAT.items()}
_CYR_TWINS = set(_CYR_TO_LAT.keys())
_LAT_TWINS = set(_LAT_TO_CYR.keys())

# Однозначно кириллические буквы (нет латинского двойника) — «маркеры» того, что
# слово русское. Нужны, чтобы на декоде отличить русское слово от англ. термина.
_ALL_CYR = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ")
_CYR_MARKERS = (_ALL_CYR - _CYR_TWINS)

# Блоки, внутри которых НИЧЕГО не трогаем (сломается код/разметка).
_SKIP_TAGS = frozenset(("script", "style", "code", "pre", "kbd", "samp"))
_TAG_NAME_RE = re.compile(r"</?\s*([a-zA-Z0-9]+)")
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)  # последовательности букв (без цифр/_)

_PAYLOAD_BITS = 48  # user_id (TG-id уже > 2^32; 48 бит ≈ 2.8e14 — с запасом)
_PAYLOAD_MASK = (1 << _PAYLOAD_BITS) - 1


def _is_russian_word(word: str) -> bool:
    return any(ch in _CYR_MARKERS for ch in word)


def _user_id_to_bits(user_id: int) -> list[int]:
    v = user_id & _PAYLOAD_MASK
    return [(v >> (_PAYLOAD_BITS - 1 - i)) & 1 for i in range(_PAYLOAD_BITS)]


def _bits_to_user_id(bits: list[int]) -> int:
    v = 0
    for b in bits:
        v = (v << 1) | (b & 1)
    return v


def _iter_text_spans(html: str):
    """Отдаёт (start, end) текстовых кусков HTML вне тегов и вне skip-блоков.

    Войдя в skip-тег (script/style/code/pre…), прыгаем сразу к его закрытию — внутренние
    '<...>' (JS-строки, подсветка кода) НЕ считаем тегами, иначе разъедется баланс."""
    lower = html.lower()
    n = len(html)
    i = 0
    while i < n:
        ch = html[i]
        if ch == "<":
            j = html.find(">", i)
            if j == -1:
                break
            tag = html[i:j + 1]
            tm = _TAG_NAME_RE.match(tag)
            name = tm.group(1).lower() if tm else ""
            if name in _SKIP_TAGS and not tag.startswith("</") and not tag.endswith("/>"):
                close = lower.find("</" + name, j + 1)
                if close == -1:
                    break
                end = html.find(">", close)
                i = (end + 1) if end != -1 else n
            else:
                i = j + 1
        else:
            j = html.find("<", i)
            if j == -1:
                j = n
            yield i, j
            i = j


def embed(html: str, user_id: int) -> str:
    """Зашить user_id в текст HTML по гомоглифам. Возвращает новый HTML."""
    bits = _user_id_to_bits(user_id)
    if not bits:
        return html
    out = list(html)
    bit_i = 0
    for start, end in _iter_text_spans(html):
        text = html[start:end]
        for wm in _WORD_RE.finditer(text):
            word = wm.group(0)
            if not _is_russian_word(word):
                continue
            base = start + wm.start()
            for off, ch in enumerate(word):
                if ch in _CYR_TWINS or ch in _LAT_TWINS:
                    want = bits[bit_i % len(bits)]
                    bit_i += 1
                    cyr = ch if ch in _CYR_TWINS else _LAT_TO_CYR[ch]
                    out[base + off] = cyr if want == 0 else _CYR_TO_LAT[cyr]
    return "".join(out)


def _extract_bits(text: str) -> list[int]:
    """Прочитать биты из (возможно HTML) текста в том же порядке, что embed."""
    bits: list[int] = []
    for start, end in _iter_text_spans(text):
        chunk = text[start:end]
        for wm in _WORD_RE.finditer(chunk):
            word = wm.group(0)
            if not _is_russian_word(word):
                continue
            for ch in word:
                if ch in _CYR_TWINS:
                    bits.append(0)
                elif ch in _LAT_TWINS:
                    bits.append(1)
    return bits


def decode_user_id(text: str) -> int | None:
    """Восстановить user_id из утёкшего текста/HTML. None — если сигнала нет."""
    bits = _extract_bits(text)
    if len(bits) < _PAYLOAD_BITS:
        return None
    votes = [0] * _PAYLOAD_BITS
    count = [0] * _PAYLOAD_BITS
    for i, b in enumerate(bits):
        pos = i % _PAYLOAD_BITS
        votes[pos] += b
        count[pos] += 1
    recovered = [1 if votes[p] * 2 >= count[p] and count[p] else 0 for p in range(_PAYLOAD_BITS)]
    uid = _bits_to_user_id(recovered)
    # uid==0 = «все биты нулевые» = обычный немаркированный текст (кириллица), а не юзер.
    return uid or None


def strip(text: str) -> str:
    """Убрать watermark (все латинские двойники обратно в кириллицу в рус. словах).
    Для нормализации образца перед сравнением/декодом из другого источника."""
    out = list(text)
    for start, end in _iter_text_spans(text):
        chunk = text[start:end]
        for wm in _WORD_RE.finditer(chunk):
            word = wm.group(0)
            if not _is_russian_word(word):
                continue
            base = start + wm.start()
            for off, ch in enumerate(word):
                if ch in _LAT_TWINS:
                    out[base + off] = _LAT_TO_CYR[ch]
    return "".join(out)
