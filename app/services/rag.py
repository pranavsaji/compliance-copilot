from typing import List, Dict, Any
from app.services.weaviate_store import WeaviateStore
from app.services.friendliai import FriendliAIClient
from app.services.comet_logger import CometLogger

class RAGPipeline:
    def __init__(self, store: WeaviateStore, llm: FriendliAIClient, logger: CometLogger):
        self.store = store
        self.llm = llm
        self.logger = logger

    async def answer(self, question: str, frameworks: List[str] | None, max_ctx: int = 8) -> Dict[str, Any]:
        # 1) Retrieve
        retrieved = self.store.search(question, limit=max_ctx)
        contexts = [hit["text"] for hit in retrieved]

        # 2) Generate
        answer = await self.llm.rag_answer(question, contexts)

        # 3) Log to Comet
        self.logger.log_rag(question, retrieved, answer, metrics={"ctx_count": len(contexts)})

        # 4) Build citations
        cits = []
        for h in retrieved:
            addn = h.get("_additional", {})
            cits.append({"id": addn.get("id"), "score": addn.get("score"), "title": h.get("title"), "framework": h.get("framework")})

        return {"answer": answer, "citations": cits}
