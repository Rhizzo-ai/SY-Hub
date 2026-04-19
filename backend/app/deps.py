"""FastAPI dependencies — current tenant scope (single tenant in Phase 1)."""
from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Tenant


@lru_cache(maxsize=1)
def _default_tenant_name() -> str:
    import os
    return os.environ.get("DEFAULT_TENANT_NAME", "SY Homes")


def get_current_tenant_id(db: Session = Depends(get_db)) -> uuid.UUID:
    """Phase 1: single tenant. Look up the seeded 'SY Homes' tenant id.

    In Phase 2+ this will inspect the authenticated user's session for the
    tenant binding, or a subdomain, or an explicit header.
    """
    tenant = db.scalar(
        select(Tenant).where(Tenant.name == _default_tenant_name())
    )
    if tenant is None:
        raise HTTPException(
            status_code=500,
            detail="Default tenant not found; seed has not run.",
        )
    return tenant.id


def get_current_user_id() -> uuid.UUID | None:
    """Phase 1: hardcoded superuser; Prompt 1.2 replaces this with JWT decode."""
    return None
