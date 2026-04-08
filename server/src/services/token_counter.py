from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.database import User, MonthlyUsage


def _current_year_month() -> str:
    return datetime.utcnow().strftime("%Y-%m")


async def get_monthly_tokens(user_id: int, db: AsyncSession) -> int:
    ym = _current_year_month()
    result = await db.execute(
        select(MonthlyUsage).where(
            MonthlyUsage.user_id == user_id,
            MonthlyUsage.year_month == ym,
        )
    )
    record = result.scalar_one_or_none()
    if record is None:
        return 0
    return record.total_input_tokens + record.total_output_tokens


async def get_remaining_tokens(user_id: int, db: AsyncSession) -> int:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return 0
    used = await get_monthly_tokens(user_id, db)
    return max(0, user.token_limit - used)
