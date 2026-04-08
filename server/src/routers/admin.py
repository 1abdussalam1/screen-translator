import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, Query
from fastapi.responses import JSONResponse
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..models.database import Admin, User, APIKey, UsageLog, MonthlyUsage
from ..models.schemas import (
    UserCreate, UserUpdate, UserResponse,
    APIKeyCreate, APIKeyResponse, APIKeyGenerated,
    UsageStats, UsageLogEntry, AdminStats,
)
from .. import config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

_serializer = URLSafeTimedSerializer(config.SECRET_KEY)
_SESSION_COOKIE = "admin_session"
_SESSION_MAX_AGE = config.ADMIN_SESSION_EXPIRE_HOURS * 3600


# ── Session helpers ────────────────────────────────────────────────────────────

def _create_session_token(admin_id: int, username: str) -> str:
    return _serializer.dumps({"id": admin_id, "username": username})


def _verify_session_token(token: str) -> dict:
    try:
        data = _serializer.loads(token, max_age=_SESSION_MAX_AGE)
        return data
    except (BadSignature, SignatureExpired):
        return {}


async def get_current_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Admin:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    data = _verify_session_token(token)
    if not data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    result = await db.execute(select(Admin).where(Admin.id == data["id"]))
    admin = result.scalar_one_or_none()
    if admin is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin not found")
    return admin


# ── Auth ───────────────────────────────────────────────────────────────────────

