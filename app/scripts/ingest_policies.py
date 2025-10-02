import uuid, json, glob
from app.models.schemas import IngestItem
from app.services.weaviate_store import WeaviateStore

def run(policies_dir="data/policies/*.json"):
    store = WeaviateStore(); store.ensure_schema()
    for f in glob.glob(policies_dir):
        data = json.load(open(f))
        item = IngestItem(
            id=str(uuid.uuid4()),
            title=data["title"],
            framework=data.get("framework"),
            control_ids=data.get("controls", []),
            text=data["text"],
            metadata=data.get("meta", {})
        )
        store.upsert_policy(item)
    print("Ingested.")

if __name__ == "__main__":
    run()
