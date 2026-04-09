import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..db import get_db
from ..models.database import APIKey, User
from ..models.schemas import TranslateRequest, TranslateResponse, TranslateImageResponse
from ..middleware.auth import verify_api_key
from ..middleware.rate_limiter import check_rate_limit
from ..services import translation as translation_service
from ..services.token_counter import get_remaining_tokens
from ..services import ocr_service
from .. import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["translate"])


async def _enforce_limits(api_key: APIKey, db: AsyncSession) -> None:
    # Rate limit
    check_rate_limit(api_key.id, api_key.rate_limit)

    # Token limit
    remaining = await get_remaining_tokens(api_key.user_id, db)
    if remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail="Monthly token limit exceeded",
        )


@router.post("/translate", response_model=TranslateResponse)
async def translate(
    body: TranslateRequest,
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_limits(api_key, db)

    if len(body.text) > config.MAX_TEXT_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Text exceeds maximum length of {config.MAX_TEXT_LENGTH} characters",
        )

    try:
        result = await translation_service.translate_text(
            text=body.text,
            source=body.source_language,
            target=body.target_language,
            db=db,
            api_key_id=api_key.id,
            user_id=api_key.user_id,
            endpoint="/api/v1/translate",
            model_override=body.model,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )
    return result


@router.post("/translate/image", response_model=TranslateImageResponse)
async def translate_image(
    image: UploadFile = File(...),
    source_language: str = Form(default="auto"),
    target_language: str = Form(default="ar"),
    api_key: APIKey = Depends(verify_api_key),
    db: AsyncSession = Depends(get_db),
):
    await _enforce_limits(api_key, db)

    image_bytes = await image.read()

    # OCR
    try:
        extracted_text = ocr_service.extract_text(image_bytes)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    if not extracted_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No text could be extracted from the image",
        )

    # Translate
    try:
        result = await translation_service.translate_text(
            text=extracted_text,
            source=source_language,
            target=target_language,
            db=db,
            api_key_id=api_key.id,
            user_id=api_key.user_id,
            endpoint="/api/v1/translate/image",
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )

    return TranslateImageResponse(
        extracted_text=extracted_text,
        translation=result.translation,
        tokens_used=result.tokens_used,
    )
