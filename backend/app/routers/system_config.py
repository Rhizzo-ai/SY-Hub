"""System config router — Prompt 1.7.

All routes mount under /api/v1/system-config (the v1 prefix is set at
include time in server.py).

Permissions:
- view: system_config.view (granted to all 10 roles)
- write/restore: super_admin only (column `minimum_role_to_edit` kept
  for v2 enforcement)

Behaviour:
- PUT validates `value` parses against `value_type`; rejects locked rows.
- POST /restore resets to `default_value`.
- All writes audit Update with old+new in metadata.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.system_config import SystemConfig
from app.models.user import User
from app.services import system_config as svc


router = APIRouter(prefix="/system-config", tags=["system_config"])


class ConfigRowOut(BaseModel):
    id: str
    config_key: str
    config_value: Any  # parsed (typed)
    raw_value: str
    value_type: str
    category: str
    description: str
    is_system_locked: bool
    default_value: str
    last_changed_by_user_id: str | None
    last_changed_at: str | None
    is_at_default: bool


class ConfigPutBody(BaseModel):
    value: Any


def _serialise(row: SystemConfig) -> dict:
    try:
        parsed = svc._parse(row.config_value, row.value_type)  # type: ignore[attr-defined]
    except Exception:
        parsed = row.config_value
    return {
        "id": str(row.id),
        "config_key": row.config_key,
        "config_value": parsed,
        "raw_value": row.config_value,
        "value_type": row.value_type,
        "category": row.category,
        "description": row.description,
        "is_system_locked": row.is_system_locked,
        "default_value": row.default_value,
        "last_changed_by_user_id":
            str(row.last_changed_by_user_id) if row.last_changed_by_user_id else None,
        "last_changed_at":
            row.last_changed_at.isoformat() if row.last_changed_at else None,
        "is_at_default": row.config_value == row.default_value,
    }


@router.get("")
def list_grouped(
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.view")),
):
    rows = svc.list_all(db)
    by_cat: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_cat[r.category].append(_serialise(r))
    return {
        "items": [_serialise(r) for r in rows],
        "by_category": dict(by_cat),
        "count": len(rows),
    }


@router.get("/{key}")
def get_one(
    key: str,
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.view")),
):
    from sqlalchemy import select
    row = db.scalar(select(SystemConfig).where(SystemConfig.config_key == key))
    if row is None:
        raise HTTPException(404, f"system_config key not found: {key}")
    return _serialise(row)


@router.put("/{key}")
def update(
    key: str,
    body: ConfigPutBody,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.admin")),
):
    try:
        row = svc.set_value(db, key, body.value, current.id, request=request)
    except KeyError:
        raise HTTPException(404, f"system_config key not found: {key}")
    except PermissionError:
        raise HTTPException(409, f"system_config key {key} is system-locked")
    except ValueError as e:
        raise HTTPException(422, f"Invalid value for {key}: {e}")
    db.commit()
    db.refresh(row)
    return _serialise(row)


@router.post("/{key}/restore")
def restore(
    key: str,
    request: Request,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    _perms: UserPermissions = Depends(require_permission("system_config.admin")),
):
    try:
        row = svc.restore(db, key, current.id, request=request)
    except KeyError:
        raise HTTPException(404, f"system_config key not found: {key}")
    except PermissionError:
        raise HTTPException(409, f"system_config key {key} is system-locked")
    db.commit()
    db.refresh(row)
    return _serialise(row)
