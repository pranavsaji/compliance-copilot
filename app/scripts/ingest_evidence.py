from pathlib import Path
import json
from app.services.weaviate_store import WeaviateStore

if __name__ == "__main__":
    store = WeaviateStore()
    root = Path("/data/evidence")
    for p in root.glob("*.*"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        obj = {
            "title": p.stem,
            "text": text,
            "metadata": json.dumps({"path": str(p)}),
        }
        store.upsert_evidence(obj)
        print(f"Ingested evidence: {p.name}")
