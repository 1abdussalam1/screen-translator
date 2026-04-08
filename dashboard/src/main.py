from pathlib import Path
from fastapi import FastAPI, Request, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# ── Paths ────────────────────────────────────────────────────────────────────
_BASE = Path(__file__).parent.parent
_TEMPLATES_DIR = _BASE / "templates"
_STATIC_DIR = _BASE / "static"

# Import server config for SECRET_KEY
import sys
_server_src = Path(__file__).parent.parent.parent / "server" / "src"
sys.path.insert(0, str(_server_src.parent))

from server.src import config as server_config

_serializer = URLSafeTimedSerializer(server_config.SECRET_KEY)
_SESSION_COOKIE = "admin_session"
_SESSION_MAX_AGE = server_config.ADMIN_SESSION_EXPIRE_HOURS * 3600

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

dashboard_app = FastAPI(title="Screen Translator Dashboard")

# Mount static files
if _STATIC_DIR.exists():
    dashboard_app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# ── Auth helper ───────────────────────────────────────────────────────────────
def get_admin_from_request(request: Request) -> dict | None:
    token = request.cookies.get(_SESSION_COOKIE)
    if not token:
        return None
    try:
        data = _serializer.loads(token, max_age=_SESSION_MAX_AGE)
        return data
    except (BadSignature, SignatureExpired):
        return None


def require_admin(request: Request) -> dict:
    admin = get_admin_from_request(request)
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/dashboard/login"},
        )
    return admin


# ── Routes ─────────────────────────────────────────────────────────────────────
@dashboard_app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    admin = get_admin_from_request(request)
    if admin:
        return RedirectResponse(url="/dashboard/", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request})


@dashboard_app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "admin": admin, "active_page": "dashboard"},
    )


@dashboard_app.get("/users", response_class=HTMLResponse)
async def users_page(request: Request):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    return templates.TemplateResponse(
        "users.html",
        {"request": request, "admin": admin, "active_page": "users"},
    )


@dashboard_app.get("/api-keys", response_class=HTMLResponse)
async def api_keys_page(request: Request):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    return templates.TemplateResponse(
        "api_keys.html",
        {"request": request, "admin": admin, "active_page": "api-keys"},
    )


@dashboard_app.get("/usage", response_class=HTMLResponse)
async def usage_page(request: Request):
    admin = get_admin_from_request(request)
    if not admin:
        return RedirectResponse(url="/dashboard/login", status_code=302)
    return templates.TemplateResponse(
        "usage.html",
        {"request": request, "admin": admin, "active_page": "usage"},
    )
