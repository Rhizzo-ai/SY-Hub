"""Session + login-history service — Prompt 1.3 stage 1b.

Handles:
  - Access (15-min JWT with jti) + refresh (opaque, SHA-256 hashed) issuance
  - Session creation, rotation on refresh, replay detection
  - Idle-timeout check (60 min)
  - Revocation with reason
  - Append-only login_history row writes
"""
from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from user_agents import parse as parse_ua

from app.models.sessions import UserSession, UserLoginHistory
from app.services.geolocation import geolocate

log = logging.getLogger("syhomes.sessions")

ACCESS_TOKEN_MINUTES = 15
REFRESH_DAYS_DEFAULT = 30
REFRESH_DAYS_REMEMBER = 90
IDLE_TIMEOUT_MINUTES = 60
LAST_ACTIVE_WRITE_THROTTLE_SECONDS = 60

_ALGO = "HS256"


def _secret() -> str:
    s = os.environ.get("JWT_SECRET")
    if not s:
        raise RuntimeError("JWT_SECRET is not set in backend/.env")
    return s


# --- token primitives ---------------------------------------------------------

def issue_access_jwt(
    user_id: uuid.UUID, email: str, tenant_id: uuid.UUID,
    session_id: uuid.UUID, jti: str,
    lifetime_minutes: int = ACCESS_TOKEN_MINUTES,
    token_type: str = "access",
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "email": email,
        "tenant_id": str(tenant_id),
        "sid": str(session_id),
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=lifetime_minutes)).timestamp()),
        "type": token_type,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def make_refresh_token() -> tuple[str, str]:
    """(raw_token, sha256_hex)."""
    raw = secrets.token_urlsafe(32)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return raw, digest


def hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- session lifecycle --------------------------------------------------------

def _device_name_from_ua(ua: str) -> str:
    try:
        u = parse_ua(ua or "")
        browser = (u.browser.family or "Unknown").strip()
        os_family = (u.os.family or "Unknown").strip()
        if u.is_mobile:
            return f"{browser} on {os_family} (mobile)"[:100]
        if u.is_tablet:
            return f"{browser} on {os_family} (tablet)"[:100]
        return f"{browser} on {os_family}"[:100]
    except Exception:
        return (ua or "Unknown")[:100]


def create_session(
    db: Session, *, user_id: uuid.UUID, email: str, tenant_id: uuid.UUID,
    ip: str, user_agent: str, remember_me: bool = False,
    impersonator_user_id: Optional[uuid.UUID] = None,
) -> tuple[UserSession, str, str]:
    """Creates a session row + returns (session, access_jwt, raw_refresh_token)."""
    now = datetime.now(timezone.utc)
    refresh_days = REFRESH_DAYS_REMEMBER if remember_me else REFRESH_DAYS_DEFAULT
    jti = secrets.token_hex(16)
    raw_refresh, refresh_hash = make_refresh_token()
    geo = geolocate(ip)

    session = UserSession(
        user_id=user_id,
        access_token_jti=jti,
        refresh_token_hash=refresh_hash,
        ip_address=ip or "",
        user_agent=user_agent or "",
        device_name=_device_name_from_ua(user_agent or ""),
        location_country=geo.country,
        location_city=geo.city,
        location_latitude=geo.latitude,
        location_longitude=geo.longitude,
        impersonator_user_id=impersonator_user_id,
        remember_me=remember_me,
        last_active_at=now,
        expires_at=now + timedelta(days=refresh_days),
    )
    db.add(session)
    db.flush()  # assign session.id

    access = issue_access_jwt(user_id, email, tenant_id, session.id, jti)
    return session, access, raw_refresh


def rotate_session(
    db: Session, session: UserSession, *, email: str, tenant_id: uuid.UUID,
    ip: str, user_agent: str,
) -> tuple[str, str]:
    """Rotate the refresh token. The prior hash is stored in
    previous_refresh_token_hash so a subsequent presentation of the old
    token is detectable as a replay. Returns (new_access_jwt, new_raw_refresh).
    """
    now = datetime.now(timezone.utc)
    jti = secrets.token_hex(16)
    raw_refresh, refresh_hash = make_refresh_token()
    session.previous_refresh_token_hash = session.refresh_token_hash
    session.access_token_jti = jti
    session.refresh_token_hash = refresh_hash
    session.last_active_at = now
    if session.remember_me:
        session.expires_at = now + timedelta(days=REFRESH_DAYS_REMEMBER)
    access = issue_access_jwt(session.user_id, email, tenant_id, session.id, jti)
    return access, raw_refresh


def revoke_session(
    db: Session, session: UserSession, reason: str,
    *, when: Optional[datetime] = None,
) -> None:
    if session.revoked_at is not None:
        return
    session.revoked_at = when or datetime.now(timezone.utc)
    session.revoked_reason = reason


def revoke_all_user_sessions(
    db: Session, user_id: uuid.UUID, reason: str,
    *, except_session_id: Optional[uuid.UUID] = None,
) -> int:
    now = datetime.now(timezone.utc)
    q = update(UserSession).where(
        UserSession.user_id == user_id,
        UserSession.revoked_at.is_(None),
    ).values(revoked_at=now, revoked_reason=reason)
    if except_session_id is not None:
        q = q.where(UserSession.id != except_session_id)
    r = db.execute(q)
    return r.rowcount or 0


def touch_session(db: Session, session: UserSession) -> None:
    """Update last_active_at only if >60s stale, to avoid write amplification."""
    now = datetime.now(timezone.utc)
    stale = (now - session.last_active_at).total_seconds() > LAST_ACTIVE_WRITE_THROTTLE_SECONDS
    if stale:
        session.last_active_at = now


def session_is_active(session: UserSession) -> bool:
    now = datetime.now(timezone.utc)
    if session.revoked_at is not None:
        return False
    if session.expires_at is not None and session.expires_at < now:
        return False
    idle_cutoff = now - timedelta(minutes=IDLE_TIMEOUT_MINUTES)
    if session.last_active_at < idle_cutoff:
        return False
    return True


def session_is_idle_expired(session: UserSession) -> bool:
    now = datetime.now(timezone.utc)
    idle_cutoff = now - timedelta(minutes=IDLE_TIMEOUT_MINUTES)
    return session.last_active_at < idle_cutoff


# --- login history ------------------------------------------------------------

def log_event(
    db: Session, *, event_type: str, email_attempted: str,
    ip: str, user_agent: str,
    user_id: Optional[uuid.UUID] = None,
    session_id: Optional[uuid.UUID] = None,
    failure_reason: Optional[str] = None,
    metadata: Optional[dict] = None,
    geo: Optional[object] = None,
) -> UserLoginHistory:
    """Append a row to user_login_history. Never raises."""
    if geo is None:
        geo = geolocate(ip or "")
    row = UserLoginHistory(
        user_id=user_id,
        email_attempted=(email_attempted or "")[:255].lower(),
        event_type=event_type,
        failure_reason=failure_reason,
        ip_address=ip or "",
        user_agent=(user_agent or "")[:8000],
        location_country=getattr(geo, "country", None),
        location_city=getattr(geo, "city", None),
        session_id=session_id,
        metadata_json=metadata or {},
    )
    db.add(row)
    db.flush()
    return row


# --- JWT decode ---------------------------------------------------------------

def decode_access_jwt(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=[_ALGO])
