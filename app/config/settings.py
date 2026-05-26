from __future__ import annotations
from pydantic_settings import BaseSettings
from typing import Literal
import os


class Settings(BaseSettings):
    evolution_api_key: str = ""
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379")
    qdrant_url: str = os.getenv("QDRANT_URL", "http://localhost:6333")
    database_url: str = os.getenv("DATABASE_URL", "")
    llm_model: Literal["mini-max", "MiniMax-Text-01"] = "MiniMax-Text-01"
    llm_api_base: str = "https://api.minimax.chat"
    minimax_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()