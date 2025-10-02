import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    APP_ENV: str = "dev"
    WEAVIATE_URL: str
    WEAVIATE_API_KEY: str | None = None
    FRIENDLIAI_API_BASE: str
    FRIENDLIAI_API_KEY: str
    COMET_API_KEY: str
    COMET_WORKSPACE: str
    COMET_PROJECT: str
    DAYTONA_API_BASE: str
    DAYTONA_API_TOKEN: str
    MCP_SERVER_URL: str
    BUNDLE_DIR: str = "/tmp/bundles"

    class Config:
        env_file = ".env"

settings = Settings()
