"""Trades service — tenant-scoped managed vocabulary (Chat 41 §R3.1 / 2.7-BE-rev-A).

Stateless service mirroring `services/suppliers.py` conventions. The
critical primitive is `get_or_create_trade`, the grow-as-you-type entry
point used by `services/suppliers._resolve_trade`. It is concurrency-safe
via a SAVEPOINT around the flush — two near-simultaneous "add Electrician"
requests resolve to the same row (case-insensitive uniqueness per tenant
is enforced by `ux_trades_tenant_name_ci`).
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.trades import Trade
from app.services.audit import field_diff, record_audit


# Columns we snapshot for audit diffing.
_AUDIT_COLS: tuple[str, ...] = ("name", "is_archived")

# Collapse runs of internal whitespace to a single space.
_WS_RE = re.compile(r"\s+")


def _snapshot(t: Trade) -> dict[str, Any]:
    return {col: getattr(t, col) for col in _AUDIT_COLS}


def _normalise_name(value: Any) -> str:
    if value is None:
        raise ValueError("name is required")
    if not isinstance(value, str):
        raise ValueError("name must be a string")
    cleaned = _WS_RE.sub(" ", value).strip()
    if not cleaned:
        raise ValueError("name is required")
    if len(cleaned) > 100:
        raise ValueError("name must be ≤ 100 characters")
    return cleaned


def _select_by_ci_name(
    tenant_id: uuid.UUID, name: str,
):
    """Case-insensitive lookup within tenant."""
    return select(Trade).where(
        Trade.tenant_id == tenant_id,
        func.lower(Trade.name) == name.lower(),
    )


def list_trades(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    q: Optional[str] = None,
    include_archived: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> tuple[list[Trade], int]:
    """Tenant-scoped paginated list. Returns (rows, total_unpaged).

    `q` is a case-insensitive substring match on `name`. Archived trades
    are excluded by default (mirrors the suppliers convention).
    """
    where = [Trade.tenant_id == tenant_id]
    if not include_archived:
        where.append(Trade.is_archived.is_(False))
    if q:
        like = f"%{q.lower()}%"
        where.append(func.lower(Trade.name).like(like))
    base = select(Trade).where(and_(*where))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        db.scalars(
            base.order_by(Trade.name.asc()).limit(limit).offset(offset)
        ).all()
    )
    return rows, int(total)


def get_trade(
    db: Session, tenant_id: uuid.UUID, trade_id: uuid.UUID,
) -> Optional[Trade]:
    return db.scalar(
        select(Trade).where(
            Trade.tenant_id == tenant_id,
            Trade.id == trade_id,
        )
    )


def get_or_create_trade(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    name: Any,
    *,
    request: Optional[Request] = None,
) -> Trade:
    """Grow-as-you-type primitive (Chat 41 §R3.1).

    - Trim + collapse internal whitespace on `name`; reject empty / >100.
    - Look up case-insensitively within tenant; if found, return it (no
      audit, no mutation).
    - If not found, INSERT inside a SAVEPOINT (begin_nested). On
      IntegrityError from `ux_trades_tenant_name_ci` (a concurrent insert
      won the race), roll back to the savepoint and re-select — both
      callers resolve to the same row, no 500.
    """
    cleaned = _normalise_name(name)

    existing = db.scalar(_select_by_ci_name(tenant_id, cleaned))
    if existing is not None:
        return existing

    row = Trade(
        tenant_id=tenant_id,
        name=cleaned,
        is_archived=False,
        created_by=user_id,
        updated_by=user_id,
    )
    try:
        with db.begin_nested():
            db.add(row)
            db.flush()
    except IntegrityError:
        # Concurrent insert won the unique-index race. Re-select the
        # winner and return it (idempotent — no audit row for the loser).
        winner = db.scalar(_select_by_ci_name(tenant_id, cleaned))
        if winner is None:
            # Genuinely something else broke — re-raise.
            raise
        return winner

    record_audit(
        db, action="Create",
        resource_type="trade",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff({}, _snapshot(row)),
        metadata={"name": row.name},
        request=request,
    )
    return row


def set_archived(
    db: Session,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    trade_id: uuid.UUID,
    *,
    archived: bool,
    request: Optional[Request] = None,
) -> Trade:
    """Toggle the archive flag. Idempotent — no audit row if no change.

    Archiving does NOT null out `suppliers.trade_id` on existing rows
    (per §R3.1 NOTE — `ON DELETE SET NULL` only fires on hard delete,
    which we don't expose; archived trades just stop appearing in pick
    lists).

    Raises:
        LookupError: trade not found in this tenant.
    """
    row = get_trade(db, tenant_id, trade_id)
    if row is None:
        raise LookupError(f"trade {trade_id} not found in tenant")

    if row.is_archived == archived:
        return row  # no-op

    before = _snapshot(row)
    row.is_archived = archived
    row.updated_by = user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    record_audit(
        db,
        action="Archive" if archived else "Restore",
        resource_type="trade",
        resource_id=row.id,
        actor_user_id=user_id,
        field_changes=field_diff(before, _snapshot(row)),
        metadata={"name": row.name},
        request=request,
    )
    return row


def serialise(row: Trade) -> dict[str, Any]:
    """Convert a Trade ORM row to a JSON-safe dict."""
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "is_archived": bool(row.is_archived),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
