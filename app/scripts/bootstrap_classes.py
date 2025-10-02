from app.services.weaviate_store import WeaviateStore
s = WeaviateStore()
s.ensure_schema()
print("Done.")
