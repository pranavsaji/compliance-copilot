from app.services.weaviate_store import WeaviateStore

if __name__ == "__main__":
    WeaviateStore()  # ensure_schema() runs in ctor
    print("Weaviate classes ensured.")
