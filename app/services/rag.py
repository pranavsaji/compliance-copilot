# app/services/rag.py
from __future__ import annotations
from typing import Dict, List, Optional, Any, Tuple
import json

from app.config import get_settings

settings = get_settings()

# Choose store
if settings.STORE_BACKEND.lower() == "memory":
    from app.services.mem_store import MemoryStore as Store
else:
    from app.services.weaviate_store import WeaviateStore as Store

from app.services.llm_client import LLMClient
from app.services.retriever import HybridRetriever


def _parse_meta(d: Dict[str, Any]) -> Dict[str, Any]:
    """Robust metadata loader from dict or JSON string."""
    md = d.get("metadata")
    if isinstance(md, dict):
        return md
    if isinstance(md, str):
        try:
            return json.loads(md)
        except Exception:
            return {}
    return {}


def _std(s: Optional[str]) -> str:
    return (s or "").strip().lower()


# Very small, opinionated hints so the app can ask for *specific* uploads
EVIDENCE_HINTS: Dict[str, Dict[str, List[str]]] = {
    # SOC 2 hints keyed by control anchors we see in tags/questions
    "soc2": {
        "cc6.1": [
            "Access Control Policy",
            "Password / Authentication Standard (IdP/Okta policy)",
            "Privileged Access Standard (PAM/Break-glass)",
            "Network Segmentation/Boundary Standard (optional)",
        ],
        "cc6.2": [
            "Joiner–Mover–Leaver (JML) / Access Provisioning SOP",
            "Termination/Deprovisioning SOP",
            "Quarterly Access Review Procedure",
        ],
        "mfa": [
            "MFA Standard (IdP policy) with coverage matrix",
            "Okta/Azure AD factor policy export (screenshots or JSON)",
        ],
    },
    "pci": {
        "8": [
            "Identification & Authentication Policy",
            "MFA Standard for CDE and remote access",
            "VPN gateway/Firewall admin access MFA configs",
        ]
    },
    "iso27001": {
        "a.9": [
            "Access Control Policy",
            "User access management procedure",
            "Access rights review records",
        ]
    },
    "nist": {
        "ac-2": ["Account management procedure", "Access request/approval tickets"],
        "ia-2": ["MFA Standard / IdP settings"],
    },
}


def _infer_evidence_needs(standard: Optional[str], tags: List[str]) -> List[str]:
    """Return a small, concrete upload checklist based on standard + tags."""
    want = _std(standard)
    key = (
        "soc2"
        if ("soc 2" in want or "soc2" in want or "trust services" in want)
        else "pci"
        if "pci" in want
        else "iso27001"
        if ("iso" in want or "27001" in want)
        else "nist"
    )

    needs: List[str] = []
    low = [t.strip().lower() for t in (tags or [])]
    if key == "soc2":
        if any("cc6.1" in t for t in low):
            needs += EVIDENCE_HINTS["soc2"].get("cc6.1", [])
        if any("cc6.2" in t for t in low):
            needs += EVIDENCE_HINTS["soc2"].get("cc6.2", [])
        if any("mfa" in t for t in low):
            needs += EVIDENCE_HINTS["soc2"].get("mfa", [])
    elif key in EVIDENCE_HINTS:
        for tag, vals in EVIDENCE_HINTS[key].items():
            if any(tag in t for t in low):
                needs += vals

    if not needs:
        needs = [
            "Relevant policy/standard for this topic",
            "Procedure/SOP",
            "Sample tickets or review reports",
            "Configuration screenshots/exports",
        ]

    # Deduplicate (preserve order), cap list
    seen = set()
    out: List[str] = []
    for n in needs:
        k = n.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(n)
    return out[:8]


