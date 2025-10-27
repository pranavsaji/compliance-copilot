# app/utils/query.py
from __future__ import annotations
import re
from typing import List, Set

_STOP = {"the","and","or","for","of","to","in","a","an","on","with","we","our","is","are","be","as","by","from"}

def extract_keywords(q: str, min_len: int = 2) -> List[str]:
    """
    Pull useful tokens from a natural language question.
    Keeps control-like tokens (AC-2, IA-2), families (AC, IA, AU, CM, SC),
    and other alphanum words (>= min_len), lowercased and de-duped.
    """
    if not q:
        return []
    # control IDs and words
    control_ids = re.findall(r"\b([A-Za-z]{2,}\-\d{1,3}[a-z]?)\b", q)
    words = re.findall(r"\b([A-Za-z0-9]{%d,})\b" % min_len, q)
    raw: List[str] = control_ids + words
    toks: Set[str] = set()
    for t in raw:
        tl = t.lower()
        if tl in _STOP:
            continue
        toks.add(tl)
        # also add stripped family (e.g., 'ac-2' -> 'ac')
        m = re.match(r"([a-z]{2,})\-\d", tl)
        if m:
            toks.add(m.group(1))
    return list(toks)
