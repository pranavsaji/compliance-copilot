import os, httpx
from typing import List, Dict, Any
from app.config import settings
# FriendliAI: we assume an OpenAI-compatible endpoint for simplicity
# Swap base URL / headers if you have a native SDK.
class FriendliAIClient:
    def __init__(self):
        self.base = settings.FRIENDLIAI_API_BASE.rstrip("/"
        self.key = settings.FRIENDLIAI_API_KEY

    async def rag_answer(self, prompt: str, context_chunks: List[str], model: str = "gpt-4o-mini"):
        system = "You are a compliance assistant. Be precise, cite sources by their titles."
        ctx = "\n\n".join([f"[CTX {i+1}]\n{c}" for i,c in enumerate(context_chunks)])
        user = f"Question:\n{prompt}\n\nUse only the context when possible.\n{ctx}"

        headers = {{"Authorization": f"Bearer {self.key}"}}
        payload = {
            "model": model,
            "messages": [
                {{"role": "system", "content": system}},
                {{"role": "user", "content": user}}
            ],
            "temperature": 0.1
        }
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(f"{self.base}/chat/completions", headers=headers, json=payload)
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]