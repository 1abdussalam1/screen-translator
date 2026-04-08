from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from . import config

# Ensure the URL uses aiosqlite for async SQLite
_db_url = config.DATABASE_URL
if _db_url.startswith("sqlite:///") and "aiosqlite" not in _db_url:
    _db_url = _db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)

engine = create_async_engine(
    _db_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in _db_url else {},
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_all_tables():
    from .models import database  # noqa – import to register models
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # SQLite migration: add raw_key column if not exists
    if "sqlite" in _db_url:
        async with engine.begin() as conn:
            try:
                await conn.execute(
                    __import__("sqlalchemy").text("ALTER TABLE api_keys ADD COLUMN raw_key TEXT")
                )
            except Exception:
                pass  # Column already exists
