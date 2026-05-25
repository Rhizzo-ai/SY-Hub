"""Auth router — Prompt 1.3 stage 1b.

Login issues session-bound (access + refresh). Short-lived access tokens,
server-side session state for idle timeout + revocation, rotated refresh
tokens, replay detection, login history for every event. Password-reset
flow (self + admin) lives here too — it's still auth-shaped.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant_id
from app.models.user import User
from app.models.rbac import Role, UserRole
from app.models.sessions import UserSession
from app.auth import (
    Principal,
    compute_effective_permissions,
    hash_password,
    is_in_history,
    issue_access_token,
    needs_rehash,
    PASSWORD_HISTORY_SIZE,
    PASSWORD_RULES,
    PasswordPolicyError,
    verify_password,
)
from app.auth.deps import get_enrollment_principal, get_enrollment_user, get_current_principal, get_current_user
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
from app.services.email import send_email
from app.services.email_templates import (
    password_reset_email,
    password_changed_email,
)
from app.services.geolocation import geolocate
from app.services.rate_limit import enforce
from app.services.sessions import (
    ACCESS_TOKEN_MINUTES,
    create_session,
    hash_refresh,
    log_event,
    revoke_all_user_sessions,
    revoke_session,
    rotate_session,
    session_is_active,
)
from app.services.audit import record_audit

log = logging.getLogger("syhomes.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

MFA_ENFORCED_ROLES = {"super_admin", "director", "finance"}
MFA_PENDING_LIFETIME_MINUTES = 15
LOCKOUT_THRESHOLD = 5
LOCKOUT_DURATIONS_MIN = [15, 30, 60]


# ---------- Schemas ----------

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str
    remember_me: bool = False


class LoginResponse(BaseModel):
    """Cookies-only transport: tokens go in Set-Cookie, never the body.

    The body carries the metadata the frontend needs to hydrate
    AuthContext without a follow-up `GET /auth/me`.

    Exception: `mfa_challenge_token` is NOT a session-bearing access token.
    It is a short-lived (5-min) opaque artifact whose sole purpose is to
    identify the half-authenticated flow on the next /mfa/verify call.
    The /mfa/verify endpoint is unauthenticated (no cookie yet) and must
    receive the challenge id in the body — this is standard for MFA
    hand-off and is out of scope for C1 (no access/refresh leak).
    """
    token_type: str = "bearer"
    mfa_required: bool = False
    mfa_challenge_token: Optional[str] = None
    mfa_enrollment_required: bool = False
    enforced_role_name: Optional[str] = None
    user: Optional[dict] = None
    access_token_expires_in: int = ACCESS_TOKEN_MINUTES * 60


class MfaVerifyRequest(BaseModel):
    challenge_token: str
    code: str = Field(..., min_length=6, max_length=16)
    use_backup_code: bool = False
    remember_me: bool = False


class MfaEnrollStartResponse(BaseModel):
    secret: str
    qr_data_uri: str


class MfaEnrollConfirmRequest(BaseModel):
    secret: str
    code: str


class MfaEnrollConfirmResponse(BaseModel):
    """Cookies-only transport: a successful enrolment from a `mfa_pending`
    token sets the full `access_token` + `refresh_token` cookies on the way
    out (see _set_cookies below). The body carries only the backup codes
    and a boolean indicating that a full session was issued — never the
    tokens themselves (audit remediation C1).
    """
    backup_codes: list[str]
    session_issued: bool = False


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


class RefreshRequest(BaseModel):
    """Cookies-only: refresh token is read from the httpOnly cookie.
    Bodies are ignored; kept as an empty model so clients sending a stale
    `{"refresh_token": "..."}` payload don't get a 422 from Pydantic.

    Any extra fields are silently discarded (Pydantic default extra='ignore').
    """
    pass


class RefreshResponse(BaseModel):
    """Cookies-only — kept as an empty model to preserve router shape; the
    real response is `204 No Content` with rotated Set-Cookie headers.
    """
    pass


class PasswordResetRequestPayload(BaseModel):
    email: str = Field(..., max_length=255)


class PasswordResetCompleteRequest(BaseModel):
    token: str
    new_password: str
    mfa_code: Optional[str] = None


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
    current_session_id: Optional[uuid.UUID] = None


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
    """Returns the most-senior MFA-enforced role the user currently holds.

    Must match `compute_effective_permissions` (app/auth/permissions.py) so
    that MFA enforcement never sees a role that the permission resolver would
    treat as expired. Seniority uses roles.priority ASC (lower = more senior).
    """
    from sqlalchemy import or_
    now = datetime.now(timezone.utc)
    return db.scalars(
        select(Role)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(
            UserRole.user_id == user.id,
            UserRole.status == "Active",
            or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
            Role.code.in_(MFA_ENFORCED_ROLES),
        )
        .order_by(Role.priority.asc())
        .limit(1)
    ).first()


def _client_ip(req: Request) -> str:
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else ""


def _ua(req: Request) -> str:
    return req.headers.get("user-agent", "")


def _is_secure_env() -> bool:
    """Secure flag everywhere except the test harness (which runs http)."""
    import os
    return os.environ.get("APP_ENV", "") != "test"


def _set_cookies(response: Response, access: str, refresh: str, remember_me: bool) -> None:
    """Access + refresh cookies, Path=/ on both so nothing breaks if a client
    reads the refresh cookie from a path other than /auth. HttpOnly + SameSite=Lax
    always; Secure off only in APP_ENV=test.
    """
    access_max_age = ACCESS_TOKEN_MINUTES * 60
    refresh_days = 90 if remember_me else 30
    refresh_max_age = refresh_days * 86400
    secure = _is_secure_env()
    response.set_cookie(
        key="access_token", value=access, httponly=True, secure=secure,
        samesite="lax", max_age=access_max_age, path="/",
    )
    response.set_cookie(
        key="refresh_token", value=refresh, httponly=True, secure=secure,
        samesite="lax", max_age=refresh_max_age, path="/",
    )


def _set_pending_cookie(response: Response, pending_token: str) -> None:
    """mfa_pending token travels via the `access_token` cookie so every auth
    dependency keeps using one transport. Short Max-Age matches JWT TTL.
    """
    response.set_cookie(
        key="access_token", value=pending_token, httponly=True,
        secure=_is_secure_env(), samesite="lax",
        max_age=MFA_PENDING_LIFETIME_MINUTES * 60, path="/",
    )
    # Defensive: ensure no stale refresh cookie leaks across an enrolment flow.
    response.delete_cookie("refresh_token", path="/")


def _clear_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    # Legacy path from the pre-remediation release — delete defensively.
    response.delete_cookie("refresh_token", path="/api/auth")


def _rate_429(retry_after: float) -> HTTPException:
    exc = HTTPException(status_code=429, detail="Too many requests — please slow down.")
    exc.headers = {"Retry-After": str(int(retry_after) + 1)}
    return exc


# ---------- Endpoints ----------

@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    email = payload.email.strip().lower()
    ip = _client_ip(request)
    ua = _ua(request)

    ok_ip, retry_ip = enforce("login_per_ip", ip or "unknown")
    ok_email, retry_email = enforce("login_per_email", email or "unknown")
    if not ok_ip or not ok_email:
        log_event(
            db, event_type="Login_Failed", email_attempted=email, ip=ip, user_agent=ua,
            failure_reason="Rate_Limited", metadata={"retry_after": int(max(retry_ip, retry_email)) + 1},
        )
        db.commit()
        raise _rate_429(max(retry_ip, retry_email))

    user = db.scalars(
        select(User).where(User.email == email, User.tenant_id == tenant_id)
    ).first()

    if user is None:
        hash_password("Decoy-Password-For-Timing-2026!")
        log_event(db, event_type="Login_Failed", email_attempted=email, ip=ip,
                  user_agent=ua, failure_reason="Unknown_Email")
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if user.status == "Archived":
        log_event(db, event_type="Login_Failed", email_attempted=email, user_id=user.id,
                  ip=ip, user_agent=ua, failure_reason="Account_Suspended")
        db.commit()
        raise HTTPException(status_code=403, detail="Account archived")
    if user.status == "Suspended":
        log_event(db, event_type="Login_Failed", email_attempted=email, user_id=user.id,
                  ip=ip, user_agent=ua, failure_reason="Account_Suspended")
        db.commit()
        raise HTTPException(status_code=403, detail="Account suspended")

    if _is_locked(user):
        log_event(db, event_type="Login_Failed", email_attempted=email, user_id=user.id,
                  ip=ip, user_agent=ua, failure_reason="Account_Locked")
        db.commit()
        retry_at = user.locked_until.isoformat() if user.locked_until else "later"
        raise HTTPException(status_code=423,
                            detail=f"Account temporarily locked. Try again after {retry_at}.")

    if not user.password_hash or not verify_password(payload.password, user.password_hash):
        _register_failed_attempt(user)
        was_just_locked = _is_locked(user)
        log_event(db, event_type="Login_Failed", email_attempted=email, user_id=user.id,
                  ip=ip, user_agent=ua, failure_reason="Invalid_Password")
        if was_just_locked:
            log_event(db, event_type="Account_Locked", email_attempted=email, user_id=user.id,
                      ip=ip, user_agent=ua,
                      metadata={"locked_until": user.locked_until.isoformat() if user.locked_until else None})
        db.commit()
        if was_just_locked:
            raise HTTPException(status_code=423,
                                detail="Too many failed attempts; account temporarily locked.")
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
    enforced_role = _most_senior_enforced_role(db, user)
    if enforced_role is not None:
        _clear_lockout(user)
        pending = issue_access_token(
            user.id, user.email, user.tenant_id,
            token_type="mfa_pending", lifetime_minutes=MFA_PENDING_LIFETIME_MINUTES,
        )
        db.commit()
        _set_pending_cookie(response, pending)
        return LoginResponse(
            mfa_enrollment_required=True,
            enforced_role_name=enforced_role.name,
            user=_serialise_user_public(user),
        )

    # Normal login — issue session.
    _clear_lockout(user)
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip

    if user.password_hash and needs_rehash(user.password_hash):
        user.password_hash = hash_password(payload.password)
        user.password_algorithm = "argon2id"

    session, access, refresh = create_session(
        db, user_id=user.id, email=user.email, tenant_id=user.tenant_id,
        ip=ip, user_agent=ua, remember_me=payload.remember_me,
    )
    log_event(db, event_type="Login_Success", email_attempted=email, user_id=user.id,
              session_id=session.id, ip=ip, user_agent=ua)
    record_audit(
        db, action="Login", resource_type="users", resource_id=user.id,
        actor_user_id=user.id, session_id=session.id, request=request,
        metadata={"mfa": "none"},
    )
    db.commit()
    _set_cookies(response, access, refresh, payload.remember_me)
    return LoginResponse(user=_serialise_user_public(user))


@router.post("/mfa/verify", response_model=LoginResponse)
def mfa_verify(
    payload: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    import jwt as _jwt
    from app.services.sessions import decode_access_jwt
    ip = _client_ip(request)
    ua = _ua(request)

    try:
        claims = decode_access_jwt(payload.challenge_token)
    except _jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Challenge expired — please log in again")
    except _jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid challenge token")
    if claims.get("type") != "mfa_challenge":
        raise HTTPException(status_code=401, detail="Invalid challenge token type")

    # P0.4 — rate-limit verify attempts per user. Layered on top of
    # per-account lockout. We key on claims["sub"] which is always
    # present by here (the type-check above already confirmed a
    # well-formed mfa_challenge token); malformed/expired tokens have
    # already raised 401 and never consume a bucket slot.
    ok_mfa, retry_mfa = enforce("mfa_verify_per_user", claims["sub"])
    if not ok_mfa:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts — try again shortly",
            headers={"Retry-After": str(int(retry_mfa))},
        )

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
        log_event(db, event_type="MFA_Failed", email_attempted=user.email, user_id=user.id,
                  ip=ip, user_agent=ua, failure_reason="MFA_Invalid")
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid MFA code")

    _clear_lockout(user)
    user.last_login_at = datetime.now(timezone.utc)
    user.last_login_ip = ip

    session, access, refresh = create_session(
        db, user_id=user.id, email=user.email, tenant_id=user.tenant_id,
        ip=ip, user_agent=ua, remember_me=payload.remember_me,
    )
    log_event(db, event_type="MFA_Success", email_attempted=user.email, user_id=user.id,
              session_id=session.id, ip=ip, user_agent=ua)
    log_event(db, event_type="Login_Success", email_attempted=user.email, user_id=user.id,
              session_id=session.id, ip=ip, user_agent=ua,
              metadata={"mfa": "totp" if not payload.use_backup_code else "backup_code"})
    record_audit(
        db, action="Login", resource_type="users", resource_id=user.id,
        actor_user_id=user.id, session_id=session.id, request=request,
        metadata={"mfa": "totp" if not payload.use_backup_code else "backup_code"},
    )
    db.commit()
    _set_cookies(response, access, refresh, payload.remember_me)
    return LoginResponse(user=_serialise_user_public(user))


@router.post("/mfa/enroll/start", response_model=MfaEnrollStartResponse)
def mfa_enroll_start(current: User = Depends(get_enrollment_user)):
    secret = generate_totp_secret()
    return MfaEnrollStartResponse(
        secret=secret,
        qr_data_uri=totp_qr_png_data_uri(secret, current.email),
    )


@router.post("/mfa/enroll/confirm", response_model=MfaEnrollConfirmResponse)
def mfa_enroll_confirm(
    payload: MfaEnrollConfirmRequest,
    request: Request,
    response: Response,
    principal: Principal = Depends(get_enrollment_principal),
    db: Session = Depends(get_db),
):
    current = principal.user
    ip = _client_ip(request)
    ua = _ua(request)
    if not verify_totp(payload.secret, payload.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code — re-scan and try again")
    codes = generate_backup_codes()
    current.mfa_secret_encrypted = encrypt_secret(payload.secret)
    current.mfa_backup_codes_encrypted = encrypt_backup_codes(codes)
    current.mfa_enabled = True
    current.mfa_method = "TOTP"
    current.mfa_enrolled_at = datetime.now(timezone.utc)
    current.last_login_at = datetime.now(timezone.utc)

    log_event(db, event_type="MFA_Enrolled", email_attempted=current.email, user_id=current.id,
              ip=ip, user_agent=ua)
    record_audit(
        db, action="Update", resource_type="users", resource_id=current.id,
        actor_user_id=current.id,
        metadata={"mfa_action": "enrol"},
        request=request,
    )
    # Prompt 1.7 retro-wire: Security_Alert on MFA enrolment.
    try:
        from app.services.notifications import safe_dispatch
        safe_dispatch(
            db,
            recipient_user_id=current.id,
            notification_type="Security_Alert",
            title="Two-factor authentication enabled",
            body=(
                "MFA (TOTP) was enrolled on your account. Keep your backup "
                "codes somewhere safe — they're the only way back in if "
                "you lose your authenticator app."
            ),
            priority="High",
            related_resource_type="users",
            related_resource_id=current.id,
            action_url="/profile/security",
            action_label="View security",
            request=request,
        )
    except Exception:
        pass

    access_token = None
    refresh_token = None
    session_issued = False
    if principal.token_type == "mfa_pending":
        session, access_token, refresh_token = create_session(
            db, user_id=current.id, email=current.email, tenant_id=current.tenant_id,
            ip=ip, user_agent=ua, remember_me=False,
        )
        log_event(db, event_type="Login_Success", email_attempted=current.email,
                  user_id=current.id, session_id=session.id, ip=ip, user_agent=ua,
                  metadata={"via": "mfa_enrolment"})
        _set_cookies(response, access_token, refresh_token, remember_me=False)
        session_issued = True

    db.commit()
    return MfaEnrollConfirmResponse(
        backup_codes=codes, session_issued=session_issued,
    )


@router.post("/mfa/disable", status_code=204)
def mfa_disable(
    payload: MfaDisableRequest,
    request: Request,
    current: User = Depends(get_enrollment_user),
    db: Session = Depends(get_db),
):
    if not current.password_hash or not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    current.mfa_enabled = False
    current.mfa_method = None
    current.mfa_secret_encrypted = None
    current.mfa_backup_codes_encrypted = None
    current.mfa_enrolled_at = None
    log_event(db, event_type="MFA_Disabled", email_attempted=current.email,
              user_id=current.id, ip=_client_ip(request), user_agent=_ua(request))
    record_audit(
        db, action="Update", resource_type="users", resource_id=current.id,
        actor_user_id=current.id,
        metadata={"mfa_action": "disable"},
        request=request,
    )
    # Prompt 1.7 retro-wire: Security_Alert on MFA disable.
    try:
        from app.services.notifications import safe_dispatch
        safe_dispatch(
            db,
            recipient_user_id=current.id,
            notification_type="Security_Alert",
            title="Two-factor authentication disabled",
            body=(
                "MFA was disabled on your account. If this wasn't you, "
                "change your password immediately and re-enable MFA."
            ),
            priority="High",
            related_resource_type="users",
            related_resource_id=current.id,
            action_url="/profile/security",
            action_label="Re-enable MFA",
            request=request,
        )
    except Exception:
        pass
    db.commit()


@router.post("/mfa/backup-codes/regenerate", response_model=RegenerateBackupCodesResponse)
def regenerate_backup_codes(
    payload: RegenerateBackupCodesRequest,
    request: Request,
    current: User = Depends(get_enrollment_user),
    db: Session = Depends(get_db),
):
    if not current.mfa_enabled or not current.mfa_secret_encrypted:
        raise HTTPException(status_code=400, detail="MFA not enrolled")
    if not current.password_hash or not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    secret = decrypt_secret(current.mfa_secret_encrypted)
    if not verify_totp(secret, payload.current_totp.strip()):
        raise HTTPException(status_code=400, detail="Invalid authenticator code")
    codes = generate_backup_codes()
    current.mfa_backup_codes_encrypted = encrypt_backup_codes(codes)
    record_audit(
        db, action="Update", resource_type="users", resource_id=current.id,
        actor_user_id=current.id,
        metadata={"mfa_action": "regenerate"},
        request=request,
    )
    db.commit()
    return RegenerateBackupCodesResponse(backup_codes=codes)


@router.post("/password/change", status_code=204)
def password_change(
    payload: PasswordChangeRequest,
    request: Request,
    # P0.3 — moved from get_enrollment_principal to get_current_principal so
    # an `mfa_pending` token (issued AFTER password, BEFORE MFA enrol) cannot
    # change the password. mfa_pending holders already proved the current
    # password, so the verify_password gate at line 669 doesn't help. Only
    # a fully session-bound `access` token may now reach this endpoint.
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    current = principal.user
    if not current.password_hash or not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    if is_in_history(payload.new_password, current.password_history or []):
        raise HTTPException(status_code=400,
                            detail=f"Password cannot match any of your last {PASSWORD_HISTORY_SIZE} passwords")
    try:
        new_hash = hash_password(payload.new_password)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=422, detail=str(e))

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

    revoke_all_user_sessions(db, current.id, "Password_Change",
                             except_session_id=(principal.session.id if principal.session else None))
    ip = _client_ip(request)
    log_event(db, event_type="Password_Change", email_attempted=current.email,
              user_id=current.id, ip=ip, user_agent=_ua(request))
    record_audit(
        db, action="Update", resource_type="users", resource_id=current.id,
        actor_user_id=current.id,
        field_changes=[{"field": "password_hash", "old": "[REDACTED]", "new": "[REDACTED]"}],
        metadata={"initiator": "self"},
        request=request,
    )

    subj, html, text = password_changed_email(
        recipient_name=current.display_name or current.first_name,
        when=datetime.now(timezone.utc), ip=ip,
    )
    send_email(db, to=current.email, subject=subj, html=html, text=text,
               template_id="password_changed_email")
    db.commit()


@router.post("/refresh", status_code=204)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Rotate refresh token. Reads refresh-token from the httpOnly cookie
    (audit remediation C1 — no body transport). Replay detection: if the
    presented hash matches a session whose refresh was already rotated,
    revoke ALL sessions for the user.
    """
    ip = _client_ip(request)
    ua = _ua(request)
    presented = request.cookies.get("refresh_token")
    if not presented:
        log_event(db, event_type="Refresh_Failed", email_attempted="",
                  ip=ip, user_agent=ua, failure_reason="Refresh_Token_Invalid",
                  metadata={"reason": "no_cookie"})
        db.commit()
        raise HTTPException(status_code=401, detail="Missing refresh cookie")
    presented_hash = hash_refresh(presented)

    # Normal rotation path
    session = db.scalar(
        select(UserSession).where(UserSession.refresh_token_hash == presented_hash)
    )
    if session is None:
        # Replay check: did this hash just get rotated out of an active session?
        replayed = db.scalar(
            select(UserSession).where(
                UserSession.previous_refresh_token_hash == presented_hash,
            )
        )
        if replayed is not None:
            log_event(db, event_type="Refresh_Failed", email_attempted="",
                      user_id=replayed.user_id, ip=ip, user_agent=ua,
                      failure_reason="Refresh_Token_Replay",
                      metadata={"session_id": str(replayed.id)})
            revoked = revoke_all_user_sessions(db, replayed.user_id, "Suspicious_Activity")
            log_event(db, event_type="Suspicious_Activity_Detected",
                      email_attempted="", user_id=replayed.user_id, ip=ip, user_agent=ua,
                      metadata={"trigger": "refresh_replay", "sessions_revoked": revoked})
            db.commit()
            raise HTTPException(status_code=401, detail="Refresh token replay detected — all sessions revoked")

        log_event(db, event_type="Refresh_Failed", email_attempted="",
                  ip=ip, user_agent=ua, failure_reason="Refresh_Token_Invalid")
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if session.revoked_at is not None:
        # Revoked refresh presented — treat as replay-like: be conservative.
        log_event(db, event_type="Refresh_Failed", email_attempted="",
                  user_id=session.user_id, ip=ip, user_agent=ua,
                  failure_reason="Refresh_Token_Replay",
                  metadata={"session_id": str(session.id)})
        revoked = revoke_all_user_sessions(db, session.user_id, "Suspicious_Activity")
        log_event(db, event_type="Suspicious_Activity_Detected",
                  email_attempted="", user_id=session.user_id, ip=ip, user_agent=ua,
                  metadata={"trigger": "refresh_replay", "sessions_revoked": revoked})
        db.commit()
        raise HTTPException(status_code=401, detail="Refresh token replay detected")

    if session.expires_at < datetime.now(timezone.utc):
        revoke_session(db, session, "Expiry")
        log_event(db, event_type="Refresh_Failed", email_attempted="",
                  user_id=session.user_id, ip=ip, user_agent=ua,
                  failure_reason="Refresh_Token_Invalid",
                  metadata={"reason": "expired"})
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.get(User, session.user_id)
    if user is None or user.status in ("Suspended", "Archived"):
        log_event(db, event_type="Refresh_Failed", email_attempted="",
                  user_id=session.user_id, ip=ip, user_agent=ua,
                  failure_reason="Account_Suspended")
        db.commit()
        raise HTTPException(status_code=401, detail="Account not active")

    access, raw_refresh = rotate_session(
        db, session, email=user.email, tenant_id=user.tenant_id,
        ip=ip, user_agent=ua,
    )
    log_event(db, event_type="Refresh_Success", email_attempted=user.email,
              user_id=user.id, session_id=session.id, ip=ip, user_agent=ua)
    db.commit()
    _set_cookies(response, access, raw_refresh, remember_me=session.remember_me)


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
):
    """Revoke current session. Unauthenticated endpoint — we look up the
    session via the refresh-token cookie (if present) or the access-token's
    sid. Either path ends with cleared cookies.
    """
    refresh = request.cookies.get("refresh_token")
    session: Optional[UserSession] = None
    if refresh:
        session = db.scalar(
            select(UserSession).where(UserSession.refresh_token_hash == hash_refresh(refresh))
        )
    if session is None:
        access = request.cookies.get("access_token")
        if access:
            try:
                from app.services.sessions import decode_access_jwt
                claims = decode_access_jwt(access)
                sid = claims.get("sid")
                if sid:
                    session = db.get(UserSession, uuid.UUID(sid))
            except Exception:
                pass

    if session is not None and session.revoked_at is None:
        revoke_session(db, session, "Logout")
        log_event(db, event_type="Logout", email_attempted="",
                  user_id=session.user_id, session_id=session.id,
                  ip=_client_ip(request), user_agent=_ua(request))
        record_audit(
            db, action="Logout", resource_type="users", resource_id=session.user_id,
            actor_user_id=session.user_id, session_id=session.id,
            request=request,
        )
        db.commit()

    _clear_cookies(response)


