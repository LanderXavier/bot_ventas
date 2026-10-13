import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "")
    meta_verify_token: str = os.getenv("META_VERIFY_TOKEN", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    input_provider: str = os.getenv("INPUT_PROVIDER", "telegram")
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini")
    llm_model: str = os.getenv("LLM_MODEL", "gemini-3.8-flash")
    openrouter_api_key: str = os.getenv("OPENROUTER_API_KEY", "")
    openrouter_model: str = os.getenv("OPENROUTER_MODEL", "openrouter/free")
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    groq_model: str = os.getenv("GROQ_MODEL", "qwen/qwen3.8-27b")
    draft_ttl_minutes: int = int(os.getenv("DRAFT_TTL_MINUTES", "15"))

settings = Settings()
