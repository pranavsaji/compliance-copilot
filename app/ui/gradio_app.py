# app/ui/gradio_app.py
from __future__ import annotations
import json
import os
import re
import hashlib
from typing import List, Optional, Dict, Any, Tuple

import gradio as gr

from app.services.rag import RAGService
from app.config import get_settings
from app.utils.pdf_ingest import chunk_pdf_file

settings = get_settings()
rag = RAGService()
BACKEND = settings.STORE_BACKEND.lower()

STANDARD_CHOICES = [
    "(Any)",
    "NIST SP 800-53 Rev.5",
    "SOC 2 TSC",
    "ISO/IEC 27001:2022",
    "PCI DSS v4.0.1",
]
DOC_TYPE_CHOICES = ["STANDARD", "COMPANY"]

# ---------- helpers ----------

def _fmt_citations(cites):
    if not cites:
        return "No citations."
    return "\n".join(
        f"• {c.get('type','?').upper()}: {c.get('title','untitled')}"
        + (f" [{c.get('framework','')}]" if c.get('framework') else "")
        + (f" ({c.get('doc_type')})" if c.get('doc_type') else "")
        for c in cites
    )

def _status():
    s = get_settings()
    def _set(x): return 'set' if x else '—'
    lines = [
        f"**STORE_BACKEND**: `{s.STORE_BACKEND}`",
        f"**LLM_PROVIDER**: `{s.LLM_PROVIDER}`",
        f"**OPENAI_API_KEY**: {_set(s.OPENAI_API_KEY or os.getenv('OPENAI_API_KEY'))}",
        f"**OPENAI_API_BASE**: `{(getattr(s, 'OPENAI_API_BASE', '') or os.getenv('OPENAI_API_BASE') or '').strip() or 'default'}`",
        f"**GROQ_API_KEY**: {_set(s.GROQ_API_KEY or os.getenv('GROQ_API_KEY'))}",
        f"**GROQ_API_BASE**: `{(getattr(s, 'GROQ_API_BASE', '') or os.getenv('GROQ_API_BASE') or '').strip() or 'default'}`",
        f"**FRIENDLIAI_API_KEY**: {_set(getattr(s, 'FRIENDLIAI_API_KEY', '') or os.getenv('FRIENDLIAI_API_KEY'))}",
        f"**FRIENDLIAI_API_BASE**: `{(getattr(s, 'FRIENDLIAI_API_BASE', '') or os.getenv('FRIENDLIAI_API_BASE') or '').strip() or 'unset'}`",
    ]
    try:
        counts = rag.store.counts()
        lines.append(f"**Docs**: policies={counts.get('policies',0)}, evidence={counts.get('evidence',0)}")
    except Exception:
        pass
    return "\n".join(lines)

def _standards_snapshot():
    try:
        ev = getattr(rag.store, "evidence", [])
        pol = getattr(rag.store, "policies", [])
        import collections
        def _meta(d):
            m = d.get("metadata")
            if isinstance(m, str):
                try: m = json.loads(m)
                except Exception: m = {}
            return m if isinstance(m, dict) else {}
        def key_of(d):
            md = _meta(d)
            return (md.get("standard") or "(none)", md.get("doc_type") or "(unset)")
        cnt = collections.Counter(key_of(d) for d in ev)
        cnt_pol = collections.Counter((_meta(d).get("standard") or "(none)") for d in pol)
        return (
            "### Standards snapshot\n"
            f"- Evidence by (standard, doc_type): {dict(cnt)}\n"
            f"- Policies by standard: {dict(cnt_pol)}\n"
            f"- Total evidence: {len(ev)}, policies: {len(pol)}"
        )
    except Exception as e:
        return f"Snapshot error: {e}"

def _reset_memory():
    try:
        if hasattr(rag.store, "clear_all"):
            rag.store.clear_all()
        else:
            if hasattr(rag.store, "policies"): rag.store.policies.clear()
            if hasattr(rag.store, "evidence"): rag.store.evidence.clear()
            if hasattr(rag.store, "version"): rag.store.version += 1
        return "In-memory store cleared ✅"
    except Exception as e:
        return f"Reset error: {e}"

_STD_PATTERNS = [
    (re.compile(r"\bnist\b.*\b800[-\s]?53", re.I), "NIST SP 800-53 Rev.5"),
    (re.compile(r"\bsoc\s*2\b|\btrust\s*services\b|\btsc\b", re.I), "SOC 2 TSC"),
    (re.compile(r"\biso\b.*\b27001\b|\biso/iec\s*27001", re.I), "ISO/IEC 27001:2022"),
    (re.compile(r"\bpci\b.*\bdss\b", re.I), "PCI DSS v4.0.1"),
]

