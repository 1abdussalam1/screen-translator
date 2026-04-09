import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import bcrypt
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import config
from .db import create_all_tables, AsyncSessionLocal
from .models.database import Admin
from .routers import translate, auth, admin
from sqlalchemy import select

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def _ensure_default_admin():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Admin))
        existing = result.scalars().first()
        if existing is None:
            password_hash = bcrypt.hashpw(b"admin123", bcrypt.gensalt()).decode()
            default_admin = Admin(
                username="admin",
                password_hash=password_hash,
            )
            db.add(default_admin)
            await db.commit()
            logger.warning(
                "="*60
            )
            logger.warning(
                "DEFAULT ADMIN CREATED: username=admin password=admin123"
            )
            logger.warning(
                "CHANGE THIS PASSWORD IMMEDIATELY IN PRODUCTION!"
            )
            logger.warning(
                "="*60
            )


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s", config.APP_NAME, config.SERVER_VERSION)
    await create_all_tables()
    await _ensure_default_admin()
    yield
    from .services.ollama_service import ollama_service
    await ollama_service.close()
    logger.info("Server shutdown complete")


app = FastAPI(
    title=config.APP_NAME,
    version=config.SERVER_VERSION,
    description="Screen translation server with Ollama backend",
    lifespan=lifespan,
)

# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = (time.monotonic() - start) * 1000
    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


# ── Exception handlers ─────────────────────────────────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(translate.router)
app.include_router(auth.router)
app.include_router(admin.router)

# ── Dashboard sub-app ─────────────────────────────────────────────────────────
try:
    import sys
    # Try Docker path first (/app/dashboard), then local dev path
    dashboard_path = Path(__file__).parent.parent / "dashboard" / "src"
    if not dashboard_path.exists():
        dashboard_path = Path(__file__).parent.parent.parent / "dashboard" / "src"
    sys.path.insert(0, str(dashboard_path.parent.parent))
    from dashboard.src.main import dashboard_app
    app.mount("/dashboard", dashboard_app)
    logger.info("Dashboard mounted at /dashboard")
except Exception as exc:
    logger.warning("Could not mount dashboard: %s", exc)


# ── Auto-update endpoint ───────────────────────────────────────────────────────
@app.get("/updates/latest")
async def get_latest_version():
    versions_path = Path(config.VERSIONS_FILE)
    if not versions_path.exists():
        return JSONResponse(
            status_code=404,
            content={"detail": "versions.json not found"},
        )
    try:
        with open(versions_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(content=data)
    except Exception as exc:
        logger.error("Failed to read versions.json: %s", exc)
        return JSONResponse(
            status_code=500,
            content={"detail": "Could not read version info"},
        )


@app.get("/")
async def root():
    return {
        "app": config.APP_NAME,
        "version": config.SERVER_VERSION,
        "docs": "/docs",
        "dashboard": "/dashboard",
    }
