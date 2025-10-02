from app.services.weaviate_store import WeaviateStore
from app.services.friendliai import FriendliAIClient
from app.services.comet_logger import CometLogger
from app.services.rag import RAGPipeline
from app.services.mcp_tools import MCPClient
from app.services.daytona import DaytonaRunner
from app.services.evidence_bundler import EvidenceBundler
from app.agents.copilot import ComplianceCopilot
from app.config import settings

def build_container():
    store = WeaviateStore(); store.ensure_schema()
    comet = CometLogger()
    llm = FriendliAIClient()
    rag = RAGPipeline(store, llm, comet)
    mcp = MCPClient(settings.MCP_SERVER_URL)
    daytona = DaytonaRunner()
    bundler = EvidenceBundler(settings.BUNDLE_DIR)
    agent = ComplianceCopilot(rag, mcp, daytona)
    return {"store": store, "comet": comet, "rag": rag, "mcp": mcp, "daytona": daytona, "bundler": bundler, "agent": agent}
