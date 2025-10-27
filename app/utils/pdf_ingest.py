# app/utils/pdf_ingest.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from pypdf import PdfReader
import re
import os

@dataclass
class Chunk:
    title: str
    text: str
    metadata: Dict[str, Any]

# ---------------- basic text cleanup ----------------
def _normalize_whitespace(s: str) -> str:
    s = s.replace("\r", "\n")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def extract_pdf_text_by_page(path: str) -> List[str]:
    reader = PdfReader(path)
    pages: List[str] = []
    for p in reader.pages:
        try:
            t = p.extract_text() or ""
        except Exception:
            t = ""
        pages.append(_normalize_whitespace(t))
    return pages

# ---------------- detectors (families / controls) ----------------
# NIST AC-2, AC-2(1), etc.
RX_NIST_CTRL = re.compile(r"\b([A-Z]{2,3})-(\d{1,3}[a-z]?(?:\(\d+\))?)\b")
RX_NIST_FAM  = re.compile(r"\b(AC|IA|AU|CM|SC|CP|IR|RA|SI|PL|PM|PS|MA|MP|PE|CA|SA|SR)\b")
# SOC 2 CC6.2, etc.
RX_SOC2_CTRL = re.compile(r"\bCC\d+(?:\.\d+)?\b", re.IGNORECASE)
# ISO A.8.24, etc.
RX_ISO_CTRL  = re.compile(r"\bA\.\d+(?:\.\d+)*\b")
# PCI 10.6, 10.6.1, etc.
RX_PCI_CTRL  = re.compile(r"\b\d{1,2}\.\d+(?:\.\d+)?\b")

def _auto_tags_from_text(text: str, standard_hint: Optional[str]) -> Dict[str, Any]:
    families: List[str] = []
    controls: List[str] = []
    tags: List[str] = []

    if not text:
        return {"families": families, "controls": controls, "tags": tags}

    t = text

    if standard_hint and "nist" in standard_hint.lower():
        controls = sorted(set(m.group(0) for m in RX_NIST_CTRL.finditer(t)))
        families = sorted(set(m.group(0) for m in RX_NIST_FAM.finditer(t)))
        tags.extend(["NIST", "NIST 800-53"])
    elif standard_hint and "soc" in standard_hint.lower():
        controls = sorted(set(m.group(0).upper() for m in RX_SOC2_CTRL.finditer(t)))
        tags.append("SOC2")
    elif standard_hint and "iso" in standard_hint.lower():
        controls = sorted(set(m.group(0) for m in RX_ISO_CTRL.finditer(t)))
        tags.extend(["ISO", "ISO 27001"])
    elif standard_hint and "pci" in standard_hint.lower():
        controls = sorted(set(m.group(0) for m in RX_PCI_CTRL.finditer(t)))
        tags.append("PCI")
    else:
        # No hint → try all patterns (best effort)
        controls.extend(m.group(0) for m in RX_NIST_CTRL.finditer(t))
        controls.extend(m.group(0).upper() for m in RX_SOC2_CTRL.finditer(t))
        controls.extend(m.group(0) for m in RX_ISO_CTRL.finditer(t))
        controls.extend(m.group(0) for m in RX_PCI_CTRL.finditer(t))
        controls = sorted(set(controls))
        fams = set(m.group(0) for m in RX_NIST_FAM.finditer(t))
        if fams:
            families = sorted(fams)

    tags = sorted(set(tags))
    return {"families": families, "controls": controls, "tags": tags}

# ---------------- smarter chunking ----------------
def _split_long_text(txt: str, target: int) -> List[str]:
    """
    Split a long page into ~target-sized pieces on paragraph/sentence boundaries.
    Falls back to hard cuts only if necessary (very long 'sentences').
    """
    if len(txt) <= target:
        return [txt]

    parts: List[str] = []
    # Prefer paragraph boundaries first
    paras = [p.strip() for p in re.split(r"\n{2,}", txt) if p.strip()]
    buf: List[str] = []
    cur = 0

    for p in paras:
        if cur + len(p) + 2 <= target:
            buf.append(p)
            cur += len(p) + 2
        else:
            if buf:
                parts.append("\n\n".join(buf))
                buf, cur = [p], len(p)
            else:
                # Paragraph itself is huge — split on sentences
                sents = re.split(r"(?<=[\.\?!])\s+", p)
                sbuf: List[str] = []
                scur = 0
                for s in sents:
                    if scur + len(s) + 1 <= target:
                        sbuf.append(s); scur += len(s) + 1
                    else:
                        if sbuf:
                            parts.append(" ".join(sbuf)); sbuf, scur = [s], len(s)
                        else:
                            # Sentence still huge — hard cuts
                            for k in range(0, len(s), target):
                                parts.append(s[k:k+target])
                            sbuf, scur = [], 0
                if sbuf:
                    parts.append(" ".join(sents if not parts else sbuf))
                buf, cur = [], 0

    if buf:
        parts.append("\n\n".join(buf))
    return parts