class RAGService:
    def __init__(self):
        self.store = Store()
        self.retriever = HybridRetriever(self.store)
        # LLMClient should internally read env/provider; it may raise on bad config.
        # We keep a soft guard so we can fallback extractively.
        try:
            self.llm = LLMClient()
            self._llm_init_error: Optional[str] = None
        except Exception as e:
            self.llm = None  # type: ignore
            self._llm_init_error = str(e)

    # --------- internal helpers ---------

    def _partition_evidence(
        self, evidence_hits: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Return (standard_evidence, company_evidence)."""
        std_evd: List[Dict[str, Any]] = []
        comp_evd: List[Dict[str, Any]] = []
        for d in evidence_hits:
            md = _parse_meta(d)
            dtype = (md.get("doc_type") or "").upper()
            if dtype == "COMPANY":
                comp_evd.append(d)
            else:
                std_evd.append(d)
        return std_evd, comp_evd

    async def _extractive_fallback(
        self, question: str, policy_hits: List[Dict[str, Any]], evidence_hits: List[Dict[str, Any]]
    ) -> str:
        """No LLM? Provide a concise extractive summary from retrieved chunks."""
        def take(d: Dict[str, Any]) -> str:
            title = d.get("title", "untitled")
            text = (d.get("text", "") or "").strip()
            md = _parse_meta(d)
            dtype = (md.get("doc_type") or "STANDARD").upper()
            p1 = md.get("page_start", "?")
            p2 = md.get("page_end", "?")
            snippet = text[:350].replace("\n", " ").strip() + ("…" if len(text) > 350 else "")
            return f"- {dtype} • {title} (pp.{p1}-{p2})\n  “{snippet}”"

        std_evd, comp_evd = self._partition_evidence(evidence_hits)

        lines: List[str] = [f"**Question:** {question.strip()}"]
        if policy_hits:
            lines.append("\n**Policies:**")
            lines += [take(p) for p in policy_hits[:2]]

        if std_evd:
            lines.append("\n**SOC 2 (catalog) evidence:**")
            lines += [take(x) for x in std_evd[:3]]

        if comp_evd:
            lines.append("\n**Company evidence:**")
            lines += [take(x) for x in comp_evd[:3]]

        if not (policy_hits or evidence_hits):
            lines.append(
                "\n_No evidence retrieved. Upload the SOC 2 catalog (Doc type=STANDARD) and your policy/SOP PDFs (Doc type=COMPANY), then retry._"
            )
        return "\n".join(lines)

    # --------- public API ---------

    async def answer(
        self,
        question: str,
        frameworks: List[str],
        limit: int = 8,
        standard: Optional[str] = None,
        tags: Optional[List[str]] = None,
        strict_standard: bool = True,
        include_company: bool = False,
        guidance_mode: bool = True,          # enable gap-aware coaching
        hard_require_company: bool = False,  # if True and include_company but no company evidence, fail-fast with helpful ask
    ) -> Dict[str, Any]:
        # Retrieval
        k_policies = max(1, min(4, limit))     # keep policies modest
        k_evidence = max(2, limit)             # pull enough evidence to cite

        policy_hits, evidence_hits = self.retriever.search(
            query=question,
            frameworks=frameworks or None,
            k_policies=k_policies,
            k_evidence=k_evidence,
            standard=standard or None,
            tags=[t.strip() for t in (tags or []) if t.strip()] or None,
            strict_standard=strict_standard,
            include_company=include_company,
        )

        std_evd, comp_evd = self._partition_evidence(evidence_hits)

        # Optional fail-fast if company evidence is required
        if include_company and hard_require_company and not comp_evd:
            needs = _infer_evidence_needs(standard, tags or [])
            msg_lines = [
                f"No **company evidence** found for the selected standard{f' ({standard})' if standard else ''}.",
                "Please upload one or more of:",
                *[f"- {n}" for n in needs],
                "",
                "Tip: Use **Upload PDFs → Doc type = COMPANY**, set the Standard hint, "
                "and include keywords like your control IDs (e.g., CC6.1, CC6.2, MFA).",
            ]
            return {
                "answer": "\n".join(msg_lines),
                "citations": [],
                "debug": {
                    "policy_hits": len(policy_hits),
                    "evidence_hits": len(evidence_hits),
                    "company_evidence": 0,
                    "standard_evidence": len(std_evd),
                },
            }

        # Build RAG context
        context_blocks: List[str] = []
        citations: List[Dict[str, Any]] = []

        # Policies (if any)
        for d in policy_hits:
            context_blocks.append(f"POLICY: {d.get('title','untitled')} [{d.get('framework','')}]")
            context_blocks.append((d.get("text") or "")[:2000])
            citations.append(
                {"type": "policy", "title": d.get("title"), "framework": d.get("framework")}
            )

        # Evidence — standard first, then company (explicit ordering)
        for d in std_evd + comp_evd:
            md = _parse_meta(d)
            doc_label = "company" if (md.get("doc_type") or "").upper() == "COMPANY" else "standard"
            context_blocks.append(f"EVIDENCE ({doc_label}): {d.get('title','untitled')}")
            context_blocks.append((d.get("text") or "")[:2000])
            citations.append({"type": "evidence", "title": d.get("title"), "doc_type": doc_label})

        # Nothing retrieved at all?
        if not context_blocks:
            chosen = f" for standard **{standard}**" if (standard and strict_standard) else ""
            msg = (
                f"No relevant policy/evidence found{chosen}.\n"
                "Ingest a catalog (Doc type=STANDARD) and your company docs (Doc type=COMPANY), then retry."
            )
            return {"answer": msg, "citations": [], "debug": {"policy_hits": 0, "evidence_hits": 0}}

        # Small instruction header to steer the LLM output
        if guidance_mode:
            coach = [
                "INSTRUCTIONS:",
                "- Map SOC 2 catalog text (CC6.1/CC6.2) to exact company clauses; quote short phrases and list page/section if visible.",
                "- If company evidence is partial/missing, answer with what we can from the standard, then add a short 'Next steps' with specific uploads.",
                "- Keep bullets concise; avoid speculation.",
            ]
            context_blocks = ["\n".join(coach)] + context_blocks

        # Generate with LLM; fall back to extractive if LLM is down
        if self.llm is None:
            # LLM failed to initialize
            answer_text = await self._extractive_fallback(question, policy_hits, evidence_hits)
            if self._llm_init_error:
                answer_text = f"_(LLM unavailable: {self._llm_init_error})_\n\n" + answer_text
        else:
            try:
                answer_text = await self.llm.rag_answer(
                    question,
                    context_blocks,
                    # LLMClient can choose sensible defaults (model/temperature) internally.
                )
            except Exception as e:
                # Network/DNS or provider error mid-call — give users something useful
                fallback = await self._extractive_fallback(question, policy_hits, evidence_hits)
                answer_text = f"_(LLM call failed: {e})_\n\n" + fallback

        # Optional tail if user asked to include company evidence but we found none
        if guidance_mode and include_company and len(comp_evd) == 0:
            needs = _infer_evidence_needs(standard, tags or [])
            tail = "\n\n**Next steps (evidence to upload):**\n" + "".join(f"- {n}\n" for n in needs[:6])
            answer_text = (answer_text or "").rstrip() + tail

        return {
            "answer": answer_text,
            "citations": citations,
            "debug": {
                "policy_hits": len(policy_hits),
                "evidence_hits": len(evidence_hits),
                "company_evidence": len(comp_evd),
                "standard_evidence": len(std_evd),
            },
        }
