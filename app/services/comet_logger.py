import os
from comet_ml import Experiment
from typing import Dict, Any
from app.config import settings

class CometLogger:
    def __init__(self):
        self.exp = Experiment(
            api_key=settings.COMET_API_KEY,
            project_name=settings.COMET_PROJECT,
            workspace=settings.COMET_WORKSPACE,
            auto_param_logging=True,
            auto_metric_logging=True
        )
        self.exp.set_name("compliance-copilot-run")

    def log_rag(self, question: str, retrieved: Any, answer: str, metrics: Dict[str, float]):
        self.exp.log_text(question, metadata={"type": "question"})
        for i, chunk in enumerate(retrieved):
            self.exp.log_text(chunk.get("text","")[:2000], metadata={"type": "ctx", "rank": i})
        self.exp.log_text(answer, metadata={"type":"answer"})
        for k,v in metrics.items():
            self.exp.log_metric(k, v)

    def log_event(self, name: str, data: Dict[str, Any]):
        self.exp.log_other(name, data)

    def end(self):
        self.exp.end()