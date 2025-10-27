# app/config.py
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_ENV: str = "dev"

    # Store backend
    STORE_BACKEND: str = "memory"  # or "weaviate"
    WEAVIATE_URL: str = "http://localhost:8081"

    # LLM provider & keys
    LLM_PROVIDER: str = "stub"      # "groq", "openai", "friendli", or "stub"

    # Groq (OpenAI-compatible)
    GROQ_API_BASE: str = "https://api.groq.com/openai/v1"
    GROQ_API_KEY: str | None = None
    GROQ_MODEL: str = "llama-3.1-70b-versatile"  # or llama-3.1-8b-instant

    # OpenAI (optional)
    OPENAI_API_BASE: str = "https://api.openai.com/v1"
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Friendli (optional)
    FRIENDLIAI_API_BASE: str | None = None
    FRIENDLIAI_API_KEY: str | None = None

    # Other
    BUNDLE_DIR: str = "./data/bundles"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

@lru_cache
def get_settings() -> Settings:
    return Settings()
