"""Session management endpoints — Prompt 1.3 stage 1b."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import Principal
from app.auth.deps import get_current_principal, require_permission
from app.models.sessions import UserSession
from app.models.user import User
from app.services.email import send_email
from app.services.email_templates import session_revoked_email
from app.services.sessions import (
    revoke_all_user_sessions,
    revoke_session as _revoke,
    log_event,
)
from app.services.audit import record_audit

router = APIRouter(tags=["sessions"])


class SessionSummary(BaseModel):
    id: uuid.UUID
    device_name: Optional[str] = None
    user_agent: str
    ip_address: str
    location_country: Optional[str] = None
    location_city: Optional[str] = None
    last_active_at: datetime
    expires_at: datetime
    remember_me: bool
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None
    created_at: datetime
    is_current: bool = False


def _serialise(s: UserSession, *, current_id: Optional[uuid.UUID] = None) -> SessionSummary:
    return SessionSummary(
        id=s.id,
        device_name=s.device_name,
        user_agent=s.user_agent or "",
        ip_address=s.ip_address or "",
        location_country=s.location_country,
        location_city=s.location_city,
        last_active_at=s.last_active_at,
        expires_at=s.expires_at,
        remember_me=s.remember_me,
        revoked_at=s.revoked_at,
        revoked_reason=s.revoked_reason,
        created_at=s.created_at,
        is_current=(current_id is not None and s.id == current_id),
    )


# ---------- My sessions ----------

@router.get("/users/me/sessions", response_model=list[SessionSummary])
def list_my_sessions(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == principal.user.id)
        .order_by(UserSession.last_active_at.desc())
        .limit(50)
    ).all()
    current_id = principal.session.id if principal.session else None
    return [_serialise(r, current_id=current_id) for r in rows]


@router.post("/users/me/sessions/{session_id}/revoke", status_code=204)
def revoke_my_session(
    session_id: uuid.UUID,
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    s = db.get(UserSession, session_id)
    if s is None or s.user_id != principal.user.id:
        raise HTTPException(404, "Session not found")
    if s.revoked_at is not None:
        return
    _revoke(db, s, "Logout")
    log_event(db, event_type="Session_Revoked", email_attempted=principal.user.email,
              user_id=principal.user.id, session_id=s.id,
              ip=s.ip_address or "", user_agent=s.user_agent or "",
              metadata={"initiator": "self"})
    record_audit(
        db, action="Delete", resource_type="user_sessions", resource_id=s.id,
        actor_user_id=principal.user.id,
        metadata={"reason": "user_revoke"}, request=request,
    )
    db.commit()


@router.post("/users/me/sessions/revoke-others", status_code=204)
def revoke_all_other_sessions(
    request: Request,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    current_id = principal.session.id if principal.session else None
    # Capture the sessions that will be revoked, so each gets its own audit row.
    to_revoke = db.scalars(
        select(UserSession).where(
            UserSession.user_id == principal.user.id,
            UserSession.revoked_at.is_(None),
            UserSession.id != current_id,
        )
    ).all()
    revoked = revoke_all_user_sessions(
        db, principal.user.id, "Logout", except_session_id=current_id,
    )
    log_event(db, event_type="Session_Revoked", email_attempted=principal.user.email,
              user_id=principal.user.id, session_id=current_id,
              ip="", user_agent="",
              metadata={"initiator": "self", "scope": "all_others", "count": revoked})
    for s in to_revoke:
        record_audit(
            db, action="Delete", resource_type="user_sessions", resource_id=s.id,
            actor_user_id=principal.user.id,
            metadata={"reason": "user_revoke_all_others"}, request=request,
        )
    db.commit()


# ---------- Admin ----------

@router.get("/users/{user_id}/sessions", response_model=list[SessionSummary])
def list_user_sessions(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _=Depends(require_permission("users.admin")),
):
    rows = db.scalars(
        select(UserSession)
        .where(UserSession.user_id == user_id)
        .order_by(UserSession.last_active_at.desc())
        .limit(100)
    ).all()
    return [_serialise(r) for r in rows]


@router.post("/users/{user_id}/sessions/revoke-all", status_code=204)
def admin_revoke_all_sessions(
    user_id: uuid.UUID,
    request: Request,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
    _=Depends(require_permission("users.admin")),
):
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(404, "User not found")
    to_revoke = db.scalars(
        select(UserSession).where(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
    ).all()
    revoked = revoke_all_user_sessions(db, user_id, "Admin_Revoke")
    log_event(db, event_type="Session_Revoked", email_attempted=target.email,
              user_id=user_id, ip="", user_agent="",
              metadata={"initiator": "admin", "admin_user_id": str(principal.user.id),
                        "count": revoked})
    for s in to_revoke:
        record_audit(
            db, action="Delete", resource_type="user_sessions", resource_id=s.id,
            actor_user_id=principal.user.id,
            metadata={"reason": "admin_revoke", "target_user_id": str(user_id)},
            request=request,
        )
    if revoked > 0:
        subj, html, text = session_revoked_email(
            recipient_name=target.display_name or target.first_name,
            revoked_by=principal.user.email, reason="administrator revocation",
        )
        send_email(db, to=target.email, subject=subj, html=html, text=text,
                   template_id="session_revoked_email")
    db.commit()
