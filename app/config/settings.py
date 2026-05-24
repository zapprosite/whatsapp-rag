from __future__ import annotations
from pydantic_settings import BaseSettings
from typing import Literal

class Settings(BaseSettings):
    evolution_api_key: str = ""
    redis_url: str = "redis://192.168.15.83:6379"
    qdrant_url: str = "http://192.168.15.83:6333"
    database_url: str = ""
    llm_model: Literal["mini-max", "MiniMax-Text-01"] = "MiniMax-Text-01"
    llm_api_base: str = "https://api.minimax.chat"
    minimax_api_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
