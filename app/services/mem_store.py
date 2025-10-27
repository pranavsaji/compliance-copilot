# app/services/mem_store.py
from __future__ import annotations
from typing import Dict, Any, List, Optional
import os, json, time
from threading import RLock

def _now_ms() -> int:
    return int(time.time() * 1000)

def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)

def _parse_meta(md: Any) -> Dict[str, Any]:
    if isinstance(md, dict):
        return md
    if isinstance(md, str):
        try:
            return json.loads(md)
        except Exception:
            return {}
    return {}

class MemoryStore:
    """
    Simple in-memory store with disk persistence (JSONL).
    Works with the HybridRetriever that reads arrays directly.
    """

    def __init__(self):
        self.policies: List[Dict[str, Any]] = []
        self.evidence: List[Dict[str, Any]] = []
        self.version: int = 0

        # Persistence folder (configurable via env), default ./data
        self.data_dir = os.getenv("STORE_DATA_DIR", "./data")
        _ensure_dir(self.data_dir)
        self._pol_path = os.path.join(self.data_dir, "policies.jsonl")
        self._evd_path = os.path.join(self.data_dir, "evidence.jsonl")

        self._lock = RLock()
        # Best-effort load on startup
        try:
            self.load_from_disk()
        except Exception:
            # Don't crash app on load errors
            pass

    # ---------- schema-ish ----------
    def ensure_schema(self):
        # NOP for memory; kept for interface parity
        return True

    # ---------- upserts ----------
    def upsert_policy(self, obj: Dict[str, Any]) -> None:
        with self._lock:
            rec = dict(obj)
            if "id" not in rec:
                rec["id"] = f"pol_{_now_ms()}_{len(self.policies)+1}"
            self.policies.append(rec)
            self.version += 1

    def upsert_evidence(self, obj: Dict[str, Any]) -> None:
        with self._lock:
            rec = dict(obj)
            if "id" not in rec:
                rec["id"] = f"evd_{_now_ms()}_{len(self.evidence)+1}"
            self.evidence.append(rec)
            self.version += 1

    # ---------- counts / info ----------
    def counts(self) -> Dict[str, int]:
        return {"policies": len(self.policies), "evidence": len(self.evidence)}

    # ---------- persistence ----------
    def save_to_disk(self) -> str:
        with self._lock:
            _ensure_dir(self.data_dir)
            # Policies
            with open(self._pol_path, "w", encoding="utf-8") as f:
                for rec in self.policies:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            # Evidence
            with open(self._evd_path, "w", encoding="utf-8") as f:
                for rec in self.evidence:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return f"Saved: {len(self.policies)} policies, {len(self.evidence)} evidence → {self.data_dir}"

    def load_from_disk(self) -> str:
        pols: List[Dict[str, Any]] = []
        evds: List[Dict[str, Any]] = []
        if os.path.exists(self._pol_path):
            with open(self._pol_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        pols.append(json.loads(line))
                    except Exception:
                        continue
        if os.path.exists(self._evd_path):
            with open(self._evd_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try:
                        evds.append(json.loads(line))
                    except Exception:
                        continue
        with self._lock:
            self.policies = pols
            self.evidence = evds
            self.version += 1
        return f"Loaded: {len(pols)} policies, {len(evds)} evidence from {self.data_dir}"

    # ---------- listing / deletion ----------
    def list_sources(self) -> List[str]:
        """Return unique evidence 'source' values from metadata."""
        srcs = set()
        for d in self.evidence:
            md = _parse_meta(d.get("metadata"))
            src = md.get("source")
            if isinstance(src, str) and src:
                srcs.add(src)
        # Return sorted for stable UI
        return sorted(srcs)

    def delete_by_source(self, source_substring: str) -> int:
        """
        Remove all evidence where metadata.source contains the given substring (case-insensitive).
        Returns number of removed items.
        """
        if not source_substring:
            return 0
        needle = source_substring.lower().strip()
        with self._lock:
            keep: List[Dict[str, Any]] = []
            removed = 0
            for d in self.evidence:
                md = _parse_meta(d.get("metadata"))
                src = (md.get("source") or "")
                if needle in src.lower():
                    removed += 1
                else:
                    keep.append(d)
            if removed:
                self.evidence = keep
                self.version += 1
            return removed

    # ---------- clear ----------
    def clear_all(self):
        with self._lock:
            self.policies.clear()
            self.evidence.clear()
            self.version += 1
