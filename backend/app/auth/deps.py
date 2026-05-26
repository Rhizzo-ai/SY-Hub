"""FastAPI auth dependencies: get_current_user + require_permission factory."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Optional

import jwt
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.user import User
from app.models.sessions import UserSession
from app.services.sessions import (
    decode_access_jwt,
    revoke_session,
    session_is_idle_expired,
    touch_session,
    log_event,
    IDLE_TIMEOUT_MINUTES,
)


@dataclass
class Principal:
    user: User
    tenant_id: uuid.UUID
    token_type: str
    session: Optional[UserSession] = None


def _extract_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    """Access tokens are read ONLY from the httpOnly `access_token` cookie.

    The previous `Authorization: Bearer <token>` fallback was intentionally
    removed as part of the audit remediation (C1) so that a successful XSS
    can't exfiltrate a bearable token: tokens never touch JS-reachable
    storage. The `authorization` parameter is retained in the signature so
    existing endpoint decorators keep their shape; it is deliberately
    ignored here.
    """
    return request.cookies.get("access_token")


def get_optional_principal(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[Principal]:
    token = _extract_token(request, authorization)
    if not token:
        return None
    try:
        payload = decode_access_jwt(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    try:
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Malformed token")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=401, detail="Tenant mismatch")
    if user.status in ("Suspended", "Archived"):
        raise HTTPException(status_code=403, detail=f"Account {user.status.lower()}")

    # Session-bound tokens (issued by Prompt 1.3+) carry a `sid` claim.
    session = None
    sid_raw = payload.get("sid")
    if sid_raw:
        try:
            sid = uuid.UUID(sid_raw)
        except ValueError:
            raise HTTPException(status_code=401, detail="Malformed session id")
        session = db.get(UserSession, sid)
        if session is None or session.user_id != user_id:
            raise HTTPException(status_code=401, detail="Session not found")
        if session.revoked_at is not None:
            raise HTTPException(status_code=401, detail="Session revoked")
        jti = payload.get("jti")
        if jti and session.access_token_jti != jti:
            # An older access token for this session — a newer one has replaced
            # it via refresh rotation. Treat as unauthenticated.
            raise HTTPException(status_code=401, detail="Session token rotated")
        if session_is_idle_expired(session):
            revoke_session(db, session, "Expiry")
            log_event(
                db, event_type="Session_Revoked",
                email_attempted=user.email, user_id=user.id, session_id=session.id,
                ip=request.client.host if request.client else "",
                user_agent=request.headers.get("user-agent", ""),
                metadata={"reason": "idle_timeout", "idle_minutes": IDLE_TIMEOUT_MINUTES},
            )
            db.commit()
            raise HTTPException(status_code=401, detail="Session idle — please log in again")
        touch_session(db, session)
        db.commit()
    # Stash for audit.py: populated even when session is None (values stay
    # None) so callers can rely on the state attrs existing.
    request.state.current_session_id = session.id if session else None
    request.state.impersonator_user_id = (
        session.impersonator_user_id if session else None
    )
    return Principal(user=user, tenant_id=tenant_id, token_type=payload["type"], session=session)


def get_current_principal(
    principal: Optional[Principal] = Depends(get_optional_principal),
) -> Principal:
    if principal is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return principal


def get_current_user(
    principal: Principal = Depends(get_current_principal),
) -> User:
    return principal.user


def get_current_tenant_id_from_user(
    principal: Principal = Depends(get_current_principal),
) -> uuid.UUID:
    return principal.tenant_id


def get_enrollment_principal(
    request: Request,
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Principal:
    """Like get_current_principal, but also accepts `mfa_pending` tokens.

    Used by endpoints that an enforced-role user must be able to reach while
    they still haven't completed MFA enrolment (e.g. /auth/me, /mfa/enroll/*,
    /logout).

    Does NOT enforce session idle-timeout because mfa_pending tokens aren't
    backed by a user_session row — they're short-lived JWTs (15 min).

    Security-critical account changes (password change, MFA disable,
    backup-code regenerate) are NOT in this list — they moved to
    `get_current_principal` / `get_current_user` in P0.3 and P1.R1 so
    a pre-MFA token cannot perform them.
    """
    token = _extract_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_access_jwt(token)
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("type") not in ("access", "mfa_pending"):
        raise HTTPException(status_code=401, detail="Invalid token type for this endpoint")

    try:
        user_id = uuid.UUID(payload["sub"])
        tenant_id = uuid.UUID(payload["tenant_id"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=401, detail="Malformed token")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if user.tenant_id != tenant_id:
        raise HTTPException(status_code=401, detail="Tenant mismatch")
    if user.status in ("Suspended", "Archived"):
        raise HTTPException(status_code=403, detail=f"Account {user.status.lower()}")

    session = None
    if payload.get("type") == "access":
        sid_raw = payload.get("sid")
        if sid_raw:
            try:
                sid = uuid.UUID(sid_raw)
            except ValueError:
                raise HTTPException(status_code=401, detail="Malformed session id")
            session = db.get(UserSession, sid)
            if session is None or session.user_id != user_id or session.revoked_at is not None:
                raise HTTPException(status_code=401, detail="Session invalid")
            jti = payload.get("jti")
            if jti and session.access_token_jti != jti:
                raise HTTPException(status_code=401, detail="Session token rotated")

    return Principal(user=user, tenant_id=tenant_id, token_type=payload["type"], session=session)


def get_enrollment_user(principal: Principal = Depends(get_enrollment_principal)) -> User:
    return principal.user


# ---------- require_permission factory ----------

def require_permission(*codes: str) -> Callable:
    from app.auth.permissions import compute_effective_permissions

    if not codes:
        raise ValueError("require_permission needs at least one permission code")

    def _dep(
        principal: Principal = Depends(get_current_principal),
        db: Session = Depends(get_db),
    ):
        perms = compute_effective_permissions(
            db, principal.user.id, principal.tenant_id
        )
        missing = [c for c in codes if not perms.has(c)]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission(s): {', '.join(missing)}",
            )
        return perms

    return _dep
