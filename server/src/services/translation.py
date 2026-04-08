import time
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.database import UsageLog, MonthlyUsage, User
from ..models.schemas import TranslateResponse
from .ollama_service import ollama_service

logger = logging.getLogger(__name__)

# Unicode ranges for basic language detection
_ARABIC_RANGE = (0x0600, 0x06FF)
_HEBREW_RANGE = (0x0590, 0x05FF)
_CJK_RANGE = (0x4E00, 0x9FFF)
_CYRILLIC_RANGE = (0x0400, 0x04FF)
_LATIN_RANGE = (0x0041, 0x024F)


def _current_year_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


def detect_language(text: str) -> str:
    """Simple heuristic language detection based on Unicode ranges."""
    if not text:
        return "unknown"

    counts = {
        "ar": 0, "he": 0, "zh": 0, "ru": 0, "en": 0
    }
    for ch in text:
        cp = ord(ch)
        if _ARABIC_RANGE[0] <= cp <= _ARABIC_RANGE[1]:
            counts["ar"] += 1
        elif _HEBREW_RANGE[0] <= cp <= _HEBREW_RANGE[1]:
            counts["he"] += 1
        elif _CJK_RANGE[0] <= cp <= _CJK_RANGE[1]:
            counts["zh"] += 1
        elif _CYRILLIC_RANGE[0] <= cp <= _CYRILLIC_RANGE[1]:
            counts["ru"] += 1
        elif _LATIN_RANGE[0] <= cp <= _LATIN_RANGE[1]:
            counts["en"] += 1

    best = max(counts, key=lambda k: counts[k])
    return best if counts[best] > 0 else "en"


async def _upsert_monthly_usage(
    db: AsyncSession,
    user_id: int,
    input_tokens: int,
    output_tokens: int,
) -> None:
    ym = _current_year_month()
    result = await db.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.year_month == ym,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        record = MonthlyUsage(
            user_id=user_id,
            year_month=ym,
            total_input_tokens=input_tokens,
            total_output_tokens=output_tokens,
            total_requests=1,
        )
        db.add(record)
    else:
        record.total_input_tokens += input_tokens
        record.total_output_tokens += output_tokens
        record.total_requests += 1
        db.add(record)


async def translate_text(
    text: str,
    source: str,
    target: str,
    db: AsyncSession,
    api_key_id: int,
    user_id: int,
    endpoint: str = "/api/v1/translate",
) -> TranslateResponse:
    start_ms = time.monotonic() * 1000

    translation, input_tokens, output_tokens = await ollama_service.translate(
        text=text,
        source_lang=source,
        target_lang=target,
    )

    elapsed_ms = time.monotonic() * 1000 - start_ms

    detected_lang = source if source != "auto" else detect_language(text)

    # --- Persist usage log ---
    log = UsageLog(
        api_key_id=api_key_id,
        user_id=user_id,
        timestamp=datetime.utcnow(),
        source_language=detected_lang,
        target_language=target,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        processing_time_ms=elapsed_ms,
        endpoint=endpoint,
    )
    db.add(log)

    # --- Upsert monthly usage ---
    await _upsert_monthly_usage(db, user_id, input_tokens, output_tokens)

    # --- Update user monthly counter ---
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        user.tokens_used_this_month += input_tokens + output_tokens
        db.add(user)

    return TranslateResponse(
        translation=translation,
        source_language_detected=detected_lang,
        tokens_used=input_tokens + output_tokens,
        processing_time_ms=round(elapsed_ms, 2),
    )
