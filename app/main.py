from fastapi import FastAPI, HTTPException
from app.models.schemas import IngestItem, AskRequest, AskResponse, EvidenceBundleRequest
from app.orchestrator import build_container

svc = build_container()
app = FastAPI(title="Compliance Copilot 2.0")

@app.post("/ingest/policy")
def ingest_policy(item: IngestItem):
    svc["store"].upsert_policy(item)
    return {"status": "ok", "id": item.id}

@app.post("/ingest/evidence")
def ingest_evidence(item: IngestItem):
    svc["store"].upsert_evidence(item)
    return {"status": "ok", "id": item.id}

@app.post("/ask", response_model=AskResponse)
async def ask(req: AskRequest):
    try:
        res = await svc["agent"].ask(
            question=req.question,
            frameworks=req.frameworks,
            force_live_checks=req.force_live_checks,
            crosswalk=req.crosswalk
        )
        return AskResponse(**res)
    except Exception as e:
        raise HTTPException(500, f"failure: {e}")

@app.post("/evidence/bundle")
def bundle(req: EvidenceBundleRequest):
    # In reality, pull from Weaviate + MCP (Jira tickets, Okta reports, etc.)
    dummy_items = [{"type": "policy", "title": "Encryption Policy", "path": "/policies/encryption.pdf"}]
    path = svc["bundler"].bundle(req.topic, dummy_items)
    return {"bundle_path": path}

@app.get("/audit/simulate/{control}")
def simulate(control: str):
    questions = svc["agent"].audit_simulator(control)
    return {"control": control, "questions": questions}
