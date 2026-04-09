import os
import secrets
import logging

logger = logging.getLogger(__name__)

def _get_secret_key() -> str:
    key = os.environ.get("SECRET_KEY", "")
    if not key:
        key = secrets.token_hex(32)
        logger.warning(
            "SECRET_KEY not set in environment. Generated a random key. "
            "THIS WILL CHANGE ON RESTART — set SECRET_KEY in production!"
        )
    return key

OLLAMA_URL: str = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.environ.get("OLLAMA_MODEL", "aya-expanse:8b")

# LLM Provider: "ollama" or "openrouter"
LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "ollama")
OPENROUTER_API_KEY: str = os.environ.get("OPENROUTER_API_KEY", "")
OPENROUTER_BASE_URL: str = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_MODEL: str = os.environ.get("OPENROUTER_MODEL", "google/gemma-3-1b-it:free")
DATABASE_URL: str = os.environ.get(
    "DATABASE_URL", "sqlite+aiosqlite:///./screen_translator.db"
)
SECRET_KEY: str = _get_secret_key()
ADMIN_SESSION_EXPIRE_HOURS: int = int(
    os.environ.get("ADMIN_SESSION_EXPIRE_HOURS", "24")
)
SERVER_VERSION: str = os.environ.get("SERVER_VERSION", "1.0.0")
RATE_LIMIT_DEFAULT: int = int(os.environ.get("RATE_LIMIT_DEFAULT", "60"))
MAX_TEXT_LENGTH: int = int(os.environ.get("MAX_TEXT_LENGTH", "5000"))
APP_NAME: str = os.environ.get("APP_NAME", "Screen Translator Server")
CORS_ORIGINS: list = os.environ.get("CORS_ORIGINS", "*").split(",")
VERSIONS_FILE: str = os.environ.get(
    "VERSIONS_FILE",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "versions.json"),
)
