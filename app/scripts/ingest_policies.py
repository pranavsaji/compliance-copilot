import json
from pathlib import Path
from app.services.weaviate_store import WeaviateStore

if __name__ == "__main__":
    store = WeaviateStore()
    root = Path("/data/policies")
    for p in root.glob("*.json"):
        data = json.loads(p.read_text(encoding="utf-8"))
        obj = {
            "title": data["title"],
            "framework": data.get("framework", "GENERIC"),
            "control_ids": data.get("controls", []),
            "text": data.get("text", ""),
            "metadata": json.dumps(data.get("meta", {})),
        }
        store.upsert_policy(obj)
        print(f"Ingested policy: {p.name}")
