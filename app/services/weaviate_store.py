# app/services/weaviate_store.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
import weaviate
from app.config import get_settings

# app/services/weaviate_store.py
from app.utils.query import extract_keywords

settings = get_settings()

POLICY_CLASS = "PolicyDoc"
EVIDENCE_CLASS = "EvidenceDoc"

class WeaviateStore:
    def __init__(self):
        self.client = weaviate.Client(url=settings.WEAVIATE_URL)
        self.ensure_schema()

    def ensure_schema(self):
        schema = self.client.schema.get()
        classes = {c["class"] for c in schema.get("classes", [])}

        def mk(cls_name: str, props: List[Dict[str, Any]]):
            if cls_name in classes:
                return
            self.client.schema.create_class({
                "class": cls_name,
                "vectorizer": "none",  # external vectorization off; demo uses LIKE filter
                "properties": props
            })

        mk(POLICY_CLASS, [
            {"name": "title", "dataType": ["text"]},
            {"name": "framework", "dataType": ["text"]},
            {"name": "control_ids", "dataType": ["text[]"]},
            {"name": "text", "dataType": ["text"]},
            {"name": "metadata", "dataType": ["text"]},
        ])
        mk(EVIDENCE_CLASS, [
            {"name": "title", "dataType": ["text"]},
            {"name": "text", "dataType": ["text"]},
            {"name": "metadata", "dataType": ["text"]},
        ])

    def upsert_policy(self, obj: Dict[str, Any], id_: Optional[str] = None):
        return self.client.data_object.create(
            class_name=POLICY_CLASS,
            data_object=obj,
            uuid=id_ if id_ else None
        )

    def upsert_evidence(self, obj: Dict[str, Any], id_: Optional[str] = None):
        return self.client.data_object.create(
            class_name=EVIDENCE_CLASS,
            data_object=obj,
            uuid=id_ if id_ else None
        )

    def _contains(self, hay: str, needle: str) -> bool:
        return (needle or "").lower() in (hay or "").lower()


    def search_policies(self, query: str, limit: int = 8, frameworks: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        toks = extract_keywords(query)
        # Pull a larger candidate set, then filter in Python (simple & robust)
        res = self.client.query.get(
            POLICY_CLASS,
            ["title", "framework", "control_ids", "text", "metadata", "_additional { id }"]
        ).with_limit(max(64, limit)).do()

        docs = res.get("data", {}).get("Get", {}).get(POLICY_CLASS, []) or []
        def match(doc):
            hay = f"{doc.get('title','')} {doc.get('text','')}".lower()
            return any(t in hay for t in toks) if toks else bool(hay.strip())
        docs = [d for d in docs if match(d)]

        if frameworks:
            fset = {f.lower() for f in frameworks}
            docs = [d for d in docs if d.get("framework","").lower() in fset]

        return docs[:limit]

    def search_evidence(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        toks = extract_keywords(query)
        res = self.client.query.get(
            EVIDENCE_CLASS,
            ["title", "text", "metadata", "_additional { id }"]
        ).with_limit(max(64, limit)).do()

        docs = res.get("data", {}).get("Get", {}).get(EVIDENCE_CLASS, []) or []
        def match(doc):
            hay = f"{doc.get('title','')} {doc.get('text','')}".lower()
            return any(t in hay for t in toks) if toks else bool(hay.strip())
        docs = [d for d in docs if match(d)]
        return docs[:limit]

