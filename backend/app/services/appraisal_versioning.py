"""Appraisal versioning / state machine — Prompt 2.2 + 2.3 Checkpoint 1.

State machine (post-2.3 retrofit):

    Draft ─submit──▶ Submitted ─approve─▶ Approved ┐
      │ ▲              │                            │
      │ │              ├─reject─▶ Rejected ─reopen─▶ Reopened ◀──┐
      │ │              │                                          │
      │ └──── reopen (Approved → cloned new Draft, source ─┐      │
      │      Superseded) — TODO 2.3 C2: split into         │      │
      │      /new-version endpoint                          │      │
      │                                                     ▼      │
      ├─withdraw─▶ Withdrawn (terminal)                            │
      │                                                            │
      └────── (Reopened is editable like Draft) ───────────────────┘

Rules:
- ONLY `Draft` and `Reopened` rows can be edited.
- `Withdrawn` and `Superseded` are terminal.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models.appraisals import (
    Appraisal, AppraisalUnit, AppraisalCostLine, AppraisalFinanceFacility,
)


# State transition rules (post-2.3 retrofit).
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "Draft":      {"Submitted", "Withdrawn"},
    "Submitted":  {"Approved", "Rejected", "Draft", "Withdrawn"},
    "Approved":   {"Superseded", "Reopened"},
    "Rejected":   {"Reopened"},
    "Reopened":   {"Submitted", "Withdrawn"},
    "Withdrawn":  set(),
    "Superseded": set(),
}


@dataclass
class TransitionError(Exception):
    current: str
    target: str

    def __str__(self) -> str:
        return f"Cannot transition from {self.current!r} to {self.target!r}."


def assert_transition(current: str, target: str) -> None:
    if target not in ALLOWED_TRANSITIONS.get(current, set()):
        raise TransitionError(current=current, target=target)


def is_editable(appraisal: Appraisal) -> bool:
    """Draft and Reopened rows take edits to data (Phase B.1)."""
    return appraisal.status in ("Draft", "Reopened")


def next_version_for_project(db: Session, project_id, scenario: str = "Base") -> int:
    """Return the next appraisal version number for a project + scenario.

    Versions are per (project_id, scenario) contiguous (1, 2, 3, …). The DB
    unique (project_id, scenario, version_number) guards against races.
    """
    row = db.execute(
        select(func.coalesce(func.max(Appraisal.version_number), 0)).where(
            Appraisal.project_id == project_id,
            Appraisal.scenario == scenario,
        )
    ).scalar_one()
    return int(row or 0) + 1


def clone_as_new_version(
    db: Session,
    source: Appraisal,
    *,
    created_by_user_id,
) -> Appraisal:
    """Deep-clone an appraisal into a new Draft at version_number = max + 1.

    Units, cost lines, and finance facilities are all copied. The new row's
    `previous_version_id` points at the source. The source is NOT mutated
    here — caller decides whether to mark it Superseded and whether to flip
    is_current. New row starts with is_current=False; caller flips it true
    AFTER setting source.is_current=False (Phase B.2 atomicity).
    """
    new = Appraisal(
        project_id=source.project_id,
        appraisal_group_id=source.appraisal_group_id,
        scenario=source.scenario,
        is_current=False,
        version_number=next_version_for_project(db, source.project_id, source.scenario),
        previous_version_id=source.id,
        name=source.name,
        status="Draft",
        reference_date=source.reference_date,
        land_purchase_price=Decimal(source.land_purchase_price or 0),
        sdlt_category=source.sdlt_category,
        developer_relief=source.developer_relief,
        contingency_pct=Decimal(source.contingency_pct or 0),
        target_profit_on_cost_pct=Decimal(source.target_profit_on_cost_pct or 0),
        target_profit_on_gdv_pct=Decimal(source.target_profit_on_gdv_pct or 0),
        project_duration_months=source.project_duration_months,
        rlv_enabled=source.rlv_enabled,
        rlv_target_basis=source.rlv_target_basis,
        rlv_target_value=Decimal(source.rlv_target_value or 0),
        notes=source.notes,
        created_by_user_id=created_by_user_id,
        is_stale=True,  # force a recompute on first save.
    )
    db.add(new)
    db.flush()

    for u in source.units or []:
        db.add(AppraisalUnit(
            appraisal_id=new.id, display_order=u.display_order,
            unit_label=u.unit_label, unit_type=u.unit_type, tenure=u.tenure,
            quantity=u.quantity, beds=u.beds,
            gia_sqm=u.gia_sqm,
            price_per_unit=Decimal(u.price_per_unit or 0),
            build_cost_per_unit=Decimal(u.build_cost_per_unit or 0),
            notes=u.notes,
        ))
    for l in source.cost_lines or []:
        db.add(AppraisalCostLine(
            appraisal_id=new.id, display_order=l.display_order,
            cost_code_id=l.cost_code_id, label=l.label,
            category=l.category, auto_source=l.auto_source,
            percentage=l.percentage, amount=Decimal(l.amount or 0),
            is_locked=l.is_locked, notes=l.notes,
        ))
    for f in source.finance_facilities or []:
        db.add(AppraisalFinanceFacility(
            appraisal_id=new.id, display_order=f.display_order,
            label=f.label, facility_type=f.facility_type,
            principal_amount=Decimal(f.principal_amount or 0),
            interest_rate_pct=Decimal(f.interest_rate_pct or 0),
            arrangement_fee_pct=Decimal(f.arrangement_fee_pct or 0),
            exit_fee_pct=Decimal(f.exit_fee_pct or 0),
            interest_mode=f.interest_mode,
            drawn_from_month=f.drawn_from_month,
            drawn_to_month=f.drawn_to_month,
            notes=f.notes,
        ))
    db.flush()
    return new


def mark_superseded(appraisal: Appraisal) -> None:
    appraisal.status = "Superseded"
    appraisal.updated_at = datetime.now(timezone.utc)
