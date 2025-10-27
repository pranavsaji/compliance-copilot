from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class IngestPolicy(BaseModel):
    id: Optional[str] = None
    title: str
    framework: str
    control_ids: List[str] = Field(default_factory=list)
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class IngestEvidence(BaseModel):
    id: Optional[str] = None
    title: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AskRequest(BaseModel):
    question: str
    frameworks: List[str] = Field(default_factory=list)
    limit: int = 8

class AskResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]] = Field(default_factory=list)
