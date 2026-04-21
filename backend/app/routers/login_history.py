"""Login-history read endpoints — Prompt 1.3 stage 1b."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth.deps import require_permission
from app.models.sessions import UserLoginHistory

router = APIRouter(tags=["login-history"])


class LoginHistoryRow(BaseModel):
    id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    email_attempted: str
    event_type: str
    failure_reason: Optional[str] = None
    ip_address: str
    user_agent: str
    location_country: Optional[str] = None
    location_city: Optional[str] = None
    session_id: Optional[uuid.UUID] = None
    metadata: dict = {}
    created_at: datetime


class LoginHistoryPage(BaseModel):
    items: list[LoginHistoryRow]
    total: int
    page: int
    page_size: int


def _row_to_model(r: UserLoginHistory) -> LoginHistoryRow:
    return LoginHistoryRow(
        id=r.id, user_id=r.user_id, email_attempted=r.email_attempted,
        event_type=r.event_type, failure_reason=r.failure_reason,
        ip_address=r.ip_address, user_agent=r.user_agent,
        location_country=r.location_country, location_city=r.location_city,
        session_id=r.session_id, metadata=r.metadata_json or {},
        created_at=r.created_at,
    )


def _base_query(
    user_id: Optional[uuid.UUID] = None,
    event_types: Optional[list[str]] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    success_only: Optional[bool] = None,
):
    q = select(UserLoginHistory)
    if user_id is not None:
        q = q.where(UserLoginHistory.user_id == user_id)
    if event_types:
        q = q.where(UserLoginHistory.event_type.in_(event_types))
    if start is not None:
        q = q.where(UserLoginHistory.created_at >= start)
    if end is not None:
        q = q.where(UserLoginHistory.created_at <= end)
    if success_only is True:
        q = q.where(UserLoginHistory.failure_reason.is_(None))
    if success_only is False:
        q = q.where(UserLoginHistory.failure_reason.is_not(None))
    return q


@router.get("/users/{user_id}/login-history", response_model=LoginHistoryPage)
def list_user_login_history(
    user_id: uuid.UUID,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    event_types: Optional[list[str]] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    success_only: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_permission("users.admin")),
):
    q = _base_query(user_id, event_types, start, end, success_only)
    q = q.order_by(UserLoginHistory.created_at.desc())
    total = db.scalar(select(__import__("sqlalchemy").func.count()).select_from(q.subquery()))
    rows = db.scalars(q.offset((page - 1) * page_size).limit(page_size)).all()
    return LoginHistoryPage(
        items=[_row_to_model(r) for r in rows],
        total=int(total or 0), page=page, page_size=page_size,
    )


@router.get("/users/{user_id}/login-history.csv")
def export_user_login_history_csv(
    user_id: uuid.UUID,
    event_types: Optional[list[str]] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_permission("users.admin")),
):
    q = _base_query(user_id, event_types, start, end).order_by(UserLoginHistory.created_at.desc())
    rows = db.scalars(q.limit(10000)).all()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "timestamp_utc", "event_type", "failure_reason", "email_attempted",
        "ip_address", "country", "city", "session_id", "user_agent",
    ])
    for r in rows:
        writer.writerow([
            r.created_at.isoformat(),
            r.event_type,
            r.failure_reason or "",
            r.email_attempted,
            r.ip_address,
            r.location_country or "",
            r.location_city or "",
            str(r.session_id) if r.session_id else "",
            r.user_agent,
        ])
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="login-history-{user_id}.csv"'},
    )
