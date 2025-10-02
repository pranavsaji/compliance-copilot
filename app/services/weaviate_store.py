import weaviate
from typing import List, Dict, Any
from pydantic import BaseModel
from app.models.schemas import IngestItem
from app.config import settings

class WeaviateStore:
    def __init__(self):
        self.client = weaviate.Client(
            url=settings.WEAVIATE_URL,
            additional_headers={{"X-OpenAI-Api-Key": settings.WEAVIATE_API_KEY}} if settings.WEAVIATE_API_KEY else {{}}
        )

    def ensure_schema(self):
        schema = self.client.schema.get()
        classes = {{c["class"] for c in schema.get("classes", [])}}

        def mk_class(name: str):
            if name in classes: return
            self.client.schema.create_class({
                "class": name,
                "vectorizer": "text2vec-transformers",
                "properties": [
                    {{"name": "title", "dataType": ["text"]}},
                    {{"name": "framework", "dataType": ["text"]}},
                    {{"name": "control_ids", "dataType": ["text[]"]}},
                    {{"name": "text", "dataType": ["text"]}},
                    {{"name": "metadata", "dataType": ["text"]}},
                ]
            })

        mk_class("PolicyDoc")
        mk_class("EvidenceDoc")

    def upsert_policy(self, item: IngestItem):
        self.client.data_object.create(
            data_object={{
                "title": item.title, "framework": item.framework or "",
                "control_ids": item.control_ids, "text": item.text,
                "metadata": str(item.metadata)
            }},
            class_name="PolicyDoc",
            uuid=item.id
        )

    def upsert_evidence(self, item: IngestItem):
        self.client.data_object.create(
            data_object={{
                "title": item.title, "framework": item.framework or "",
                "control_ids": item.control_ids, "text": item.text,
                "metadata": str(item.metadata)
            }},
            class_name="EvidenceDoc",
            uuid=item.id
        )

    def search(self, query: str, limit: int = 8) -> List[Dict[str, Any]]:
        res = self.client.query.get(
            "PolicyDoc", ["title", "framework", "control_ids", "text", "metadata", "_additional {{score id}}"]
        ).with_near_text({{"concepts": [query]}}).with_limit(limit).do()
        hits = res.get("data", {{}}).get("Get", {{}}).get("PolicyDoc", [])
        return hits