# ---------- Password reset ----------

@router.post("/password-reset/request", status_code=200)
def password_reset_request(
    payload: PasswordResetRequestPayload,
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Always returns 200 — we never leak whether the email exists."""
    email = (payload.email or "").strip().lower()
    ip = _client_ip(request)
    ua = _ua(request)

    ok_email, retry_email = enforce("pw_reset_request_per_email", email or "unknown")
    ok_ip, retry_ip = enforce("pw_reset_request_per_ip", ip or "unknown")
    if not ok_email or not ok_ip:
        log_event(db, event_type="Password_Reset_Requested", email_attempted=email,
                  ip=ip, user_agent=ua, failure_reason="Rate_Limited")
        db.commit()
        return {"ok": True}

    user = db.scalar(
        select(User).where(User.email == email, User.tenant_id == tenant_id)
    )
    if user is not None and user.status == "Active":
        raw = secrets.token_urlsafe(32)
        user.password_reset_token_hash = hashlib.sha256(raw.encode()).hexdigest()
        user.password_reset_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        import os
        app_origin = os.environ.get("APP_ORIGIN", "").rstrip("/") or str(request.base_url).rstrip("/")
        reset_url = f"{app_origin}/reset-password?token={raw}"
        subj, html, text = password_reset_email(
            recipient_name=user.display_name or user.first_name, reset_url=reset_url,
        )
        send_email(db, to=user.email, subject=subj, html=html, text=text,
                   template_id="password_reset_email")
        log_event(db, event_type="Password_Reset_Requested", email_attempted=email,
                  user_id=user.id, ip=ip, user_agent=ua)
        # Prompt 1.7 retro-wire: in-app Security_Alert.
        try:
            from app.services.notifications import safe_dispatch
            safe_dispatch(
                db,
                recipient_user_id=user.id,
                notification_type="Security_Alert",
                title="Password reset requested",
                body=(
                    "A password reset was requested for your account. "
                    "If this wasn't you, change your password and review "
                    "your active sessions immediately."
                ),
                priority="High",
                related_resource_type="users",
                related_resource_id=user.id,
                action_url="/profile/sessions",
                action_label="View sessions",
                request=request,
            )
        except Exception:
            pass
    else:
        log_event(db, event_type="Password_Reset_Requested", email_attempted=email,
                  ip=ip, user_agent=ua, metadata={"outcome": "no_account_or_not_active"})
    db.commit()
    return {"ok": True}


@router.post("/password-reset/complete", status_code=204)
def password_reset_complete(
    payload: PasswordResetCompleteRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    ip = _client_ip(request)
    ua = _ua(request)
    ok_ip, retry_ip = enforce("pw_reset_complete_per_ip", ip or "unknown")
    if not ok_ip:
        raise _rate_429(retry_ip)

    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    user = db.scalar(select(User).where(User.password_reset_token_hash == token_hash))
    if user is None:
        log_event(db, event_type="Password_Reset_Completed", email_attempted="",
                  ip=ip, user_agent=ua, failure_reason="Reset_Token_Invalid")
        db.commit()
        raise HTTPException(status_code=400, detail="Reset link is invalid or already used")
    if user.password_reset_expires_at is None or user.password_reset_expires_at < datetime.now(timezone.utc):
        user.password_reset_token_hash = None
        user.password_reset_expires_at = None
        log_event(db, event_type="Password_Reset_Completed", email_attempted=user.email,
                  user_id=user.id, ip=ip, user_agent=ua, failure_reason="Reset_Token_Expired")
        db.commit()
        raise HTTPException(status_code=400, detail="Reset link has expired")

    if user.mfa_enabled:
        if not payload.mfa_code or not user.mfa_secret_encrypted:
            log_event(db, event_type="Password_Reset_Completed", email_attempted=user.email,
                      user_id=user.id, ip=ip, user_agent=ua, failure_reason="MFA_Missing")
            db.commit()
            raise HTTPException(status_code=401, detail="Two-factor code required to complete reset")
        secret = decrypt_secret(user.mfa_secret_encrypted)
        if not verify_totp(secret, payload.mfa_code.strip()):
            log_event(db, event_type="Password_Reset_Completed", email_attempted=user.email,
                      user_id=user.id, ip=ip, user_agent=ua, failure_reason="MFA_Invalid")
            db.commit()
            raise HTTPException(status_code=401, detail="Invalid two-factor code")

    if is_in_history(payload.new_password, user.password_history or []):
        raise HTTPException(status_code=400,
                            detail=f"Password cannot match any of your last {PASSWORD_HISTORY_SIZE} passwords")
    try:
        new_hash = hash_password(payload.new_password)
    except PasswordPolicyError as e:
        raise HTTPException(status_code=422, detail=str(e))

    hist = list(user.password_history or [])
    hist.append({
        "hash": user.password_hash,
        "algorithm": user.password_algorithm,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    })
    hist = hist[-PASSWORD_HISTORY_SIZE:]

    user.password_hash = new_hash
    user.password_algorithm = "argon2id"
    user.password_history = hist
    user.password_changed_at = datetime.now(timezone.utc)
    user.password_reset_token_hash = None
    user.password_reset_expires_at = None
    _clear_lockout(user)

    revoke_all_user_sessions(db, user.id, "Password_Reset")
    log_event(db, event_type="Password_Reset_Completed", email_attempted=user.email,
              user_id=user.id, ip=ip, user_agent=ua)
    record_audit(
        db, action="Update", resource_type="users", resource_id=user.id,
        actor_user_id=user.id,
        field_changes=[{"field": "password_hash", "old": "[REDACTED]", "new": "[REDACTED]"}],
        metadata={"reset_initiator": "self"},
        request=request,
    )

    subj, html, text = password_changed_email(
        recipient_name=user.display_name or user.first_name,
        when=datetime.now(timezone.utc), ip=ip,
    )
    send_email(db, to=user.email, subject=subj, html=html, text=text,
               template_id="password_changed_email")
    db.commit()


@router.get("/password-policy")
def password_policy():
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
    if principal.token_type == "mfa_pending":
        permissions: list[str] = []
        is_super_admin = False
    else:
        perms = compute_effective_permissions(db, u.id, principal.tenant_id)
        permissions = sorted(perms.all_permissions)
        is_super_admin = perms.is_super_admin

    enforced_role = None
    enforcement_required = False
    if not u.mfa_enabled:
        enforced_role = _most_senior_enforced_role(db, u)
        enforcement_required = enforced_role is not None

    backup_remaining = count_unused_backup_codes(u.mfa_backup_codes_encrypted)

    return MeResponse(
        id=u.id, email=u.email,
        first_name=u.first_name, last_name=u.last_name,
        display_name=u.display_name or f"{u.first_name} {u.last_name}",
        user_type=u.user_type, status=u.status,
        mfa_enabled=u.mfa_enabled, mfa_method=u.mfa_method,
        mfa_enrollment_required=enforcement_required,
        mfa_backup_codes_remaining=backup_remaining,
        enforced_role_name=enforced_role.name if enforced_role else None,
        token_type=principal.token_type,
        permissions=permissions, is_super_admin=is_super_admin,
        password_changed_at=u.password_changed_at,
        last_login_at=u.last_login_at,
        current_session_id=principal.session.id if principal.session else None,
    )
