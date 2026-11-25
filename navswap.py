#!/usr/bin/env python3
"""Watermark навигатора: per-user перестановка пары соседних вопросов в рамках собеса.

navigator-data.json отдаётся как JSON (homoglyph на него не ложится), поэтому порядок
вопросов внутри собеса — его собственная метка. Переставляем только вопросы, принадлежащие
РОВНО одному собесу (single-owner) — тогда своп не задевает другие собесы и не меняет смысл.

Схема: на каждый собес берём до MAX_PAIRS_PER_INTERVIEW непересекающихся пар его вопросов;
своп пары t ⇔ бит payload (user_id, 48 бит) на позиции hash(interview_id, t) % 48.
Позиция бита = СТАБИЛЬНЫЙ хеш → добавление/удаление собесов не ломает выравнивание.
Декод: по утёкшему JSON сверяем порядок пар с каноническим, majority-vote → user_id.

Переживает LLM-переформулировку текстов (порядок вопросов сохраняется), но декод возможен
лишь если утёк сам список/JSON с порядком, а не пересказ одного вопроса.
"""
from __future__ import annotations

import hashlib

from watermark import _PAYLOAD_BITS, _user_id_to_bits, _bits_to_user_id

MAX_PAIRS_PER_INTERVIEW = 2  # «пара перестановок на собес, или меньше» — максимально незаметно


def _owner(q) -> object | None:
    """interview_id, если вопрос принадлежит ровно одному собесу, иначе None."""
    iids = {e.get("interview_id") for e in (q.get("evidence") or [])
            if e.get("interview_id") is not None}
    return next(iter(iids)) if len(iids) == 1 else None


def _slot_bitpos(interview_id, t: int) -> int:
    h = hashlib.blake2b(f"{interview_id}:{t}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") % _PAYLOAD_BITS


def _interview_pairs(questions: list) -> dict:
    """interview_id -> [(idxA, idxB), ...] — индексы пар single-owner вопросов в массиве."""
    groups: dict = {}
    for idx, q in enumerate(questions):
        o = _owner(q)
        if o is not None:
            groups.setdefault(o, []).append(idx)
    pairs: dict = {}
    for iid, idxs in groups.items():
        pr = [(idxs[2 * t], idxs[2 * t + 1])
              for t in range(min(MAX_PAIRS_PER_INTERVIEW, len(idxs) // 2))]
        if pr:
            pairs[iid] = pr
    return pairs


def permute(nav: dict, user_id: int) -> dict:
    """Вернуть копию nav с переставленными под user_id вопросами."""
    qs = nav.get("questions")
    if not qs:
        return nav
    bits = _user_id_to_bits(user_id)
    new_qs = list(qs)
    for iid, pr in _interview_pairs(qs).items():
        for t, (a, b) in enumerate(pr):
            if bits[_slot_bitpos(iid, t)]:
                new_qs[a], new_qs[b] = new_qs[b], new_qs[a]
    out = dict(nav)
    out["questions"] = new_qs
    return out


def decode(leaked_nav: dict, canonical_nav: dict) -> int | None:
    """Вычислить user_id из утёкшего navigator-data.json (нужен канонический для сверки)."""
    cqs = canonical_nav.get("questions") or []
    lqs = leaked_nav.get("questions") or []
    if not cqs or not lqs:
        return None
    lpos = {q.get("id"): i for i, q in enumerate(lqs)}
    votes = [0] * _PAYLOAD_BITS
    cnt = [0] * _PAYLOAD_BITS
    for iid, pr in _interview_pairs(cqs).items():
        for t, (a, b) in enumerate(pr):
            pa, pb = lpos.get(cqs[a].get("id")), lpos.get(cqs[b].get("id"))
            if pa is None or pb is None:
                continue
            pos = _slot_bitpos(iid, t)
            votes[pos] += 1 if pa > pb else 0  # pa>pb ⇒ пара переставлена ⇒ бит 1
            cnt[pos] += 1
    if not any(cnt):
        return None
    recovered = [1 if cnt[p] and votes[p] * 2 >= cnt[p] else 0 for p in range(_PAYLOAD_BITS)]
    return _bits_to_user_id(recovered) or None
