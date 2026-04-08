from __future__ import annotations
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field


# ── Translation ──────────────────────────────────────────────────────────────

class TranslateRequest(BaseModel):
    text: str = Field(..., max_length=5000)
    source_language: str = Field(default="auto")
    target_language: str = Field(default="ar")


class TranslateResponse(BaseModel):
    translation: str
    source_language_detected: str
    tokens_used: int
    processing_time_ms: float


class TranslateImageResponse(BaseModel):
    extracted_text: str
    translation: str
    tokens_used: int


# ── Auth ─────────────────────────────────────────────────────────────────────

class AuthValidateRequest(BaseModel):
    api_key: str


class AuthValidateResponse(BaseModel):
    valid: bool
    user: Optional[str] = None
    tokens_remaining: Optional[int] = None


# ── Health ───────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    ollama_status: str
    model_loaded: bool
    version: str


# ── Users ────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=100)
    email: Optional[str] = None
    token_limit: int = Field(default=1_000_000, ge=0)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    is_active: Optional[bool] = None
    token_limit: Optional[int] = Field(default=None, ge=0)


class UserResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    created_at: datetime
    is_active: bool
    token_limit: int
    tokens_used_this_month: int

    model_config = {"from_attributes": True}


# ── API Keys ─────────────────────────────────────────────────────────────────

class APIKeyCreate(BaseModel):
    user_id: int
    name: str = Field(default="Default", max_length=100)
    rate_limit: int = Field(default=60, ge=1)


class APIKeyResponse(BaseModel):
    id: int
    user_id: int
    key_prefix: str
    name: str
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool
    rate_limit: int

    model_config = {"from_attributes": True}


class APIKeyGenerated(BaseModel):
    """Returned only once when a key is first generated."""
    id: int
    key: str  # full key — shown once
    key_prefix: str
    name: str
    user_id: int
    created_at: datetime


# ── Usage / Stats ────────────────────────────────────────────────────────────

class UsageLogEntry(BaseModel):
    id: int
    user_id: Optional[int]
    api_key_id: Optional[int]
    timestamp: datetime
    source_language: Optional[str]
    target_language: Optional[str]
    input_tokens: int
    output_tokens: int
    processing_time_ms: float
    endpoint: Optional[str]

    model_config = {"from_attributes": True}


class UsageStats(BaseModel):
    logs: List[UsageLogEntry]
    total: int


class AdminStats(BaseModel):
    total_users: int
    active_users: int
    total_api_keys: int
    active_api_keys: int
    requests_today: int
    tokens_today: int
    requests_this_month: int
    tokens_this_month: int
    daily_requests: List[dict]  # [{date, count}]


# ── Auto-update ───────────────────────────────────────────────────────────────

class UpdateInfo(BaseModel):
    version: str
    download_url: str
    release_notes: str
    released_at: str
    min_version: str = "1.0.0"
