"""User preferences service — per-user UI surface state CRUD.

Chat 23 Build Pack A R1.4. No tenant scoping — user_id IS the scope.
Surface keys are open-ended strings (the application layer decides
which surfaces exist). The two partial-unique indexes from migration
0028 guarantee:
  - At most one row with `name IS NULL` per (user_id, surface_key).
  - At most one row with a given `(user_id, surface_key, name)` triple
    for non-null `name`.

The service treats those indexes as the source of truth: it does not
hold its own optimistic-check before INSERT; instead it lets the DB
raise IntegrityError and translates to ConflictError for the route.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.user_preferences import UserPreference


class UserPreferenceConflictError(Exception):
    """409: a named view with this name already exists for the surface."""


class UserPreferenceNotFoundError(Exception):
    """404: named view not found for the (user, surface) pair."""


# ----------------------------------------------------------------------
# Current (autosave) row
# ----------------------------------------------------------------------
def get_current(
    db: Session, *, user_id: uuid.UUID, surface_key: str,
) -> Optional[UserPreference]:
    return db.scalar(
        select(UserPreference).where(
            UserPreference.user_id == user_id,
            UserPreference.surface_key == surface_key,
            UserPreference.name.is_(None),
        )
    )


def set_current(
    db: Session, *, user_id: uuid.UUID, surface_key: str,
    payload: dict[str, Any],
) -> UserPreference:
    """Upsert the current-state row. Idempotent: creates on first call,
    updates payload + bumps updated_at on subsequent calls."""
    row = get_current(db, user_id=user_id, surface_key=surface_key)
    if row is None:
        row = UserPreference(
            user_id=user_id, surface_key=surface_key,
            name=None, payload=payload,
        )
        db.add(row)
        db.flush()
        return row
    row.payload = payload
    db.flush()
    return row


# ----------------------------------------------------------------------
# Named saved views
# ----------------------------------------------------------------------
def list_views(
    db: Session, *, user_id: uuid.UUID, surface_key: str,
) -> list[UserPreference]:
    return list(db.scalars(
        select(UserPreference)
        .where(
            UserPreference.user_id == user_id,
            UserPreference.surface_key == surface_key,
            UserPreference.name.is_not(None),
        )
        .order_by(UserPreference.updated_at.desc())
    ).all())


def get_view(
    db: Session, *, user_id: uuid.UUID, surface_key: str, name: str,
) -> Optional[UserPreference]:
    return db.scalar(
        select(UserPreference).where(
            UserPreference.user_id == user_id,
            UserPreference.surface_key == surface_key,
            UserPreference.name == name,
        )
    )


def create_view(
    db: Session, *, user_id: uuid.UUID, surface_key: str,
    name: str, payload: dict[str, Any],
) -> UserPreference:
    row = UserPreference(
        user_id=user_id, surface_key=surface_key,
        name=name, payload=payload,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise UserPreferenceConflictError(
            f"A view named {name!r} already exists for surface "
            f"{surface_key!r}"
        ) from exc
    return row


def update_view(
    db: Session, *, user_id: uuid.UUID, surface_key: str,
    name: str, payload: dict[str, Any],
) -> UserPreference:
    row = get_view(db, user_id=user_id, surface_key=surface_key, name=name)
    if row is None:
        raise UserPreferenceNotFoundError(
            f"View {name!r} not found for surface {surface_key!r}"
        )
    row.payload = payload
    db.flush()
    return row


def delete_view(
    db: Session, *, user_id: uuid.UUID, surface_key: str, name: str,
) -> bool:
    row = get_view(db, user_id=user_id, surface_key=surface_key, name=name)
    if row is None:
        return False
    db.delete(row)
    db.flush()
    return True