def detect_standard_from_filename(name: str) -> Optional[str]:
    base = os.path.basename(name or "")
    for rx, label in _STD_PATTERNS:
        if rx.search(base):
            return label
    return None

def _sha1_file(path: str) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def _already_ingested(source: str, file_sha1: str) -> bool:
    """Best-effort check: if evidence exists with same source or same sha1, skip."""
    ev = getattr(rag.store, "evidence", [])
    for d in ev:
        md = d.get("metadata")
        if isinstance(md, str):
            try: md = json.loads(md)
            except Exception: md = {}
        if not isinstance(md, dict):
            continue
        src = md.get("source") or ""
        sha = md.get("file_sha1") or ""
        if (src and src == source) or (sha and sha == file_sha1):
            return True
    return False

# ---------- persistence helpers for Admin ----------

def _save_now():
    try:
        return getattr(rag.store, "save_to_disk")()
    except Exception as e:
        return f"Save error: {e}"

def _load_now():
    try:
        return getattr(rag.store, "load_from_disk")()
    except Exception as e:
        return f"Load error: {e}"

def _list_sources():
    try:
        lst = getattr(rag.store, "list_sources")()
        if not lst:
            return "No evidence sources found."
        return "### Evidence sources\n" + "\n".join(f"- {s}" for s in lst)
    except Exception as e:
        return f"List error: {e}"

def _delete_by_source(substr: str):
    if not (substr or "").strip():
        return "Enter part of the filename/path (metadata.source) to delete."
    try:
        removed = getattr(rag.store, "delete_by_source")(substr.strip())
        return f"Removed {removed} evidence chunks matching '{substr}'."
    except Exception as e:
        return f"Delete error: {e}"

# ---------- LLM healthcheck ----------

async def _llm_health():
    try:
        return await rag.llm.healthcheck()
    except Exception as e:
        return f"Healthcheck error: {e}"

# ---------- handlers ----------

async def _ask(
    question: str,
    frameworks_text: str,
    limit: int,
    std_choice: str,
    tags_csv: str,
    strict: bool,
    include_company: bool,
    gap_aware: bool,
    require_company: bool,
):
    try:
        frameworks = [s.strip() for s in frameworks_text.split(",") if s.strip()] if frameworks_text else []
        standard = None if not std_choice or std_choice == "(Any)" else std_choice
        tags = [t.strip() for t in tags_csv.split(",") if t.strip()] if tags_csv else []

        result = await rag.answer(
            question.strip(),
            frameworks,
            limit,
            standard=standard,
            tags=tags,
            strict_standard=bool(strict),
            include_company=bool(include_company),
            guidance_mode=bool(gap_aware),
            hard_require_company=bool(require_company),
        )
        dbg = result.get("debug", {})
        stats = (
            f"_retrieved: policies={dbg.get('policy_hits',0)}, "
            f"evidence={dbg.get('evidence_hits',0)}, "
            f"company_evidence={dbg.get('company_evidence',0)}, "
            f"standard_evidence={dbg.get('standard_evidence',0)}_"
        )
        citations_txt = _fmt_citations(result.get("citations", []))
        answer_txt = (result.get("answer", "") or "").strip()
        if stats:
            answer_txt = f"{answer_txt}\n\n{stats}"
        return answer_txt, citations_txt
    except Exception as e:
        return f"⚠️ Error: {e}", "Check .env and logs. Verify LLM provider/key in Admin → Status."

def _ingest_policy(title, framework, control_ids_csv, text, metadata_json):
    control_ids = [c.strip() for c in control_ids_csv.split(",") if c.strip()] if control_ids_csv else []
    try:
        metadata = json.loads(metadata_json) if metadata_json.strip() else {}
    except json.JSONDecodeError as e:
        return f"Metadata JSON error: {e}"
    obj = {
        "title": (title or "").strip(),
        "framework": (framework or "GENERIC").strip(),
        "control_ids": control_ids,
        "text": (text or "").strip(),
        "metadata": json.dumps(metadata),
    }
    rag.store.upsert_policy(obj)
    return "Policy ingested ✅"