def page_chunks(
    pages: List[str],
    target_chars: int = 4000,
    overlap_chars: int = 400,
    split_within_page: bool = False,
) -> List[Tuple[str, int, int]]:
    """
    Greedy chunker with overlap.
    - If split_within_page is False (default), never splits inside a page (legacy behavior).
    - If True, pages longer than target_chars will be split on paragraph/sentence boundaries.
    """
    chunks: List[Tuple[str, int, int]] = []
    buf: List[str] = []
    buf_len = 0
    start_page = 0

    for i, page_text in enumerate(pages):
        if not page_text:
            continue

        # Optionally split long pages into multiple parts first
        page_parts = _split_long_text(page_text, target_chars) if split_within_page else [page_text]

        for j, part in enumerate(page_parts):
            if buf_len + len(part) > target_chars and buf:
                chunk_text = "\n\n".join(buf).strip()
                chunks.append((chunk_text, start_page, i))
                tail = chunk_text[-overlap_chars:] if overlap_chars > 0 else ""
                buf = [tail, part] if tail else [part]
                buf_len = len(tail) + len(part)
                start_page = i
            else:
                if not buf:
                    start_page = i
                buf.append(part)
                buf_len += len(part)

    if buf:
        chunk_text = "\n\n".join(buf).strip()
        chunks.append((chunk_text, start_page, max(start_page, len(pages) - 1)))
    return chunks

def chunk_pdf_file(
    path: str,
    title_hint: Optional[str] = None,
    standard_hint: Optional[str] = None,
    manual_tags: Optional[List[str]] = None,
    doc_type: str = "STANDARD",                 # "STANDARD" or "COMPANY"
    extra_metadata: Optional[Dict[str, Any]] = None,
    target_chars: int = 4000,
    overlap_chars: int = 400,
    split_within_page: bool = False,            # <-- NEW: toggle
) -> List[Chunk]:
    """
    Extract -> chunk -> auto-tag -> merge manual tags + extra metadata.
    `doc_type`: "STANDARD" for catalog/ground truth; "COMPANY" for org docs.
    `split_within_page`: if True, a single long PDF page may produce multiple chunks.
    """
    base = os.path.basename(path)
    title = title_hint or os.path.splitext(base)[0]
    manual_tags = [t.strip() for t in (manual_tags or []) if t.strip()]
    extra_metadata = extra_metadata or {}

    pages = extract_pdf_text_by_page(path)
    if not any(pages):
        return [Chunk(
            title=f"{title} [empty or non-extractable]",
            text="",
            metadata={"source": f"file://{path}", "pages": [], "doc_type": doc_type.upper()}
        )]

    raw_chunks = page_chunks(
        pages,
        target_chars=target_chars,
        overlap_chars=overlap_chars,
        split_within_page=split_within_page,
    )

    results: List[Chunk] = []
    for i, (txt, p_start, p_end) in enumerate(raw_chunks, start=1):
        detected = _auto_tags_from_text(txt, standard_hint)
        md: Dict[str, Any] = {
            "source": f"file://{path}",
            "page_start": int(p_start) + 1,
            "page_end": int(p_end) + 1,
            "chunk_index": i,
            "chunk_chars": len(txt),
            "standard": standard_hint or "",
            "families": detected.get("families", []),
            "controls": detected.get("controls", []),
            "tags": detected.get("tags", []),
            "manual_tags": manual_tags,           # highest weight
            "doc_type": doc_type.upper(),
        }
        # Merge additional metadata without clobbering core keys
        for k, v in (extra_metadata or {}).items():
            if k not in md:
                md[k] = v

        results.append(Chunk(
            title=f"{title} — chunk {i:03d}",
            text=txt,
            metadata=md
        ))
    return results
