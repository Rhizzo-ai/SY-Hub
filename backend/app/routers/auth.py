"""Auth router — login, MFA enroll/verify, password change, logout."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant_id
from app.models.user import User
from app.models.rbac import Role, UserRole
from app.auth import (
    Principal,
    compute_effective_permissions,
    get_current_principal,
    hash_password,
    is_in_history,
    issue_access_token,
    needs_rehash,
    PASSWORD_HISTORY_SIZE,
    PASSWORD_RULES,
    PasswordPolicyError,
    verify_password,
)
from app.auth.deps import get_enrollment_principal, get_enrollment_user
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
MFA_PENDING_LIFETIME_MINUTES = 15
LOCKOUT_THRESHOLD = 5
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
    mfa_enrollment_required: bool = False
    mfa_pending_token: Optional[str] = None
    enforced_role_name: Optional[str] = None
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
    access_token: Optional[str] = None


class MfaDisableRequest(BaseModel):
    current_password: str = Field(..., min_length=1)


class RegenerateBackupCodesRequest(BaseModel):
    current_password: str = Field(..., min_length=1)
    current_totp: str = Field(..., min_length=6, max_length=16)


class RegenerateBackupCodesResponse(BaseModel):
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
    mfa_method: Optional[str] = None
    mfa_enrollment_required: bool = False
    mfa_backup_codes_remaining: int = 0
    enforced_role_name: Optional[str] = None
    token_type: str = "access"
    permissions: list[str]
    is_super_admin: bool
    password_changed_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None


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


def _most_senior_enforced_role(db: Session, user: User) -> Optional[Role]:
    """Returns the most-senior enforced role the user holds via Active user_roles.

    Seniority uses roles.priority ASC (lower = more senior; super_admin=1).
    """
    role = db.scalars(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            UserRole.status == "Active",
            Role.code.in_(MFA_ENFORCED_ROLES),
        )
        .order_by(Role.priority.asc())
        .limit(1)
    ).first()
    return role


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
        # Use a policy-compliant decoy (new complexity rules would reject
        # a plain lowercase string). Any argon2 hash call takes ~350ms.
        hash_password("Decoy-Password-For-Timing-2026!")
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

    # MFA-enforced role but not enrolled → HARD BLOCK.
    # Issue a short-lived `mfa_pending` token that only permits
    # /auth/me, /auth/mfa/enroll/*, /auth/password/change, /auth/logout.
    enforced_role = _most_senior_enforced_role(db, user)
    if enforced_role is not None:
        _clear_lockout(user)
        pending = issue_access_token(
            user.id, user.email, user.tenant_id,
            token_type="mfa_pending", lifetime_minutes=MFA_PENDING_LIFETIME_MINUTES,
        )
        db.commit()
        return LoginResponse(
            access_token=pending,
            mfa_enrollment_required=True,
            mfa_pending_token=pending,
            enforced_role_name=enforced_role.name,
            user=_serialise_user_public(user),
        )

    # Normal login — no MFA, no enforcement.
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
def mfa_enroll_start(current: User = Depends(get_enrollment_user)):
    # Accessible to both full `access` tokens (user opted in)
    # and `mfa_pending` tokens (enforced-role user completing enrolment).
    secret = generate_totp_secret()
    return MfaEnrollStartResponse(
        secret=secret,
        qr_data_uri=totp_qr_png_data_uri(secret, current.email),
    )


@router.post("/mfa/enroll/confirm", response_model=MfaEnrollConfirmResponse)
def mfa_enroll_confirm(
    payload: MfaEnrollConfirmRequest,
    response: Response,
    principal: Principal = Depends(get_enrollment_principal),
    db: Session = Depends(get_db),
):
    current = principal.user
    if not verify_totp(payload.secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code — re-scan and try again")
    codes = generate_backup_codes()
    current.mfa_secret_encrypted = encrypt_secret(payload.secret)
    current.mfa_backup_codes_encrypted = encrypt_backup_codes(codes)
    current.mfa_enabled = True
    current.mfa_method = "TOTP"
    current.mfa_enrolled_at = datetime.now(timezone.utc)
    current.last_login_at = datetime.now(timezone.utc)

    # If the caller came in on an `mfa_pending` token, promote them to a full
    # access token now that enrolment is complete.
    access_token = None
    if principal.token_type == "mfa_pending":
        access_token = issue_access_token(current.id, current.email, current.tenant_id)
        _set_token_cookie(response, access_token)

    db.commit()
    return MfaEnrollConfirmResponse(backup_codes=codes, access_token=access_token)


@router.post("/mfa/disable", status_code=204)
def mfa_disable(
    payload: MfaDisableRequest,
    current: User = Depends(get_enrollment_user),
    db: Session = Depends(get_db),
):
    # Require password re-auth — a valid session alone is not enough to
    # remove a second factor. Prevents session-hijack MFA stripping.
    if not current.password_hash or not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current.mfa_enabled = False
    current.mfa_method = None
    current.mfa_secret_encrypted = None
    current.mfa_backup_codes_encrypted = None
    current.mfa_enrolled_at = None
    db.commit()


@router.post("/mfa/backup-codes/regenerate", response_model=RegenerateBackupCodesResponse)
def regenerate_backup_codes(
    payload: RegenerateBackupCodesRequest,
    current: User = Depends(get_enrollment_user),
    db: Session = Depends(get_db),
):
    if not current.mfa_enabled or not current.mfa_secret_encrypted:
        raise HTTPException(status_code=400, detail="MFA not enrolled")

    # Require password AND current TOTP — regeneration invalidates all
    # existing backup codes, so we double-gate it.
    if not current.password_hash or not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    secret = decrypt_secret(current.mfa_secret_encrypted)
    if not verify_totp(secret, payload.current_totp.strip()):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")

    codes = generate_backup_codes()
    current.mfa_backup_codes_encrypted = encrypt_backup_codes(codes)
    db.commit()
    return RegenerateBackupCodesResponse(backup_codes=codes)


@router.post("/password/change", status_code=204)
def password_change(
    payload: PasswordChangeRequest,
    current: User = Depends(get_enrollment_user),
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
    # Intentionally unauthenticated: clearing local/cookie token is enough,
    # and this also lets an mfa_pending user cleanly sign out.
    response.delete_cookie("access_token", path="/")


@router.get("/password-policy")
def password_policy():
    """Public — UI pulls the active password rules from here so the list
    never drifts from what the backend actually enforces.
    """
    return {
        "rules": [{"code": code, "label": label} for code, label in PASSWORD_RULES],
        "history_size": PASSWORD_HISTORY_SIZE,
    }


@router.get("/me", response_model=MeResponse)
def me(
    principal: Principal = Depends(get_enrollment_principal),
    db: Session = Depends(get_db),
):
    u = principal.user

    # For mfa_pending tokens we have no permissions yet — return an empty
    # set so the UI knows to gate the shell.
    if principal.token_type == "mfa_pending":
        permissions: list[str] = []
        is_super_admin = False
    else:
        perms = compute_effective_permissions(db, u.id, principal.tenant_id)
        permissions = sorted(perms.all_permissions)
        is_super_admin = perms.is_super_admin

    # Compute enforced role (if any) regardless of token type so the UI can
    # show the "Your role (Director) requires MFA" copy correctly.
    enforced_role = None
    enforcement_required = False
    if not u.mfa_enabled:
        enforced_role = _most_senior_enforced_role(db, u)
        enforcement_required = enforced_role is not None

    backup_remaining = count_unused_backup_codes(u.mfa_backup_codes_encrypted)

    return MeResponse(
        id=u.id,
        email=u.email,
        first_name=u.first_name,
        last_name=u.last_name,
        display_name=u.display_name or f"{u.first_name} {u.last_name}",
        user_type=u.user_type,
        status=u.status,
        mfa_enabled=u.mfa_enabled,
        mfa_method=u.mfa_method,
        mfa_enrollment_required=enforcement_required,
        mfa_backup_codes_remaining=backup_remaining,
        enforced_role_name=enforced_role.name if enforced_role else None,
        token_type=principal.token_type,
        permissions=permissions,
        is_super_admin=is_super_admin,
        password_changed_at=u.password_changed_at,
        last_login_at=u.last_login_at,
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