def _ingest_pdfs(
    files: List[gr.File],
    target_chars: int,
    overlap_chars: int,
    title_hint: str,
    std_choice: str,
    manual_tags_csv: str,
    force_hint: bool,
    doc_type: str,
    extra_meta_json: str,
    split_within_page: bool,
    persist_after: bool,
    skip_duplicates: bool,
    auto_doc_type: bool,
) -> Tuple[str, None]:
    """
    Returns (status_markdown, None) so the File component gets cleared after ingest.
    """
    if not files:
        return "No files selected.", None

    chosen_hint = None if not std_choice or std_choice == "(Any)" else std_choice
    manual_tags = [t.strip() for t in (manual_tags_csv or "").split(",") if t.strip()]
    total_chunks = 0
    lines = []

    # parse extra metadata (optional)
    extra_meta: Dict[str, Any] = {}
    if (extra_meta_json or "").strip():
        try:
            extra_meta = json.loads(extra_meta_json)
            if not isinstance(extra_meta, dict):
                return "Additional metadata must be a JSON object.", None
        except Exception as e:
            return f"Additional metadata JSON error: {e}", None

    for f in files:
        path = f.name if hasattr(f, "name") else str(f)
        base_name = os.path.basename(path)
        source = f"file://{path}"

        # compute sha1 to detect duplicates
        try:
            sha1 = _sha1_file(path)
        except Exception:
            sha1 = ""

        # duplicate guard
        if skip_duplicates and _already_ingested(source, sha1):
            lines.append(f"• {base_name} — skipped (already ingested)")
            continue

        detected_standard = detect_standard_from_filename(path) or None
        use_standard = chosen_hint if (force_hint or not detected_standard) else detected_standard

        # per-file doc_type auto-detect (prevents catalogs being marked COMPANY by accident)
        doc_type_for_file = doc_type
        if auto_doc_type and detected_standard:
            doc_type_for_file = "STANDARD"

        # merge per-file metadata add-ons
        per_file_meta = dict(extra_meta)
        per_file_meta.setdefault("original_filename", base_name)
        per_file_meta.setdefault("source", source)  # ensure source is set
        if sha1:
            per_file_meta.setdefault("file_sha1", sha1)

        chunks = chunk_pdf_file(
            path,
            title_hint=title_hint.strip() or None,
            standard_hint=use_standard,
            manual_tags=manual_tags,
            doc_type=doc_type_for_file,
            extra_metadata=per_file_meta,
            target_chars=int(target_chars),
            overlap_chars=int(overlap_chars),
            split_within_page=bool(split_within_page),
        )
        for ch in chunks:
            obj = {"title": ch.title, "text": ch.text, "metadata": json.dumps(ch.metadata)}
            rag.store.upsert_evidence(obj)
        total_chunks += len(chunks)
        label = (use_standard or "(auto: none)") + f" • {doc_type_for_file}"
        lines.append(f"• {base_name} [{label}] → {len(chunks)} chunks")

    if persist_after and hasattr(rag.store, "save_to_disk"):
        try:
            msg = rag.store.save_to_disk()
            lines.append("\n" + msg)
        except Exception as e:
            lines.append(f"\nSave error: {e}")

    lines.append(f"\nTotal chunks ingested: {total_chunks}")

    # Clear the file input after ingest
    return "\n".join(lines), None

def _bootstrap_classes():
    if hasattr(rag.store, "ensure_schema"):
        rag.store.ensure_schema()
        return "Schema ensured ✅"
    return "Using in-memory backend; nothing to bootstrap."

# ---------- UI ----------

