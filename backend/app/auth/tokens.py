"""JWT access tokens — HS256, 4h lifetime in Prompt 1.2.

Prompt 1.3 will shrink this to 15 min and add refresh tokens + session rows.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal, Optional

import jwt


_ALGO = "HS256"


def _secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        raise RuntimeError("JWT_SECRET is not set in backend/.env")
    return secret


def _hours() -> int:
    return int(os.environ.get("JWT_ACCESS_TOKEN_HOURS", "4"))


def issue_access_token(
    user_id: uuid.UUID,
    email: str,
    tenant_id: uuid.UUID,
    token_type: Literal["access", "mfa_challenge"] = "access",
    lifetime_minutes: Optional[int] = None,
) -> str:
    now = datetime.now(timezone.utc)
    exp = now + (
        timedelta(minutes=lifetime_minutes)
        if lifetime_minutes is not None
        else timedelta(hours=_hours())
    )
    payload = {
        "sub": str(user_id),
        "email": email,
        "tenant_id": str(tenant_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "type": token_type,
    }
    return jwt.encode(payload, _secret(), algorithm=_ALGO)


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=[_ALGO])
