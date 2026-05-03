"""Appraisals API — Prompt 2.2.

Mounts under /api/v1/appraisals.

Endpoints (high-level):
  Project-scoped:
    GET  /projects/{project_id}/appraisals                 list versions
    POST /projects/{project_id}/appraisals                 create Draft
  Appraisal-scoped:
    GET  /appraisals/{id}                                  header + children
    PUT  /appraisals/{id}                                  edit header (Draft only)
    POST /appraisals/{id}/recompute                        run 8-step pipeline
    POST /appraisals/{id}/recalculate-rlv                  run RLV solver
    POST /appraisals/{id}/submit                           Draft → Submitted
    POST /appraisals/{id}/approve                          Submitted → Approved
    POST /appraisals/{id}/reject                           Submitted → Rejected
    POST /appraisals/{id}/reopen                           Rejected/Approved → new Draft
    POST /appraisals/{id}/withdraw                         Submitted → Draft (author only)

  Units:
    POST   /appraisals/{id}/units
    PUT    /appraisals/{id}/units/{unit_id}
    DELETE /appraisals/{id}/units/{unit_id}

  Cost lines:
    POST   /appraisals/{id}/cost-lines
    PUT    /appraisals/{id}/cost-lines/{line_id}
    DELETE /appraisals/{id}/cost-lines/{line_id}

  Finance facilities:
    POST   /appraisals/{id}/finance
    PUT    /appraisals/{id}/finance/{fac_id}
    DELETE /appraisals/{id}/finance/{fac_id}

All writes audit via services.audit.record_audit.
`view_financials` gating: callers without `appraisals.view_financials`
see the header with the gated money keys REMOVED (not nullified).
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions, compute_effective_permissions
from app.db import get_db
from app.models.appraisals import (
    APPRAISAL_STATES, AUTO_SOURCES, COST_CATEGORIES, FINANCE_TYPES,
    INTEREST_MODES, TENURE_TYPES, UNIT_TYPES,
    Appraisal, AppraisalCostLine, AppraisalFinanceFacility, AppraisalUnit,
)
from app.models.projects import Project
from app.models.rbac import UserRole, user_role_projects
from app.models.reference_data import (
    APPRAISAL_SETTING_TYPES, AppraisalDefaultSetting, SDLT_CATEGORIES,
)
from app.models.user import User
from app.services import appraisal_calc, rlv_solver
from app.services.appraisal_versioning import (
    TransitionError, assert_transition, clone_as_new_version,
    is_editable, mark_superseded, next_version_for_project,
)
from app.services.audit import record_audit, field_diff, stamp_self_approval


router = APIRouter(tags=["appraisals"])


# Fields visible only with appraisals.view_financials
FINANCIAL_KEYS: tuple[str, ...] = (
    "land_purchase_price",
    "gdv_total",
    "total_acquisition_cost",
    "total_build_cost",
    "total_professional_fees",
    "total_statutory_cost",
    "total_finance_cost",
    "total_contingency",
    "total_sales_cost",
    "total_other_cost",
    "total_cost",
    "profit_total",
    "profit_on_cost_pct",
    "profit_on_gdv_pct",
    "target_profit_on_cost_pct",
    "target_profit_on_gdv_pct",
    "rlv_computed_land_value",
    "rlv_target_value",
)


# ---------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------

class AppraisalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    reference_date: Optional[date] = None
    land_purchase_price: Decimal = Decimal("0")
    sdlt_category: str = "Residential_Standard"
    developer_relief: bool = False
    project_duration_months: int = 18
    notes: Optional[str] = None


class AppraisalHeaderUpdate(BaseModel):
    name: Optional[str] = None
    reference_date: Optional[date] = None
    land_purchase_price: Optional[Decimal] = None
    sdlt_category: Optional[str] = None
    developer_relief: Optional[bool] = None
    contingency_pct: Optional[Decimal] = None
    target_profit_on_cost_pct: Optional[Decimal] = None
    target_profit_on_gdv_pct: Optional[Decimal] = None
    project_duration_months: Optional[int] = None
    rlv_enabled: Optional[bool] = None
    rlv_target_basis: Optional[str] = None
    rlv_target_value: Optional[Decimal] = None
    notes: Optional[str] = None


class UnitIn(BaseModel):
    display_order: int = 0
    unit_label: str = Field(min_length=1, max_length=100)
    unit_type: str = "Detached"
    tenure: str = "Open_Market"
    quantity: int = Field(ge=0, default=1)
    beds: Optional[int] = None
    gia_sqm: Optional[Decimal] = None
    price_per_unit: Decimal = Decimal("0")
    build_cost_per_unit: Decimal = Decimal("0")
    notes: Optional[str] = None


class CostLineIn(BaseModel):
    display_order: int = 0
    cost_code_id: Optional[uuid.UUID] = None
    label: str = Field(min_length=1, max_length=255)
    category: str = "Other"
    auto_source: str = "Manual"
    percentage: Optional[Decimal] = None
    amount: Decimal = Decimal("0")
    is_locked: bool = False
    notes: Optional[str] = None


class FacilityIn(BaseModel):
    display_order: int = 0
    label: str = Field(min_length=1, max_length=255)
    facility_type: str = "Debt"
    principal_amount: Decimal = Decimal("0")
    interest_rate_pct: Decimal = Decimal("0")
    arrangement_fee_pct: Decimal = Decimal("0")
    exit_fee_pct: Decimal = Decimal("0")
    interest_mode: str = "Simple_Monthly"
    drawn_from_month: int = 0
    drawn_to_month: int = 18
    notes: Optional[str] = None


class WorkflowActionIn(BaseModel):
    reason: Optional[str] = None


class RlvRequestIn(BaseModel):
    basis: Optional[str] = None          # override header basis
    target_pct: Optional[Decimal] = None  # override header target


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def _visible_project_ids(
    db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID,
) -> Optional[set[uuid.UUID]]:
    """None = all-projects; empty set = no access; else explicit set."""
    now = datetime.now(timezone.utc)
    roles = db.scalars(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.status == "Active",
            or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
        )
    ).all()
    ids: set[uuid.UUID] = set()
    has_all = False
    for ur in roles:
        if ur.project_scope == "All":
            has_all = True
        elif ur.project_scope == "Specific":
            rows = db.execute(
                select(user_role_projects.c.project_id)
                .where(user_role_projects.c.user_role_id == ur.id)
            ).all()
            ids.update(r[0] for r in rows)
    if has_all:
        return None
    return ids


def _load_appraisal(
    db: Session, appraisal_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Appraisal:
    row = db.get(Appraisal, appraisal_id)
    if row is None:
        raise HTTPException(404, "Appraisal not found")
    project = db.get(Project, row.project_id)
    if project is None:
        raise HTTPException(404, "Appraisal not found")
    # Tenant isolation via project.
    if hasattr(project, "tenant_id") and project.tenant_id != user.tenant_id:
        # Our Project model doesn't store tenant_id directly — it's inherited
        # via primary_entity. Skip if not present on the model.
        raise HTTPException(404, "Appraisal not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and project.id not in allowed:
            raise HTTPException(404, "Appraisal not found")
    return row


def _load_project(
    db: Session, project_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Project:
    p = db.get(Project, project_id)
    if p is None:
        raise HTTPException(404, "Project not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and p.id not in allowed:
            raise HTTPException(404, "Project not found")
    return p


def _serialise_unit(u: AppraisalUnit) -> dict:
    return {
        "id": str(u.id),
        "display_order": u.display_order,
        "unit_label": u.unit_label,
        "unit_type": u.unit_type,
        "tenure": u.tenure,
        "quantity": u.quantity,
        "beds": u.beds,
        "gia_sqm": str(u.gia_sqm) if u.gia_sqm is not None else None,
        "price_per_unit": str(u.price_per_unit),
        "build_cost_per_unit": str(u.build_cost_per_unit),
        "notes": u.notes,
    }


def _serialise_line(l: AppraisalCostLine) -> dict:
    return {
        "id": str(l.id),
        "display_order": l.display_order,
        "cost_code_id": str(l.cost_code_id) if l.cost_code_id else None,
        "label": l.label,
        "category": l.category,
        "auto_source": l.auto_source,
        "percentage": str(l.percentage) if l.percentage is not None else None,
        "amount": str(l.amount),
        "is_locked": l.is_locked,
        "notes": l.notes,
    }


def _serialise_fac(f: AppraisalFinanceFacility) -> dict:
    return {
        "id": str(f.id),
        "display_order": f.display_order,
        "label": f.label,
        "facility_type": f.facility_type,
        "principal_amount": str(f.principal_amount),
        "interest_rate_pct": str(f.interest_rate_pct),
        "arrangement_fee_pct": str(f.arrangement_fee_pct),
        "exit_fee_pct": str(f.exit_fee_pct),
        "interest_mode": f.interest_mode,
        "drawn_from_month": f.drawn_from_month,
        "drawn_to_month": f.drawn_to_month,
        "total_interest": str(f.total_interest),
        "total_fees": str(f.total_fees),
        "total_finance_cost": str(f.total_finance_cost),
        "notes": f.notes,
    }


def _serialise_header(a: Appraisal, perms: UserPermissions) -> dict:
    d: dict[str, Any] = {
        "id": str(a.id),
        "project_id": str(a.project_id),
        "version_number": a.version_number,
        "previous_version_id": str(a.previous_version_id) if a.previous_version_id else None,
        "name": a.name,
        "status": a.status,
        "appraisal_group_id": str(a.appraisal_group_id) if a.appraisal_group_id else None,
        "is_current": a.is_current,
        "scenario": a.scenario,
        "reference_date": a.reference_date.isoformat(),
        "sdlt_category": a.sdlt_category,
        "developer_relief": a.developer_relief,
        "contingency_pct": str(a.contingency_pct),
        "project_duration_months": a.project_duration_months,
        "rlv_enabled": a.rlv_enabled,
        "rlv_target_basis": a.rlv_target_basis,
        "rlv_iterations": a.rlv_iterations,
        "rlv_converged": a.rlv_converged,
        "rlv_computed_at": (
            a.rlv_computed_at.isoformat() if a.rlv_computed_at else None
        ),
        "notes": a.notes,
        "is_stale": a.is_stale,
        "submitted_by_user_id": (
            str(a.submitted_by_user_id) if a.submitted_by_user_id else None
        ),
        "submitted_at": a.submitted_at.isoformat() if a.submitted_at else None,
        "approved_by_user_id": (
            str(a.approved_by_user_id) if a.approved_by_user_id else None
        ),
        "approved_at": a.approved_at.isoformat() if a.approved_at else None,
        "rejection_reason": a.rejection_reason,
        "created_at": a.created_at.isoformat(),
        "updated_at": a.updated_at.isoformat(),
        "created_by_user_id": str(a.created_by_user_id),
    }
    # Financial-field gating: add keys only if caller has view_financials.
    if perms.has("appraisals.view_financials") or perms.is_super_admin:
        d["land_purchase_price"] = str(a.land_purchase_price)
        d["gdv_total"] = str(a.gdv_total)
        d["total_acquisition_cost"] = str(a.total_acquisition_cost)
        d["total_build_cost"] = str(a.total_build_cost)
        d["total_professional_fees"] = str(a.total_professional_fees)
        d["total_statutory_cost"] = str(a.total_statutory_cost)
        d["total_finance_cost"] = str(a.total_finance_cost)
        d["total_contingency"] = str(a.total_contingency)
        d["total_sales_cost"] = str(a.total_sales_cost)
        d["total_other_cost"] = str(a.total_other_cost)
        d["total_cost"] = str(a.total_cost)
        d["profit_total"] = str(a.profit_total)
        d["profit_on_cost_pct"] = str(a.profit_on_cost_pct)
        d["profit_on_gdv_pct"] = str(a.profit_on_gdv_pct)
        d["target_profit_on_cost_pct"] = str(a.target_profit_on_cost_pct)
        d["target_profit_on_gdv_pct"] = str(a.target_profit_on_gdv_pct)
        d["rlv_target_value"] = str(a.rlv_target_value)
        d["rlv_computed_land_value"] = (
            str(a.rlv_computed_land_value)
            if a.rlv_computed_land_value is not None else None
        )
    return d


def _serialise_full(a: Appraisal, perms: UserPermissions) -> dict:
    d = _serialise_header(a, perms)
    d["units"] = [_serialise_unit(u) for u in (a.units or [])]
    can_fin = (
        perms.has("appraisals.view_financials") or perms.is_super_admin
    )
    if can_fin:
        d["cost_lines"] = [_serialise_line(l) for l in (a.cost_lines or [])]
        d["finance_facilities"] = [
            _serialise_fac(f) for f in (a.finance_facilities or [])
        ]
    else:
        # Omit keys entirely (per spec).
        pass
    return d


def _ensure_editable(a: Appraisal) -> None:
    if not is_editable(a):
        raise HTTPException(
            409, f"Appraisal is {a.status!r} — only Draft or Reopened rows may be edited."
        )


def _apply_defaults_on_create(
    db: Session, appraisal: Appraisal, project: Project, user: User,
) -> None:
    """Consume appraisal_default_settings for the tenant + project type.

    Applied KEYS map to Appraisal header fields:
    - default_hurdle_on_cost_pct -> target_profit_on_cost_pct
    - default_hurdle_on_gdv_pct  -> target_profit_on_gdv_pct
    - default_contingency_pct    -> contingency_pct

    Also pre-seeds a set of `Percentage_Of_*` cost lines so the user gets
    the tenant's standard appraisal skeleton out of the box.
    """
    rows = db.scalars(
        select(AppraisalDefaultSetting).where(
            AppraisalDefaultSetting.tenant_id == user.tenant_id,
            or_(
                AppraisalDefaultSetting.applies_to_project_type.is_(None),
                AppraisalDefaultSetting.applies_to_project_type
                == project.project_type,
            ),
        )
    ).all()

    by_key: dict[str, AppraisalDefaultSetting] = {}
    # Specific-project-type rows beat All-type rows.
    for r in rows:
        existing = by_key.get(r.setting_key)
        if existing is None or (
            existing.applies_to_project_type is None
            and r.applies_to_project_type is not None
        ):
            by_key[r.setting_key] = r

    def _val(key: str) -> Optional[Decimal]:
        r = by_key.get(key)
        return Decimal(r.setting_value) if r else None

    if (v := _val("default_hurdle_on_cost_pct")) is not None:
        appraisal.target_profit_on_cost_pct = v
    if (v := _val("default_hurdle_on_gdv_pct")) is not None:
        appraisal.target_profit_on_gdv_pct = v
    if (v := _val("default_contingency_pct")) is not None:
        appraisal.contingency_pct = v

    # Seed Percentage_Of_* lines where defaults exist. These become
    # the starting cost-line skeleton.
    pct_seeds: list[tuple[str, str, str, str]] = [
        # (setting_key, label, category, auto_source)
        ("default_architect_fee_pct", "Architect fees",
         "Professional_Fees", "Percentage_Of_Build_Cost"),
        ("default_structural_fee_pct", "Structural engineer fees",
         "Professional_Fees", "Percentage_Of_Build_Cost"),
        ("default_qs_fee_pct", "Quantity surveyor fees",
         "Professional_Fees", "Percentage_Of_Build_Cost"),
        ("default_prelims_pct", "Preliminaries",
         "Construction", "Percentage_Of_Build_Cost"),
        ("default_mc_oh_p_pct", "Main contractor OH&P",
         "Construction", "Percentage_Of_Build_Cost"),
        ("default_selling_agents_pct", "Selling agents",
         "Sales", "Percentage_Of_GDV"),
        ("default_legal_on_sale_pct", "Legal fees on sale",
         "Sales", "Percentage_Of_GDV"),
        ("default_contingency_pct", "Contingency",
         "Contingency", "Percentage_Of_Build_Cost"),
    ]
    order = 10
    for (key, label, cat, src) in pct_seeds:
        v = _val(key)
        if v is None:
            continue
        db.add(AppraisalCostLine(
            appraisal_id=appraisal.id,
            display_order=order,
            label=label,
            category=cat,
            auto_source=src,
            percentage=v,
            amount=Decimal("0"),
        ))
        order += 10

    # Always seed an SDLT_Engine line (recomputed on every save).
    db.add(AppraisalCostLine(
        appraisal_id=appraisal.id,
        display_order=1,
        label="Stamp Duty Land Tax",
        category="Acquisition",
        auto_source="SDLT_Engine",
        amount=Decimal("0"),
    ))
    # Finance_Engine aggregator line.
    db.add(AppraisalCostLine(
        appraisal_id=appraisal.id,
        display_order=500,
        label="Finance cost (auto)",
        category="Finance",
        auto_source="Finance_Engine",
        amount=Decimal("0"),
    ))
    db.flush()


def _validate_enums(line: CostLineIn) -> None:
    if line.category not in COST_CATEGORIES:
        raise HTTPException(400, f"Unknown category: {line.category}")
    if line.auto_source not in AUTO_SOURCES:
        raise HTTPException(400, f"Unknown auto_source: {line.auto_source}")


def _validate_unit_enums(u: UnitIn) -> None:
    if u.unit_type not in UNIT_TYPES:
        raise HTTPException(400, f"Unknown unit_type: {u.unit_type}")
    if u.tenure not in TENURE_TYPES:
        raise HTTPException(400, f"Unknown tenure: {u.tenure}")


def _validate_facility_enums(f: FacilityIn) -> None:
    if f.facility_type not in FINANCE_TYPES:
        raise HTTPException(400, f"Unknown facility_type: {f.facility_type}")
    if f.interest_mode not in INTEREST_MODES:
        raise HTTPException(400, f"Unknown interest_mode: {f.interest_mode}")


# ---------------------------------------------------------------------
# Project-scoped endpoints
# ---------------------------------------------------------------------

@router.get("/projects/{project_id}/appraisals")
def list_appraisals(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    _load_project(db, project_id, current, perms)
    rows = db.scalars(
        select(Appraisal)
        .where(Appraisal.project_id == project_id)
        .order_by(Appraisal.version_number.desc())
    ).all()
    return {
        "project_id": str(project_id),
        "items": [_serialise_header(r, perms) for r in rows],
        "count": len(rows),
    }


@router.post("/projects/{project_id}/appraisals", status_code=201)
def create_appraisal(
    project_id: uuid.UUID,
    body: AppraisalCreate,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.create")),
    db: Session = Depends(get_db),
):
    if body.sdlt_category not in SDLT_CATEGORIES:
        raise HTTPException(400, f"Unknown sdlt_category: {body.sdlt_category}")
    project = _load_project(db, project_id, current, perms)
    ref_date = body.reference_date or date.today()
    scenario = "Base"
    version = next_version_for_project(db, project_id, scenario)

    # Reuse the project's existing appraisal_group_id if any; else mint one.
    existing_group_id = db.scalar(
        select(Appraisal.appraisal_group_id)
        .where(Appraisal.project_id == project_id)
        .limit(1)
    )
    group_id = existing_group_id or uuid.uuid4()

    # Demote any existing is_current row for this (project, scenario) to
    # honour partial unique uq_appraisals_current_per_project_scenario.
    existing_currents = db.scalars(
        select(Appraisal).where(
            Appraisal.project_id == project_id,
            Appraisal.scenario == scenario,
            Appraisal.is_current.is_(True),
        )
    ).all()
    for ec in existing_currents:
        ec.is_current = False
    if existing_currents:
        db.flush()

    a = Appraisal(
        project_id=project_id,
        appraisal_group_id=group_id,
        scenario=scenario,
        is_current=True,
        version_number=version,
        name=body.name,
        status="Draft",
        reference_date=ref_date,
        land_purchase_price=Decimal(body.land_purchase_price),
        sdlt_category=body.sdlt_category,
        developer_relief=body.developer_relief,
        project_duration_months=body.project_duration_months,
        notes=body.notes,
        created_by_user_id=current.id,
    )
    db.add(a)
    db.flush()
    _apply_defaults_on_create(db, a, project, current)
    # Initial recompute.
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Create", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=project_id, field_changes=[],
        metadata={"version": version, "project_id": str(project_id)},
        request=request,
    )
    db.commit()
    db.refresh(a)
    return _serialise_full(a, perms)


# ---------------------------------------------------------------------
# Appraisal-scoped read / edit
# ---------------------------------------------------------------------

@router.get("/appraisals/{appraisal_id}")
def get_appraisal(
    appraisal_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    return _serialise_full(a, perms)


@router.put("/appraisals/{appraisal_id}")
def update_appraisal(
    appraisal_id: uuid.UUID,
    body: AppraisalHeaderUpdate,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)

    if body.sdlt_category is not None and body.sdlt_category not in SDLT_CATEGORIES:
        raise HTTPException(400, f"Unknown sdlt_category: {body.sdlt_category}")
    if body.rlv_target_basis is not None and body.rlv_target_basis not in ("on_cost", "on_gdv"):
        raise HTTPException(400, "rlv_target_basis must be on_cost or on_gdv")

    before = {
        "name": a.name,
        "reference_date": a.reference_date.isoformat(),
        "land_purchase_price": str(a.land_purchase_price),
        "sdlt_category": a.sdlt_category,
        "developer_relief": a.developer_relief,
        "contingency_pct": str(a.contingency_pct),
        "target_profit_on_cost_pct": str(a.target_profit_on_cost_pct),
        "target_profit_on_gdv_pct": str(a.target_profit_on_gdv_pct),
        "project_duration_months": a.project_duration_months,
        "rlv_enabled": a.rlv_enabled,
        "rlv_target_basis": a.rlv_target_basis,
        "rlv_target_value": str(a.rlv_target_value),
        "notes": a.notes,
    }
    payload = body.model_dump(exclude_unset=True)
    for k, v in payload.items():
        if v is None:
            continue
        setattr(a, k, v)
    a.is_stale = True
    db.flush()

    appraisal_calc.recompute(db, a)
    after = {
        "name": a.name,
        "reference_date": a.reference_date.isoformat(),
        "land_purchase_price": str(a.land_purchase_price),
        "sdlt_category": a.sdlt_category,
        "developer_relief": a.developer_relief,
        "contingency_pct": str(a.contingency_pct),
        "target_profit_on_cost_pct": str(a.target_profit_on_cost_pct),
        "target_profit_on_gdv_pct": str(a.target_profit_on_gdv_pct),
        "project_duration_months": a.project_duration_months,
        "rlv_enabled": a.rlv_enabled,
        "rlv_target_basis": a.rlv_target_basis,
        "rlv_target_value": str(a.rlv_target_value),
        "notes": a.notes,
    }
    record_audit(
        db, action="Update", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=field_diff(before, after),
        metadata={"kind": "header_update"}, request=request,
    )
    db.commit()
    db.refresh(a)
    return _serialise_full(a, perms)


@router.post("/appraisals/{appraisal_id}/recompute")
def recompute_appraisal(
    appraisal_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Update", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"kind": "manual_recompute"}, request=request,
    )
    db.commit()
    db.refresh(a)
    return _serialise_full(a, perms)


@router.post("/appraisals/{appraisal_id}/recalculate-rlv")
def recalculate_rlv(
    appraisal_id: uuid.UUID,
    body: RlvRequestIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    basis = body.basis or a.rlv_target_basis
    target = (body.target_pct if body.target_pct is not None
              else a.rlv_target_value)
    res = rlv_solver.solve(db, a, basis=basis, target_pct=Decimal(target))
    a.rlv_enabled = True
    a.rlv_target_basis = basis
    a.rlv_target_value = Decimal(target)
    a.rlv_computed_land_value = res.land_value
    a.rlv_iterations = res.iterations
    a.rlv_converged = res.converged
    a.rlv_computed_at = datetime.now(timezone.utc)
    # Re-run canonical recompute at the header's actual land price so
    # the KPIs don't reflect the solver's final probe price.
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Update", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={
            "kind": "rlv_recalculate", "basis": basis,
            "target_pct": str(target),
            "converged": res.converged, "iterations": res.iterations,
            "computed_land_value": str(res.land_value),
            "message": res.message,
        },
        request=request,
    )
    db.commit()
    db.refresh(a)
    return {
        "converged": res.converged,
        "iterations": res.iterations,
        "basis": basis,
        "target_pct": str(target),
        "achieved_pct": str(res.achieved_pct),
        "computed_land_value": str(res.land_value),
        "message": res.message,
        "appraisal": _serialise_full(a, perms),
    }


# ---------------------------------------------------------------------
# State machine endpoints
# ---------------------------------------------------------------------

@router.post("/appraisals/{appraisal_id}/submit")
def submit_appraisal(
    appraisal_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.submit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    try:
        assert_transition(a.status, "Submitted")
    except TransitionError as e:
        raise HTTPException(409, str(e))
    a.status = "Submitted"
    a.submitted_by_user_id = current.id
    a.submitted_at = datetime.now(timezone.utc)
    record_audit(
        db, action="Submit", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"kind": "state_transition", "to": "Submitted"},
        request=request,
    )
    db.commit()
    db.refresh(a)
    return _serialise_header(a, perms)


@router.post("/appraisals/{appraisal_id}/approve")
def approve_appraisal(
    appraisal_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.approve")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    try:
        assert_transition(a.status, "Approved")
    except TransitionError as e:
        raise HTTPException(409, str(e))
    a.status = "Approved"
    a.approved_by_user_id = current.id
    a.approved_at = datetime.now(timezone.utc)
    meta = stamp_self_approval(
        {"kind": "state_transition", "to": "Approved"},
        current.id, a.submitted_by_user_id,
    )
    record_audit(
        db, action="Approve", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata=meta, request=request,
    )
    db.commit()
    db.refresh(a)
    return _serialise_header(a, perms)


@router.post("/appraisals/{appraisal_id}/reject")
def reject_appraisal(
    appraisal_id: uuid.UUID,
    body: WorkflowActionIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.approve")),
    db: Session = Depends(get_db),
):
    if not body.reason or len(body.reason.strip()) < 5:
        raise HTTPException(400, "A rejection reason (min 5 chars) is required.")
    a = _load_appraisal(db, appraisal_id, current, perms)
    try:
        assert_transition(a.status, "Rejected")
    except TransitionError as e:
        raise HTTPException(409, str(e))
    a.status = "Rejected"
    a.rejection_reason = body.reason.strip()
    record_audit(
        db, action="Reject", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"kind": "state_transition", "to": "Rejected",
                  "reason": body.reason.strip()},
        request=request,
    )
    db.commit()
    db.refresh(a)
    return _serialise_header(a, perms)


@router.post("/appraisals/{appraisal_id}/withdraw")
def withdraw_appraisal(
    appraisal_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    """Withdraw an in-flight appraisal — Phase F (2.3 retrofit).

    Allowed sources: Draft, Submitted, Reopened. Sets status='Withdrawn',
    is_current=false. No submitter restriction (2.2 behaviour change —
    documented in CHANGELOG).
    """
    a = _load_appraisal(db, appraisal_id, current, perms)
    if a.status not in ("Draft", "Submitted", "Reopened"):
        raise HTTPException(
            400,
            detail={
                "code": "NOT_WITHDRAWABLE",
                "message": (
                    f"Cannot withdraw appraisal in status {a.status!r}. "
                    "Only Draft, Submitted, or Reopened may be withdrawn."
                ),
            },
        )
    a.status = "Withdrawn"
    a.is_current = False
    record_audit(
        db, action="Appraisal.Withdraw", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"kind": "state_transition", "to": "Withdrawn"},
        request=request,
    )
    db.commit()
    db.refresh(a)
    return _serialise_header(a, perms)


@router.post("/appraisals/{appraisal_id}/reopen")
def reopen_appraisal(
    appraisal_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    """Reopen Approved (clone, legacy) or Rejected (toggle to Reopened).

    TODO 2.3 C2: split /reopen and /new-version per Phase B.2 of v6 prompt.
    In C1 we retain the Approved-clone path so existing 2.2 clone tests pass
    post-rename. C2 will move clone behaviour into a new POST /new-version
    endpoint (with revision_reason + summary_of_changes body, writing an
    appraisal_revisions row in the same transaction). After C2:
      - /reopen handles Approved AND Rejected by toggling status='Reopened'
        (no clone, no version bump, is_current unchanged).
      - /new-version handles the Approved/Rejected → clone → Draft path.
    """
    a = _load_appraisal(db, appraisal_id, current, perms)

    if a.status == "Rejected":
        # Rewritten in 2.3: target is now Reopened (was Draft in 2.2).
        try:
            assert_transition(a.status, "Reopened")
        except TransitionError as e:
            raise HTTPException(409, str(e))
        a.status = "Reopened"
        a.rejection_reason = None
        # is_current unchanged per Phase B.2 matrix.
        record_audit(
            db, action="Reopen", resource_type="appraisals",
            resource_id=a.id, actor_user_id=current.id,
            project_id=a.project_id, field_changes=[],
            metadata={"kind": "state_transition", "to": "Reopened",
                      "from": "Rejected"},
            request=request,
        )
        db.commit()
        db.refresh(a)
        return _serialise_header(a, perms)

    if a.status == "Approved":
        # Legacy clone path retained for C1. Atomic is_current handover:
        # source flips to false BEFORE new row flips to true so the partial
        # unique uq_appraisals_current_per_project_scenario never sees two
        # currents simultaneously.
        a.is_current = False
        db.flush()
        new = clone_as_new_version(db, a, created_by_user_id=current.id)
        mark_superseded(a)
        new.is_current = True
        db.flush()
        appraisal_calc.recompute(db, new)
        record_audit(
            db, action="Reopen", resource_type="appraisals",
            resource_id=new.id, actor_user_id=current.id,
            project_id=a.project_id, field_changes=[],
            metadata={"kind": "new_version_clone",
                      "previous_version_id": str(a.id),
                      "new_version": new.version_number},
            request=request,
        )
        db.commit()
        db.refresh(new)
        return _serialise_full(new, perms)

    raise HTTPException(409, f"Cannot reopen an appraisal in status {a.status!r}.")


# ---------------------------------------------------------------------
# Unit CRUD
# ---------------------------------------------------------------------

@router.post("/appraisals/{appraisal_id}/units", status_code=201)
def add_unit(
    appraisal_id: uuid.UUID,
    body: UnitIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    _validate_unit_enums(body)
    u = AppraisalUnit(appraisal_id=a.id, **body.model_dump())
    db.add(u)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Create", resource_type="appraisal_units",
        resource_id=u.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"appraisal_id": str(a.id), "label": u.unit_label},
        request=request,
    )
    db.commit()
    db.refresh(u)
    return _serialise_unit(u)


@router.put("/appraisals/{appraisal_id}/units/{unit_id}")
def update_unit(
    appraisal_id: uuid.UUID,
    unit_id: uuid.UUID,
    body: UnitIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    _validate_unit_enums(body)
    u = db.get(AppraisalUnit, unit_id)
    if u is None or u.appraisal_id != a.id:
        raise HTTPException(404, "Unit not found")
    before = _serialise_unit(u)
    for k, v in body.model_dump().items():
        setattr(u, k, v)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Update", resource_type="appraisal_units",
        resource_id=u.id, actor_user_id=current.id,
        project_id=a.project_id,
        field_changes=field_diff(before, _serialise_unit(u)),
        metadata={"appraisal_id": str(a.id)}, request=request,
    )
    db.commit()
    db.refresh(u)
    return _serialise_unit(u)


@router.delete("/appraisals/{appraisal_id}/units/{unit_id}", status_code=204)
def delete_unit(
    appraisal_id: uuid.UUID,
    unit_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    u = db.get(AppraisalUnit, unit_id)
    if u is None or u.appraisal_id != a.id:
        raise HTTPException(404, "Unit not found")
    db.delete(u)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Delete", resource_type="appraisal_units",
        resource_id=unit_id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"appraisal_id": str(a.id)}, request=request,
    )
    db.commit()
    return None


# ---------------------------------------------------------------------
# Cost line CRUD
# ---------------------------------------------------------------------

@router.post("/appraisals/{appraisal_id}/cost-lines", status_code=201)
def add_cost_line(
    appraisal_id: uuid.UUID,
    body: CostLineIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    _validate_enums(body)
    l = AppraisalCostLine(appraisal_id=a.id, **body.model_dump())
    db.add(l)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Create", resource_type="appraisal_cost_lines",
        resource_id=l.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"appraisal_id": str(a.id), "label": l.label}, request=request,
    )
    db.commit()
    db.refresh(l)
    return _serialise_line(l)


@router.put("/appraisals/{appraisal_id}/cost-lines/{line_id}")
def update_cost_line(
    appraisal_id: uuid.UUID,
    line_id: uuid.UUID,
    body: CostLineIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    _validate_enums(body)
    l = db.get(AppraisalCostLine, line_id)
    if l is None or l.appraisal_id != a.id:
        raise HTTPException(404, "Cost line not found")
    if l.is_locked and not perms.is_super_admin:
        raise HTTPException(409, "Cost line is locked.")
    before = _serialise_line(l)
    for k, v in body.model_dump().items():
        setattr(l, k, v)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Update", resource_type="appraisal_cost_lines",
        resource_id=l.id, actor_user_id=current.id,
        project_id=a.project_id,
        field_changes=field_diff(before, _serialise_line(l)),
        metadata={"appraisal_id": str(a.id)}, request=request,
    )
    db.commit()
    db.refresh(l)
    return _serialise_line(l)


@router.delete("/appraisals/{appraisal_id}/cost-lines/{line_id}", status_code=204)
def delete_cost_line(
    appraisal_id: uuid.UUID,
    line_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    l = db.get(AppraisalCostLine, line_id)
    if l is None or l.appraisal_id != a.id:
        raise HTTPException(404, "Cost line not found")
    if l.is_locked and not perms.is_super_admin:
        raise HTTPException(409, "Cost line is locked.")
    db.delete(l)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Delete", resource_type="appraisal_cost_lines",
        resource_id=line_id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"appraisal_id": str(a.id)}, request=request,
    )
    db.commit()
    return None


# ---------------------------------------------------------------------
# Finance facility CRUD
# ---------------------------------------------------------------------

@router.post("/appraisals/{appraisal_id}/finance", status_code=201)
def add_finance_facility(
    appraisal_id: uuid.UUID,
    body: FacilityIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    _validate_facility_enums(body)
    f = AppraisalFinanceFacility(appraisal_id=a.id, **body.model_dump())
    db.add(f)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Create", resource_type="appraisal_finance_model",
        resource_id=f.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"appraisal_id": str(a.id), "label": f.label}, request=request,
    )
    db.commit()
    db.refresh(f)
    return _serialise_fac(f)


@router.put("/appraisals/{appraisal_id}/finance/{fac_id}")
def update_finance_facility(
    appraisal_id: uuid.UUID,
    fac_id: uuid.UUID,
    body: FacilityIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    _validate_facility_enums(body)
    f = db.get(AppraisalFinanceFacility, fac_id)
    if f is None or f.appraisal_id != a.id:
        raise HTTPException(404, "Facility not found")
    before = _serialise_fac(f)
    for k, v in body.model_dump().items():
        setattr(f, k, v)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Update", resource_type="appraisal_finance_model",
        resource_id=f.id, actor_user_id=current.id,
        project_id=a.project_id,
        field_changes=field_diff(before, _serialise_fac(f)),
        metadata={"appraisal_id": str(a.id)}, request=request,
    )
    db.commit()
    db.refresh(f)
    return _serialise_fac(f)


@router.delete("/appraisals/{appraisal_id}/finance/{fac_id}", status_code=204)
def delete_finance_facility(
    appraisal_id: uuid.UUID,
    fac_id: uuid.UUID,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    _ensure_editable(a)
    f = db.get(AppraisalFinanceFacility, fac_id)
    if f is None or f.appraisal_id != a.id:
        raise HTTPException(404, "Facility not found")
    db.delete(f)
    db.flush()
    a.is_stale = True
    appraisal_calc.recompute(db, a)
    record_audit(
        db, action="Delete", resource_type="appraisal_finance_model",
        resource_id=fac_id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={"appraisal_id": str(a.id)}, request=request,
    )
    db.commit()
    return None
