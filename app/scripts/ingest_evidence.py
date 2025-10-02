import uuid, glob
from app.models.schemas import IngestItem
from app.services.weaviate_store import WeaviateStore

def run(evidence_glob="data/evidence/*.txt"):
    store = WeaviateStore(); store.ensure_schema()
    for f in glob.glob(evidence_glob):
        text = open(f).read()
        item = IngestItem(
            id=str(uuid.uuid4()),
            title=f.split("/")[-1],
            framework=None,
            control_ids=[],
            text=text,
            metadata={"path": f}
        )
        store.upsert_evidence(item)
    print("Done.")

if __name__ == "__main__":
    run()
    