"""Reference-data admin services — Prompt 2.1.

- `create_sdlt_structure(...)` — atomic version transition:
    1. Close off currently-active bands (effective_to = new effective_from - 1)
    2. Insert the new bands with effective_to=NULL
    3. ONE audit_log row describing the transition (rows_closed + rows_created).

- `update_appraisal_setting(...)` — tenant-scoped update with per-row audit.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Iterable, Optional
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select, update as sql_update
from sqlalchemy.orm import Session

from app.models.reference_data import (
    APPRAISAL_SETTING_TYPES, AppraisalDefaultSetting,
    PROJECT_TYPES, SDLT_CATEGORIES, SdltRateBand,
)
from app.services.audit import field_diff, record_audit


def create_sdlt_structure(
    db: Session,
    *,
    effective_from: date,
    bands_by_category: dict[str, list[dict]],
    actor_user_id: UUID,
    notes_by_row: Optional[list[str]] = None,
    request=None,
) -> dict:
    """Create a new SDLT version.

    bands_by_category : {category: [{"band_lower":…, "band_upper":…|None, "rate_pct":…, "notes":…?}, …]}
    Every category in bands_by_category has its previously-active rows
    closed off (effective_to = effective_from - 1 day) and the new rows
    are inserted. Categories NOT mentioned are left alone.
    """
    for cat in bands_by_category.keys():
        if cat not in SDLT_CATEGORIES:
            raise ValueError(f"Unknown SDLT category: {cat!r}")
    day_before = effective_from - timedelta(days=1)

    # Close off currently-active rows for each touched category.
    closed_count = 0
    for cat in bands_by_category:
        result = db.execute(
            sql_update(SdltRateBand)
            .where(
                SdltRateBand.category == cat,
                SdltRateBand.effective_to.is_(None),
                SdltRateBand.effective_from < effective_from,
            )
            .values(effective_to=day_before)
        )
        closed_count += result.rowcount or 0

    # Insert new rows.
    created_ids: list[UUID] = []
    for cat, rows in bands_by_category.items():
        for row in rows:
            b = SdltRateBand(
                effective_from=effective_from,
                effective_to=None,
                category=cat,
                band_lower=Decimal(str(row["band_lower"])),
                band_upper=(
                    Decimal(str(row["band_upper"]))
                    if row.get("band_upper") is not None else None
                ),
                rate_pct=Decimal(str(row["rate_pct"])),
                notes=row.get("notes"),
            )
            db.add(b)
            db.flush()
            created_ids.append(b.id)

    # One summary audit row per version transition.
    record_audit(
        db, action="Create", resource_type="sdlt_rate_bands",
        resource_id=uuid4(), actor_user_id=actor_user_id,
        field_changes=[],
        metadata={
            "kind": "sdlt_version_transition",
            "effective_from": effective_from.isoformat(),
            "categories": sorted(bands_by_category.keys()),
            "rows_closed": closed_count,
            "rows_created": len(created_ids),
        },
        request=request,
    )
    return {
        "effective_from": effective_from.isoformat(),
        "rows_closed": closed_count,
        "rows_created": len(created_ids),
        "new_band_ids": [str(i) for i in created_ids],
    }


def update_appraisal_setting(
    db: Session,
    *,
    setting_id: UUID,
    new_value: Decimal,
    new_description: Optional[str],
    actor_user_id: UUID,
    tenant_id: UUID,
    request=None,
) -> AppraisalDefaultSetting:
    """Tenant-scoped update.

    Rejects a row whose tenant_id doesn't match the caller's — this is
    the hard isolation guard. Audits old+new per field.
    """
    row = db.get(AppraisalDefaultSetting, setting_id)
    if row is None:
        raise LookupError("setting not found")
    if row.tenant_id != tenant_id:
        # Treat as not-found from the outside — don't leak existence.
        raise LookupError("setting not found")

    old = {
        "setting_value": str(row.setting_value),
        "description": row.description,
    }
    row.setting_value = Decimal(str(new_value))
    if new_description is not None:
        row.description = new_description
    row.updated_by_user_id = actor_user_id
    row.updated_at = datetime.now(timezone.utc)
    db.flush()

    new = {
        "setting_value": str(row.setting_value),
        "description": row.description,
    }
    record_audit(
        db, action="Update", resource_type="appraisal_default_settings",
        resource_id=row.id, actor_user_id=actor_user_id,
        field_changes=field_diff(old, new),
        metadata={
            "setting_key": row.setting_key,
            "applies_to_project_type": row.applies_to_project_type,
        },
        request=request,
    )
    return row
