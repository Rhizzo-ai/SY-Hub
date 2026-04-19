"""Meta endpoints — enums, tenant info, manual job trigger for testing."""
from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_tenant_id
from app.jobs.insurance_alerts import compute_insurance_alerts
from app.models import (
    Tenant,
    ENTITY_TYPES,
    VAT_SCHEMES,
    VAT_RETURN_PERIODS,
    CIS_STATUSES,
    ENTITY_STATUSES,
)
from app.schemas.entity import InsuranceAlert

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/enums")
def get_enums():
    return {
        "entity_types": list(ENTITY_TYPES),
        "vat_schemes": list(VAT_SCHEMES),
        "vat_return_periods": list(VAT_RETURN_PERIODS),
        "cis_statuses": list(CIS_STATUSES),
        "entity_statuses": list(ENTITY_STATUSES),
    }


@router.get("/tenant")
def get_tenant(
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    t = db.get(Tenant, tenant_id)
    return {
        "id": str(t.id),
        "name": t.name,
        "created_at": t.created_at.isoformat(),
    }


@router.get("/insurance-alerts", response_model=List[InsuranceAlert])
def preview_insurance_alerts(
    db: Session = Depends(get_db),
    tenant_id: uuid.UUID = Depends(get_current_tenant_id),
):
    """Preview today's insurance alerts on demand (read-only).

    The scheduled daily job uses the same computation; this endpoint exposes
    it for UI dashboards and acceptance testing.
    """
    return compute_insurance_alerts(db, tenant_id)
