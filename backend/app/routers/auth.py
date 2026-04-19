"""Auth router — login, MFA enroll/verify, password change, logout."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant_id
from app.models.user import User
from app.models.rbac import UserRole
from app.auth import (
    Principal,
    compute_effective_permissions,
    get_current_principal,
    get_current_user,
    hash_password,
    is_in_history,
    issue_access_token,
    needs_rehash,
    PASSWORD_HISTORY_SIZE,
    PasswordPolicyError,
    verify_password,
)
from app.auth.mfa import (
    count_unused_backup_codes,
    decrypt_secret,
    encrypt_backup_codes,
    encrypt_secret,
    generate_backup_codes,
    generate_totp_secret,
    totp_qr_png_data_uri,
    verify_totp,
    consume_backup_code,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

MFA_ENFORCED_ROLES = {"super_admin", "director", "finance"}
LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW_MIN = 15
LOCKOUT_DURATIONS_MIN = [15, 30, 60]  # escalating


# ---------- Schemas ----------

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str


class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_challenge_token: Optional[str] = None
    user: Optional[dict] = None


class MfaVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(..., min_length=6, max_length=16)
    use_backup_code: bool = False


class MfaEnrollStartResponse(BaseModel):
    secret: str
    qr_data_uri: str


class MfaEnrollConfirmRequest(BaseModel):
    secret: str
    code: str


class MfaEnrollConfirmResponse(BaseModel):
    backup_codes: list[str]


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


class MeResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: str
    last_name: str
    display_name: Optional[str] = None
    user_type: str
    status: str
    mfa_enabled: bool
    permissions: list[str]
    is_super_admin: bool


# ---------- Helpers ----------

def _serialise_user_public(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "first_name": u.first_name,
        "last_name": u.last_name,
        "display_name": u.display_name or f"{u.first_name} {u.last_name}",
        "user_type": u.user_type,
        "status": u.status,
        "mfa_enabled": u.mfa_enabled,
    }


def _clear_lockout(u: User) -> None:
    u.failed_login_attempts = 0
    u.locked_until = None


def _register_failed_attempt(u: User) -> None:
    u.failed_login_attempts = (u.failed_login_attempts or 0) + 1
    if u.failed_login_attempts >= LOCKOUT_THRESHOLD:
        idx = min(u.lockout_level or 0, len(LOCKOUT_DURATIONS_MIN) - 1)
        minutes = LOCKOUT_DURATIONS_MIN[idx]
        u.locked_until = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        u.lockout_level = (u.lockout_level or 0) + 1
        u.failed_login_attempts = 0


def _is_locked(u: User) -> bool:
    return u.locked_until is not None and u.locked_until > datetime.now(timezone.utc)


def _user_is_mfa_enforced(db: Session, user: User) -> bool:
    rows = db.execute(
        select(UserRole.role_id)
        .where(UserRole.user_id == user.id, UserRole.status == "Active")
    ).all()
    if not rows:
        return False
    from app.models.rbac import Role
    codes = db.scalars(
        select(Role.code).where(Role.id.in_([r[0] for r in rows]))
    ).all()
    return any(c in MFA_ENFORCED_ROLES for c in codes)


# ---------- Endpoints ----------

@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    email = payload.email.strip().lower()
    user = db.scalars(
        select(User).where(User.email == email, User.tenant_id == tenant_id)
    ).first()

    # Constant-ish timing: always run a hash-verify even if user missing.
    if user is None:
        hash_password("decoy-password-for-timing")
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status == "Archived":
        raise HTTPException(status_code=403, detail="Account archived")
    if user.status == "Suspended":
        raise HTTPException(status_code=403, detail="Account suspended")

    if _is_locked(user):
        retry_at = user.locked_until.isoformat() if user.locked_until else "later"
        raise HTTPException(
            status_code=423,
            detail=f"Account temporarily locked. Try again after {retry_at}.",
        )

    if not user.password_hash or not verify_password(payload.password, user.password_hash):
        _register_failed_attempt(user)
        db.commit()
        if _is_locked(user):
            raise HTTPException(
                status_code=423,
                detail="Too many failed attempts; account temporarily locked.",
            )
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Password OK — MFA flow?
    if user.mfa_enabled:
        challenge = issue_access_token(
            user.id, user.email, user.tenant_id,
            token_type="mfa_challenge", lifetime_minutes=5,
        )
        db.commit()
        return LoginResponse(mfa_required=True, mfa_challenge_token=challenge)

    # MFA enforced but not enrolled: permit first login, flag for enrollment.
    _clear_lockout(user)
    user.last_login_at = datetime.now(timezone.utc)

    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        user.password_algorithm = "argon2id"

    token = issue_access_token(user.id, user.email, user.tenant_id)
    db.commit()
    _set_token_cookie(response, token)
    return LoginResponse(access_token=token, user=_serialise_user_public(user))


@router.post("/mfa/verify", response_model=LoginResponse)
def mfa_verify(
    payload: MfaVerifyRequest,
    response: Response,
    db: Session = Depends(get_db),
):
    from app.auth.tokens import decode_token
    import jwt as _jwt

    try:
        claims = decode_token(payload.challenge_token)
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Challenge expired — please log in again")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid challenge token")
    if claims.get("type") != "mfa_challenge":
        raise HTTPException(status_code=401, detail="Invalid challenge token type")

    user = db.get(User, uuid.UUID(claims["sub"]))
    if user is None or not user.mfa_enabled or not user.mfa_secret_encrypted:
        raise HTTPException(status_code=401, detail="MFA not enrolled")

    ok = False
    if payload.use_backup_code:
        verified, updated = consume_backup_code(
            user.mfa_backup_codes_encrypted or "", payload.code
        )
        if verified:
            user.mfa_backup_codes_encrypted = updated
            ok = True
    else:
        secret = decrypt_secret(user.mfa_secret_encrypted)
        ok = verify_totp(secret, payload.code)

    if not ok:
        _register_failed_attempt(user)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    _clear_lockout(user)
    user.last_login_at = datetime.now(timezone.utc)
    token = issue_access_token(user.id, user.email, user.tenant_id)
    db.commit()
    _set_token_cookie(response, token)
    return LoginResponse(access_token=token, user=_serialise_user_public(user))


@router.post("/mfa/enroll/start", response_model=MfaEnrollStartResponse)
def mfa_enroll_start(current: User = Depends(get_current_user)):
    secret = generate_totp_secret()
    return MfaEnrollStartResponse(
        secret=secret,
        qr_data_uri=totp_qr_png_data_uri(secret, current.email),
    )


@router.post("/mfa/enroll/confirm", response_model=MfaEnrollConfirmResponse)
def mfa_enroll_confirm(
    payload: MfaEnrollConfirmRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_totp(payload.secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code — re-scan and try again")
    codes = generate_backup_codes()
    current.mfa_secret_encrypted = encrypt_secret(payload.secret)
    current.mfa_backup_codes_encrypted = encrypt_backup_codes(codes)
    current.mfa_enabled = True
    current.mfa_method = "TOTP"
    current.mfa_enforced_at = datetime.now(timezone.utc)
    db.commit()
    return MfaEnrollConfirmResponse(backup_codes=codes)


@router.post("/mfa/disable", status_code=204)
def mfa_disable(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    current.mfa_enabled = False
    current.mfa_method = None
    current.mfa_secret_encrypted = None
    current.mfa_backup_codes_encrypted = None
    db.commit()


@router.post("/password/change", status_code=204)
def password_change(
    payload: PasswordChangeRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not current.password_hash or not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if is_in_history(payload.new_password, current.password_history or []):
        raise HTTPException(
            status_code=400,
            detail=f"Password cannot match any of your last {PASSWORD_HISTORY_SIZE} passwords",
        )
    try:
        new_hash = hash_password(payload.new_password)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Push current into history (keep last 5)
    hist = list(current.password_history or [])
    hist.append({
        "hash": current.password_hash,
        "algorithm": current.password_algorithm,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    })
    hist = hist[-PASSWORD_HISTORY_SIZE:]

    current.password_hash = new_hash
    current.password_algorithm = "argon2id"
    current.password_history = hist
    current.password_changed_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/logout", status_code=204)
def logout(response: Response):
    response.delete_cookie("access_token", path="/")


@router.get("/me", response_model=MeResponse)
def me(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    perms = compute_effective_permissions(db, principal.user.id, principal.tenant_id)
    u = principal.user
    return MeResponse(
        id=u.id,
        email=u.email,
        first_name=u.first_name,
        last_name=u.last_name,
        display_name=u.display_name or f"{u.first_name} {u.last_name}",
        user_type=u.user_type,
        status=u.status,
        mfa_enabled=u.mfa_enabled,
        permissions=sorted(perms.all_permissions),
        is_super_admin=perms.is_super_admin,
    )


# ---------- Cookie helper ----------

def _set_token_cookie(response: Response, token: str) -> None:
    # httpOnly; not Secure for dev — tighten in 1.3 when sessions land.
    import os
    max_age = int(os.environ.get("JWT_ACCESS_TOKEN_HOURS", "4")) * 3600
    response.set_cookie(
        key="access_token", value=token, httponly=True, secure=False,
        samesite="lax", max_age=max_age, path="/",
    )
