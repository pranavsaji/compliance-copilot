# app/services/llm_client.py
from __future__ import annotations
from typing import List, Optional
import os, json, asyncio, aiohttp

from app.config import get_settings

def _clean(s: Optional[str]) -> str:
    return (s or "").strip().rstrip("/")

class LLMClient:
    def __init__(self) -> None:
        s = get_settings()
        self.provider = (s.LLM_PROVIDER or "stub").strip().lower()

        # Read keys/bases (and trim!)
        self.openai_key = _clean(s.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"))
        self.openai_base = _clean(getattr(s, "OPENAI_API_BASE", "") or os.getenv("OPENAI_API_BASE") or "https://api.openai.com/v1")

        self.groq_key = _clean(s.GROQ_API_KEY or os.getenv("GROQ_API_KEY"))
        self.groq_base = _clean(getattr(s, "GROQ_API_BASE", "") or os.getenv("GROQ_API_BASE") or "https://api.groq.com/openai/v1")

        self.friendli_key = _clean(getattr(s, "FRIENDLIAI_API_KEY", "") or os.getenv("FRIENDLIAI_API_KEY"))
        self.friendli_base = _clean(getattr(s, "FRIENDLIAI_API_BASE", "") or os.getenv("FRIENDLIAI_API_BASE"))

        # Default model choices (tweak to your taste)
        self.openai_model = getattr(s, "OPENAI_MODEL", "gpt-4o-mini")
        self.groq_model   = getattr(s, "GROQ_MODEL", "llama-3.1-70b-versatile")
        self.friendli_model = getattr(s, "FRIENDLIAI_MODEL", "meta/llama-3.1-70b-instruct")

    async def rag_answer(self, question: str, chunks: List[str]) -> str:
        if self.provider == "stub":
            # Deterministic, local-only path for dev/offline
            return self._stub_compose(question, chunks)

        if self.provider == "openai":
            return await self._call_openai(question, chunks)
        if self.provider == "groq":
            return await self._call_groq(question, chunks)
        if self.provider == "friendli":
            return await self._call_friendli(question, chunks)

        # Unknown provider → behave like stub
        return self._stub_compose(question, chunks)

    def _stub_compose(self, question: str, chunks: List[str]) -> str:
        # Tiny, cheap composition to make dev easy
        ctx = "\n\n".join(chunks[:8])
        return f"{question.strip()}\n\n[DEV-STUB ANSWER]\n\nKey context:\n{ctx[:2000]}"

    async def _call_openai(self, question: str, chunks: List[str]) -> str:
        if not self.openai_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        base = self.openai_base
        if not base:
            raise RuntimeError("OPENAI_API_BASE is empty")

        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.openai_key}", "Content-Type": "application/json"}
        system = "You are a precise compliance analyst. Use the provided context. Be concise and cite clearly."
        content = "\n\n".join(chunks[:12])

        body = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Question: {question}\n\nContext:\n{content}"},
            ],
            "temperature": 0.1,
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sess:
                async with sess.post(url, headers=headers, json=body) as r:
                    t = await r.text()
                    if r.status >= 400:
                        raise RuntimeError(f"OpenAI HTTP {r.status}: {t[:500]}")
                    data = json.loads(t)
                    return data["choices"][0]["message"]["content"]
        except OSError as e:
            # This is where your “[Errno 8] nodename …” shows up → make it explicit
            raise RuntimeError(f"Network/DNS error calling OpenAI at {url}: {e}")
        except Exception as e:
            raise RuntimeError(f"OpenAI error: {e}")

    async def _call_groq(self, question: str, chunks: List[str]) -> str:
        if not self.groq_key:
            raise RuntimeError("GROQ_API_KEY not set")
        base = self.groq_base or "https://api.groq.com/openai/v1"
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.groq_key}", "Content-Type": "application/json"}
        system = "You are a precise compliance analyst. Use the provided context. Be concise and cite clearly."
        content = "\n\n".join(chunks[:12])

        body = {
            "model": self.groq_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Question: {question}\n\nContext:\n{content}"},
            ],
            "temperature": 0.1,
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sess:
                async with sess.post(url, headers=headers, json=body) as r:
                    t = await r.text()
                    if r.status >= 400:
                        raise RuntimeError(f"Groq HTTP {r.status}: {t[:500]}")
                    data = json.loads(t)
                    return data["choices"][0]["message"]["content"]
        except OSError as e:
            raise RuntimeError(f"Network/DNS error calling Groq at {url}: {e}")
        except Exception as e:
            raise RuntimeError(f"Groq error: {e}")

    async def _call_friendli(self, question: str, chunks: List[str]) -> str:
        if not self.friendli_key:
            raise RuntimeError("FRIENDLIAI_API_KEY not set")
        base = self.friendli_base
        if not base:
            raise RuntimeError("FRIENDLIAI_API_BASE not set")
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {self.friendli_key}", "Content-Type": "application/json"}
        system = "You are a precise compliance analyst. Use the provided context. Be concise and cite clearly."
        content = "\n\n".join(chunks[:12])

        body = {
            "model": self.friendli_model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": f"Question: {question}\n\nContext:\n{content}"},
            ],
            "temperature": 0.1,
        }
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60)) as sess:
                async with sess.post(url, headers=headers, json=body) as r:
                    t = await r.text()
                    if r.status >= 400:
                        raise RuntimeError(f"Friendli HTTP {r.status}: {t[:500]}")
                    data = json.loads(t)
                    return data["choices"][0]["message"]["content"]
        except OSError as e:
            raise RuntimeError(f"Network/DNS error calling Friendli at {url}: {e}")
        except Exception as e:
            raise RuntimeError(f"Friendli error: {e}")

    async def healthcheck(self) -> str:
        """Quick ping to verify provider/key/base before you run a real question."""
        try:
            if self.provider == "stub":
                return "LLM ok: stub"
            # Tiny no-context call
            return await self.rag_answer("Ping", ["You are healthy."])
        except Exception as e:
            return f"LLM NOT OK ({self.provider}): {e}"