with gr.Blocks(title="Compliance Copilot") as demo:
    gr.Markdown("# 🧭 Compliance Copilot")

    # ---------------- Ask ----------------
    with gr.Tab("Ask"):
        question = gr.Textbox(
            label="Question",
            placeholder="Which SOC 2 criteria relate to least privilege? Provide short narratives and cite.",
        )
        with gr.Row():
            frameworks = gr.Textbox(label="Frameworks (comma separated)", placeholder="SOC2, ISO27001")
            std_choice = gr.Dropdown(choices=STANDARD_CHOICES, value="(Any)", label="Standard")
        with gr.Row():
            tags_csv = gr.Textbox(
                label="Tags (comma separated, highest weight)",
                placeholder="CC6.1, CC6.2, least privilege, MFA",
            )
            strict_standard = gr.Checkbox(value=True, label="Restrict to selected Standard")
            include_company = gr.Checkbox(value=False, label="Include company evidence")
        with gr.Row():
            gap_aware = gr.Checkbox(value=True, label="Gap-aware suggestions")
            require_company = gr.Checkbox(value=False, label="Require company evidence (fail-fast)")
        limit = gr.Slider(1, 20, value=8, step=1, label="Result limit")
        ask_btn = gr.Button("Ask")
        answer = gr.Markdown(label="Answer")
        citations = gr.Textbox(label="Citations", interactive=False, lines=8)
        ask_btn.click(
            fn=_ask,
            inputs=[question, frameworks, limit, std_choice, tags_csv, strict_standard, include_company, gap_aware, require_company],
            outputs=[answer, citations],
        )

    # ---------------- Ingest Policy (manual) ----------------
    with gr.Tab("Ingest Policy"):
        p_title = gr.Textbox(label="Title")
        p_framework = gr.Textbox(label="Framework", placeholder="SOC2")
        p_control_ids = gr.Textbox(label="Control IDs (CSV)", placeholder="CC6.1, CC6.2")
        p_text = gr.Textbox(label="Policy Text", lines=8)
        p_meta = gr.Textbox(label="Metadata (JSON)", placeholder='{"owner":"security"}', lines=3)
        p_btn = gr.Button("Ingest Policy")
        p_status = gr.Markdown()
        p_btn.click(fn=_ingest_policy, inputs=[p_title, p_framework, p_control_ids, p_text, p_meta], outputs=p_status)

    # ---------------- Upload PDFs ----------------
    with gr.Tab("Upload PDFs"):
        gr.Markdown(
            "Upload PDFs; we’ll extract, auto-tag, store manual tags, and ingest with page metadata. "
            "Use **Doc type** to distinguish standard vs company docs."
        )
        pdf_files = gr.File(label="PDFs", file_types=[".pdf"], file_count="multiple")
        with gr.Row():
            chunk_chars = gr.Number(value=400, precision=0, label="Target chunk size (chars)")
            overlap_chars = gr.Number(value=100, precision=0, label="Overlap (chars)")
        with gr.Row():
            title_hint = gr.Textbox(label="Optional title hint (prefix for chunk titles)")
            std_choice_up = gr.Dropdown(choices=STANDARD_CHOICES, value="(Any)", label="Standard hint (fallback)")
        with gr.Row():
            doc_type = gr.Dropdown(choices=DOC_TYPE_CHOICES, value="STANDARD", label="Doc type (affects metadata)")
            force_hint = gr.Checkbox(value=False, label="Force the Standard hint for ALL files in this batch")
            split_within_page = gr.Checkbox(value=True, label="Split within page when long")
        manual_tags_csv = gr.Textbox(
            label="Manual tags (comma separated; highest weight)",
            placeholder="CC6.1, CC6.2, access provisioning, privileged access, MFA",
        )
        extra_meta_json = gr.Textbox(
            label="Additional metadata (JSON, optional)",
            lines=6,
            placeholder='{\n  "owner": "Security",\n  "policy_id": "AC-Policy-2024"\n}',
        )
        persist_after = gr.Checkbox(value=True, label="Persist after ingest (save to disk)")
        skip_duplicates = gr.Checkbox(value=True, label="Skip files already ingested (by filename or hash)")
        auto_doc_type = gr.Checkbox(value=True, label="Auto-detect doc type per file (recommended)")
        pdf_btn = gr.Button("Ingest PDFs")
        pdf_status = gr.Markdown()
        # IMPORTANT: outputs include the File component to clear it (return None)
        pdf_btn.click(
            fn=_ingest_pdfs,
            inputs=[
                pdf_files,
                chunk_chars,
                overlap_chars,
                title_hint,
                std_choice_up,
                manual_tags_csv,
                force_hint,
                doc_type,
                extra_meta_json,
                split_within_page,
                persist_after,
                skip_duplicates,
                auto_doc_type,
            ],
            outputs=[pdf_status, pdf_files],
        )

    # ---------------- Admin ----------------
    with gr.Tab("Admin"):
        gr.Markdown(f"**Backend**: `{BACKEND}` (set in `.env` as `STORE_BACKEND=`)")
        with gr.Row():
            boot_btn = gr.Button("Ensure Schema");  boot_status = gr.Markdown()
        with gr.Row():
            status_btn = gr.Button("Show runtime status"); status_md = gr.Markdown()
        with gr.Row():
            snapshot_btn = gr.Button("Show standards snapshot"); snapshot_md = gr.Markdown()
        with gr.Row():
            save_btn = gr.Button("Save now"); save_md = gr.Markdown()
            load_btn = gr.Button("Load from disk"); load_md = gr.Markdown()
        with gr.Row():
            list_btn = gr.Button("List evidence sources"); list_md = gr.Markdown()
        with gr.Row():
            del_src = gr.Textbox(label="Delete by source (substring of metadata.source / filename)")
            del_btn = gr.Button("Delete evidence by source"); del_md = gr.Markdown()
        with gr.Row():
            llm_btn = gr.Button("Test LLM connectivity"); llm_md = gr.Markdown()
        with gr.Row():
            reset_btn = gr.Button("Reset in-memory store"); reset_md = gr.Markdown()
        boot_btn.click(fn=_bootstrap_classes, outputs=boot_status)
        status_btn.click(fn=_status, outputs=status_md)
        snapshot_btn.click(fn=_standards_snapshot, outputs=snapshot_md)
        save_btn.click(fn=_save_now, outputs=save_md)
        load_btn.click(fn=_load_now, outputs=load_md)
        list_btn.click(fn=_list_sources, outputs=list_md)
        del_btn.click(fn=_delete_by_source, inputs=del_src, outputs=del_md)
        llm_btn.click(fn=_llm_health, outputs=llm_md)
        reset_btn.click(fn=_reset_memory, outputs=reset_md)

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7867, share=False)
