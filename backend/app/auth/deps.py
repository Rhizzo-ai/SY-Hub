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
from app.auth.tokens import decode_token


@dataclass
class Principal:
    user: User
    tenant_id: uuid.UUID
    token_type: str


def _extract_token(request: Request, authorization: Optional[str]) -> Optional[str]:
    # Prefer Authorization: Bearer <token>; fall back to httpOnly cookie.
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
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
        payload = decode_token(token)
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
    return Principal(user=user, tenant_id=tenant_id, token_type=payload["type"])


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
    /password/change, /logout).
    """
    from app.auth.tokens import decode_token
    import jwt

    token = _extract_token(request, authorization)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
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
    return Principal(user=user, tenant_id=tenant_id, token_type=payload["type"])


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
