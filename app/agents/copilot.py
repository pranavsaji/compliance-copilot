from typing import Dict, Any, List
from app.services.rag import RAGPipeline
from app.services.mcp_tools import MCPClient
from app.services.daytona import DaytonaRunner
from app.agents.crosswalk import map_controls
from app.agents.auditor import probe

class ComplianceCopilot:
    def __init__(self, rag: RAGPipeline, mcp: MCPClient, daytona: DaytonaRunner):
        self.rag = rag
        self.mcp = mcp
        self.daytona = daytona

    async def ask(self, question: str, frameworks: List[str] | None, force_live_checks=False, crosswalk=True):
        rag_ans = await self.rag.answer(question, frameworks, max_ctx=8)

        # Heuristic: if question mentions access reviews or “admin dormant”
        gaps = []
        if force_live_checks or "access review" in question.lower():
            # EXAMPLE Daytona job: run live IAM dormant-admins script (image contains the scanner)
            job = await self.daytona.run_job(
                name="iam-dormant-admins",
                image="ghcr.io/yourorg/iam-checks:latest",
                command="python check_dormant_admins.py --days 90",
                env={}
            )
            rag_ans["answer"] += f"\n\n🔎 Live check kicked: job={job.get('id','N/A')}"

        # ACI.dev MCP examples (Okta admins + Jira evidence tickets)
        try:
            okta_admins = await self.mcp.okta_list_admins()
            if any(a.get("last_login_days", 0) > 90 for a in okta_admins):
                gaps.append("Dormant admin accounts detected (>90 days).")
        except Exception:
            pass

        # Cross-map controls (framework reuse)
        if crosswalk:
            xwalk = map_controls(["SOC2:CC6.2", "SOC2:CC6.1"])  # demo
            rag_ans["answer"] += f"\n\n🔗 Crosswalk: {xwalk}"

        rag_ans["gaps"] = gaps
        # Toy readiness score
        rag_ans["readiness_score"] = 0.85 if not gaps else 0.65
        return rag_ans

    def audit_simulator(self, control: str) -> list[str]:
        return probe(control)