@router.post("/login")
async def admin_login(request: Request, db: AsyncSession = Depends(get_db)):
    body = await request.json()
    username = body.get("username", "")
    password = body.get("password", "")

    result = await db.execute(select(Admin).where(Admin.username == username))
    admin = result.scalar_one_or_none()

    if admin is None or not bcrypt.checkpw(password.encode(), admin.password_hash.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    admin.last_login = datetime.utcnow()
    db.add(admin)

    token = _create_session_token(admin.id, admin.username)
    resp = JSONResponse({"ok": True, "username": admin.username})
    resp.set_cookie(
        key=_SESSION_COOKIE,
        value=token,
        httponly=True,
        max_age=_SESSION_MAX_AGE,
        samesite="lax",
    )
    return resp


@router.post("/logout")
async def admin_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(_SESSION_COOKIE)
    return resp


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/api/users")
async def list_users(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    result = await db.execute(select(User).offset(skip).limit(limit))
    users = result.scalars().all()
    count_result = await db.execute(select(func.count(User.id)))
    total = count_result.scalar_one()
    return {
        "users": [UserResponse.model_validate(u) for u in users],
        "total": total,
    }


@router.post("/api/users", response_model=UserResponse, status_code=201)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    # Check uniqueness
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    user = User(
        username=body.username,
        email=body.email,
        token_limit=body.token_limit,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserResponse.model_validate(user)


@router.patch("/api/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if body.email is not None:
        user.email = body.email
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.token_limit is not None:
        user.token_limit = body.token_limit

    db.add(user)
    await db.flush()
    await db.refresh(user)
    return UserResponse.model_validate(user)


# ── API Keys ───────────────────────────────────────────────────────────────────

@router.post("/api/keys/generate", response_model=APIKeyGenerated, status_code=201)
async def generate_api_key(
    body: APIKeyCreate,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    # Verify user exists
    result = await db.execute(select(User).where(User.id == body.user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    # Generate: sk- + 32 random hex chars
    raw_key = "sk-" + secrets.token_hex(16)
    key_prefix = raw_key[:8]
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    api_key = APIKey(
        user_id=body.user_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=body.name,
        rate_limit=body.rate_limit,
        is_active=True,
        raw_key=raw_key,
    )
    db.add(api_key)
    await db.flush()
    await db.refresh(api_key)

    return APIKeyGenerated(
        id=api_key.id,
        key=raw_key,  # shown ONCE
        key_prefix=key_prefix,
        name=api_key.name,
        user_id=api_key.user_id,
        created_at=api_key.created_at,
    )


@router.delete("/api/keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    result = await db.execute(select(APIKey).where(APIKey.id == key_id))
    api_key = result.scalar_one_or_none()
    if api_key is None:
        raise HTTPException(status_code=404, detail="API key not found")

    # Hard delete the row
    await db.delete(api_key)


@router.get("/api/keys")
async def list_api_keys(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
    user_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
):
    query = select(APIKey)
    if user_id:
        query = query.where(APIKey.user_id == user_id)
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    keys = result.scalars().all()
    return {"keys": [APIKeyResponse.model_validate(k) for k in keys]}


# ── Usage ─────────────────────────────────────────────────────────────────────

@router.get("/api/usage", response_model=UsageStats)
async def get_usage(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
    user_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
):
    query = select(UsageLog).order_by(UsageLog.timestamp.desc())
    filters = []

    if user_id:
        filters.append(UsageLog.user_id == user_id)
    if start_date:
        try:
            dt = datetime.fromisoformat(start_date)
            filters.append(UsageLog.timestamp >= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid start_date format")
    if end_date:
        try:
            dt = datetime.fromisoformat(end_date)
            filters.append(UsageLog.timestamp <= dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid end_date format")

    if filters:
        query = query.where(and_(*filters))

    count_query = select(func.count(UsageLog.id))
    if filters:
        count_query = count_query.where(and_(*filters))

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return UsageStats(
        logs=[UsageLogEntry.model_validate(l) for l in logs],
        total=total,
    )


# ── Stats ──────────────────────────────────────────────────────────────────────

@router.get("/api/stats", response_model=AdminStats)
async def get_stats(
    db: AsyncSession = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    total_users = (await db.execute(select(func.count(User.id)))).scalar_one()
    active_users = (await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )).scalar_one()
    total_keys = (await db.execute(select(func.count(APIKey.id)))).scalar_one()
    active_keys = (await db.execute(
        select(func.count(APIKey.id)).where(APIKey.is_active == True)
    )).scalar_one()

    requests_today = (await db.execute(
        select(func.count(UsageLog.id)).where(UsageLog.timestamp >= today_start)
    )).scalar_one()

    tokens_today_in = (await db.execute(
        select(func.coalesce(func.sum(UsageLog.input_tokens), 0))
        .where(UsageLog.timestamp >= today_start)
    )).scalar_one()
    tokens_today_out = (await db.execute(
        select(func.coalesce(func.sum(UsageLog.output_tokens), 0))
        .where(UsageLog.timestamp >= today_start)
    )).scalar_one()

    requests_month = (await db.execute(
        select(func.count(UsageLog.id)).where(UsageLog.timestamp >= month_start)
    )).scalar_one()

    tokens_month_in = (await db.execute(
        select(func.coalesce(func.sum(UsageLog.input_tokens), 0))
        .where(UsageLog.timestamp >= month_start)
    )).scalar_one()
    tokens_month_out = (await db.execute(
        select(func.coalesce(func.sum(UsageLog.output_tokens), 0))
        .where(UsageLog.timestamp >= month_start)
    )).scalar_one()

    # Daily requests for last 30 days
    daily_result = await db.execute(
        select(
            func.strftime("%Y-%m-%d", UsageLog.timestamp).label("date"),
            func.count(UsageLog.id).label("count"),
        )
        .where(UsageLog.timestamp >= (today_start - timedelta(days=29)))
        .group_by(func.strftime("%Y-%m-%d", UsageLog.timestamp))
        .order_by("date")
    )
    daily_requests = [{"date": row.date, "count": row.count} for row in daily_result]

    return AdminStats(
        total_users=total_users,
        active_users=active_users,
        total_api_keys=total_keys,
        active_api_keys=active_keys,
        requests_today=requests_today,
        tokens_today=int(tokens_today_in) + int(tokens_today_out),
        requests_this_month=requests_month,
        tokens_this_month=int(tokens_month_in) + int(tokens_month_out),
        daily_requests=daily_requests,
    )
