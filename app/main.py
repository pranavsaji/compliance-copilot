from fastapi import FastAPI
from fastapi import Body
from fastapi.responses import ORJSONResponse
from app.config import get_settings
from app.models.schemas import IngestPolicy, IngestEvidence, AskRequest, AskResponse
from app.services.weaviate_store import WeaviateStore
from app.services.rag import RAGService
from app.utils.bundles import write_bundle

app = FastAPI(title="Compliance Copilot", default_response_class=ORJSONResponse)
settings = get_settings()
store = WeaviateStore()
rag = RAGService()

@app.get("/healthz")
def healthz():
    return {"ok": True, "env": settings.APP_ENV}

@app.post("/ingest/policy")
def ingest_policy(payload: IngestPolicy):
    obj = {
        "title": payload.title,
        "framework": payload.framework,
        "control_ids": payload.control_ids,
        "text": payload.text,
        "metadata": "{}" if not payload.metadata else str(payload.metadata),
    }
    store.upsert_policy(obj, id_=payload.id)
    return {"status": "ok"}

@app.post("/ingest/evidence")
def ingest_evidence(payload: IngestEvidence):
    obj = {
        "title": payload.title,
        "text": payload.text,
        "metadata": "{}" if not payload.metadata else str(payload.metadata),
    }
    store.upsert_evidence(obj, id_=payload.id)
    return {"status": "ok"}

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    result = await rag.answer(req.question, req.frameworks, req.limit)
    return AskResponse(answer=result["answer"], citations=result["citations"])

@app.post("/evidence/bundle")
def evidence_bundle(topic: str = Body(..., embed=True), content: str = Body("", embed=True)):
    path = write_bundle(settings.BUNDLE_DIR, topic, content or f"Bundle for {topic}")
    return {"status": "ok", "path": path}
