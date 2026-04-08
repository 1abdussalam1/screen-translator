from pathlib import Path
from datetime import datetime
import hashlib
import secrets

import bcrypt
from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

# ── Paths ────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).parent.parent
_TEMPLATES_DIR = _BASE / "templates"
_STATIC_DIR = _BASE / "static"

# Import server config + db
import sys
_server_root = Path(__file__).parent.parent.parent / "server"
sys.path.insert(0, str(_server_root.parent))

from server.src import config as server_config
from server.src.db import AsyncSessionLocal
from server.src.models.database import Admin, User, APIKey, UsageLog, MonthlyUsage

_serializer = URLSafeTimedSerializer(server_config.SECRET_KEY)
_SESSION_COOKIE = "admin_session"
_SESSION_MAX_AGE = server_config.ADMIN_SESSION_EXPIRE_HOURS * 3600

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

dashboard_app = FastAPI(title="Screen Translator Dashboard")

if _STATIC_DIR.exists():
    dashboard_app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ── DB dependency ─────────────────────────────────────────────────────────────
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


# ── Auth helpers ──────────────────────────────────────────────────────────────
def get_admin_from_request(request: Request) -> dict | None:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return None
    try:
        return _serializer.loads(token, max_age=_SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def login_required(request: Request):
    admin = get_admin_from_request(request)
    if not admin:
        return None
    return admin


# ── Pages ─────────────────────────────────────────────────────────────────────
@dashboard_app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    admin = get_admin_from_request(request)
    if admin:
        return RedirectResponse(url="/dashboard/", status_code=302)
    return templates.TemplateResponse(
        request=request, name="login.html", context={"error": None}
    )


@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    # Stats
    active_users = (await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )).scalar() or 0

    active_keys = (await db.execute(
        select(func.count(APIKey.id)).where(APIKey.is_active == True)
    )).scalar() or 0

    today = datetime.utcnow().date()
    today_requests = (await db.execute(
        select(func.count(UsageLog.id)).where(
            func.date(UsageLog.timestamp) == today
        )
    )).scalar() or 0

    today_tokens = (await db.execute(
        select(func.coalesce(
            func.sum(UsageLog.input_tokens + UsageLog.output_tokens), 0
        )).where(func.date(UsageLog.timestamp) == today)
    )).scalar() or 0

    # Last 30 days chart data
    chart_data = []
    from sqlalchemy import text
    rows = (await db.execute(text("""
        SELECT date(timestamp) as day, COUNT(*) as cnt
        FROM usage_logs
        WHERE timestamp >= date('now', '-30 days')
        GROUP BY day ORDER BY day
    """))).fetchall()
    chart_labels = [str(r[0]) for r in rows]
    chart_values = [r[1] for r in rows]

    # Recent logs
    recent_logs = (await db.execute(
        select(UsageLog).order_by(desc(UsageLog.timestamp)).limit(10)
    )).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "admin": admin,
            "active_page": "dashboard",
            "active_users": active_users,
            "active_keys": active_keys,
            "today_requests": today_requests,
            "today_tokens": today_tokens,
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "recent_logs": recent_logs,
        }
    )


@dashboard_app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    users = (await db.execute(
        select(User).order_by(desc(User.created_at))
    )).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="users.html",
        context={"admin": admin, "active_page": "users", "users": users}
    )


@dashboard_app.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    keys = (await db.execute(
        select(APIKey, User.username)
        .join(User, APIKey.user_id == User.id)
        .order_by(desc(APIKey.created_at))
    )).all()

    keys_data = [
        {
            "id": k.id,
            "name": k.name,
            "key_prefix": k.key_prefix,
            "raw_key": k.raw_key,
            "username": username,
            "is_active": k.is_active,
            "created_at": k.created_at,
            "last_used_at": k.last_used_at,
        }
        for k, username in keys
    ]

    users = (await db.execute(
        select(User).where(User.is_active == True)
    )).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="api_keys.html",
        context={
            "admin": admin,
            "active_page": "api-keys",
            "keys": keys_data,
            "users": users,
            "new_key": None,
        }
    )


@dashboard_app.get("/usage", response_class=HTMLResponse)
async def usage_page(request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)

    logs = (await db.execute(
        select(UsageLog, User.username)
        .join(User, UsageLog.user_id == User.id)
        .order_by(desc(UsageLog.timestamp))
        .limit(100)
    )).all()

    logs_data = [
        {
            "id": l.id,
            "username": username,
            "timestamp": l.timestamp,
            "source_language": l.source_language,
            "target_language": l.target_language,
            "input_tokens": l.input_tokens,
            "output_tokens": l.output_tokens,
            "processing_time_ms": l.processing_time_ms,
        }
        for l, username in logs
    ]

    users = (await db.execute(select(User))).scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="usage.html",
        context={
            "admin": admin,
            "active_page": "usage",
            "logs": logs_data,
            "users": users,
        }
    )


# ── Admin API endpoints (HTMX/JSON) ──────────────────────────────────────────
@dashboard_app.post("/api/users")
async def create_user(request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    user = User(
        username=data["username"],
        email=data.get("email", ""),
        token_limit=int(data.get("token_limit", 1_000_000)),
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return JSONResponse({"id": user.id, "username": user.username})


@dashboard_app.patch("/api/users/{user_id}")
async def update_user(user_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    user = await db.get(User, user_id)
    if not user:
        return JSONResponse({"error": "Not found"}, status_code=404)

    for field in ("username", "email", "is_active", "token_limit"):
        if field in data:
            setattr(user, field, data[field])

    await db.commit()
    return JSONResponse({"ok": True})


@dashboard_app.post("/api/keys/generate")
async def generate_key(request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    data = await request.json()
    user_id = data.get("user_id")
    name = data.get("name", "API Key")

    raw_key = "sk-" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:8]

    api_key = APIKey(
        user_id=user_id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        name=name,
        is_active=True,
        rate_limit=server_config.RATE_LIMIT_DEFAULT,
        raw_key=raw_key,
    )
    db.add(api_key)
    await db.commit()

    return JSONResponse({"key": raw_key, "prefix": key_prefix, "name": name})


@dashboard_app.delete("/api/keys/{key_id}")
async def delete_key(key_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    from sqlalchemy import delete as sql_delete
    await db.execute(sql_delete(APIKey).where(APIKey.id == key_id))
    await db.commit()
    return Response(status_code=200)  # Empty response — HTMX removes the row


@dashboard_app.get("/api/stats")
async def get_stats(request: Request, db: AsyncSession = Depends(get_db)):
    admin = get_admin_from_request(request)
    if not admin:
        return JSONResponse({"error": "Unauthorized"}, status_code=401)

    total_requests = (await db.execute(select(func.count(UsageLog.id)))).scalar() or 0
    total_tokens = (await db.execute(
        select(func.coalesce(func.sum(UsageLog.input_tokens + UsageLog.output_tokens), 0))
    )).scalar() or 0
    total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0

    return JSONResponse({
        "total_requests": total_requests,
        "total_tokens": total_tokens,
        "total_users": total_users,
    })
