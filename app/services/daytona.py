import httpx
from typing import Dict, Any
from app.config import settings

class DaytonaRunner:
    def __init__(self):
        self.base = settings.DAYTONA_API_BASE.rstrip("/")
        self.token = settings.DAYTONA_API_TOKEN

    async def run_job(self, name: str, image: str, command: str, env: Dict[str,str]) -> Dict[str,Any]:
        headers = {"Authorization": f"Bearer {self.token}"}
        payload = {"name": name, "image": image, "command": command, "env": env}
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(f"{self.base}/jobs", headers=headers, json=payload)
            r.raise_for_status()
            return r.json()
