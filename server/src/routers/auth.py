import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_db
from ..models.database import APIKey, User
from ..models.schemas import AuthValidateRequest, AuthValidateResponse, HealthResponse
from ..services.ollama_service import ollama_service
from ..services.token_counter import get_remaining_tokens
from .. import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["auth"])


@router.post("/auth/validate", response_model=AuthValidateResponse)
async def validate_key(
    body: AuthValidateRequest,
    db: AsyncSession = Depends(get_db),
):
    key_hash = hashlib.sha256(body.api_key.encode()).hexdigest()
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash)
    )
    api_key = result.scalar_one_or_none()

    if api_key is None or not api_key.is_active:
        return AuthValidateResponse(valid=False)

    # Get user info
    user_result = await db.execute(select(User).where(User.id == api_key.user_id))
    user = user_result.scalar_one_or_none()

    if user is None or not user.is_active:
        return AuthValidateResponse(valid=False)

    remaining = await get_remaining_tokens(api_key.user_id, db)

    return AuthValidateResponse(
        valid=True,
        user=user.username,
        tokens_remaining=remaining,
    )


@router.get("/health", response_model=HealthResponse)
async def health():
    ollama_up = await ollama_service.check_health()
    model_loaded = await ollama_service.is_model_loaded() if ollama_up else False

    return HealthResponse(
        status="ok" if ollama_up else "degraded",
        ollama_status="online" if ollama_up else "offline",
        model_loaded=model_loaded,
        version=config.SERVER_VERSION,
    )


@router.get("/models")
async def list_models():
    """Returns all Ollama models available on this server."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{config.OLLAMA_URL}/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", [])]
            return {
                "models": models,
                "current_model": config.OLLAMA_MODEL,
                "count": len(models),
            }
    except Exception as e:
        logger.error("Failed to fetch models from Ollama: %s", e)
        return {"models": [], "current_model": config.OLLAMA_MODEL, "count": 0}
