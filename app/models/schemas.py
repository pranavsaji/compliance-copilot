from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class IngestItem(BaseModel):
    id: str
    title: str
    framework: Optional[str] = None  # SOC2, ISO27001, HIPAA, PCI, GDPR
    control_ids: List[str] = []
    text: str
    metadata: Dict[str, Any] = {}

class AskRequest(BaseModel):
    question: str
    frameworks: Optional[List[str]] = None
    force_live_checks: bool = False
    crosswalk: bool = True
    max_ctx: int = 8

class AskResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]] = []
    evidence_package_path: Optional[str] = None
    readiness_score: Optional[float] = None
    gaps: List[str] = []

class EvidenceBundleRequest(BaseModel):
    topic: str  # e.g., "encryption Q4"
    include_logs: bool = True
    include_policies: bool = True
    include_tickets: bool = True