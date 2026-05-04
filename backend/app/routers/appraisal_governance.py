"""Appraisal governance endpoints — Prompt 2.3 Checkpoint 2.

Routes mounted alongside the existing /api/v1/appraisals router:

- POST   /appraisals/{id}/new-version
- GET    /appraisals/{id}/revisions
- GET    /projects/{project_id}/revisions
- POST   /appraisals/{base_id}/scenarios
- GET    /appraisal-groups/{group_id}/scenarios
- GET    /appraisal-groups/{group_id}/comparator
- POST   /appraisals/{id}/decisions
- GET    /appraisals/{id}/decisions
- GET    /projects/{project_id}/nudge
"""
from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.db import get_db
from app.models.appraisal_governance import (
    APPRAISAL_REVISION_REASONS, AppraisalDecisionLog, AppraisalRevision,
    AppraisalScenario, DECISION_TYPES,
)
from app.models.appraisals import Appraisal
from app.models.user import User
from app.routers.appraisals import (
    _load_appraisal, _load_project, _serialise_full, _serialise_header,
)
from app.services import (
    appraisal_decisions as decisions_svc,
    appraisal_revisions as revisions_svc,
    appraisal_scenarios as scenarios_svc,
)
from app.services.audit import record_audit


router = APIRouter(tags=["appraisal-governance"])


# ---------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------

class NewVersionIn(BaseModel):
    revision_reason: str
    summary_of_changes: str = Field(min_length=10)


class CreateScenarioIn(BaseModel):
    scenario_label: str
    scenario_description: str = Field(min_length=10)


class LogDecisionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appraisal_version: int
    decision_type: str
    decision_date: date
    decision_rationale: str = Field(min_length=10)
    conditions: Optional[str] = None
    key_assumptions_challenged: Optional[str] = None
    supporting_documents: list[Any] = Field(default_factory=list)
    correction_of_decision_id: Optional[uuid.UUID] = None


# ---------------------------------------------------------------------
# Serialisers
# ---------------------------------------------------------------------

def _serialise_revision(r: AppraisalRevision) -> dict:
    return {
        "id": str(r.id),
        "from_version": r.from_version,
        "to_version": r.to_version,
        "appraisal_id_from": str(r.appraisal_id_from),
        "appraisal_id_to": str(r.appraisal_id_to),
        "revision_reason": r.revision_reason,
        "summary_of_changes": r.summary_of_changes,
        "delta_gdv": str(r.delta_gdv),
        "delta_total_cost": str(r.delta_total_cost),
        "delta_profit": str(r.delta_profit),
        "revised_by_user_id": str(r.revised_by_user_id),
        "created_at": r.created_at.isoformat(),
    }


def _serialise_decision(d: AppraisalDecisionLog) -> dict:
    return {
        "id": str(d.id),
        "appraisal_id": str(d.appraisal_id),
        "appraisal_version": d.appraisal_version,
        "decision_type": d.decision_type,
        "decision_maker_user_id": str(d.decision_maker_user_id),
        "decision_date": d.decision_date.isoformat(),
        "decision_rationale": d.decision_rationale,
        "conditions": d.conditions,
        "key_assumptions_challenged": d.key_assumptions_challenged,
        "supporting_documents": list(d.supporting_documents or []),
        "correction_of_decision_id": (
            str(d.correction_of_decision_id)
            if d.correction_of_decision_id else None
        ),
        "created_at": d.created_at.isoformat(),
    }


# ---------------------------------------------------------------------
# POST /appraisals/{id}/new-version
# ---------------------------------------------------------------------

@router.post("/appraisals/{appraisal_id}/new-version", status_code=201)
def create_new_version(
    appraisal_id: uuid.UUID,
    body: NewVersionIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    if body.revision_reason not in APPRAISAL_REVISION_REASONS:
        raise HTTPException(
            400,
            detail={
                "code": "INVALID_REVISION_REASON",
                "message": f"Unknown revision_reason: {body.revision_reason}",
            },
        )
    source = _load_appraisal(db, appraisal_id, current, perms)
    try:
        new, rev = revisions_svc.create_new_version(
            db, source,
            revision_reason=body.revision_reason,
            summary_of_changes=body.summary_of_changes,
            actor_user_id=current.id,
        )
    except revisions_svc.RevisionError as e:
        raise HTTPException(e.http_status,
                            detail={"code": e.code, "message": e.message})

    record_audit(
        db, action="Appraisal.NewVersion", resource_type="appraisals",
        resource_id=new.id, actor_user_id=current.id,
        project_id=new.project_id, field_changes=[],
        metadata={
            "kind": "new_version",
            "from_version": source.version_number,
            "to_version": new.version_number,
            "revision_reason": body.revision_reason,
            "source_appraisal_id": str(source.id),
            "target_appraisal_id": str(new.id),
            "scenario": new.scenario,
            "appraisal_group_id": str(new.appraisal_group_id),
        },
        request=request,
    )
    db.commit()
    db.refresh(new)
    db.refresh(rev)
    return {
        "appraisal": _serialise_full(new, perms),
        "revision": _serialise_revision(rev),
    }


# ---------------------------------------------------------------------
# GET /appraisals/{id}/revisions — lineage for this (group, scenario)
# ---------------------------------------------------------------------

@router.get("/appraisals/{appraisal_id}/revisions")
def list_revisions_for_appraisal(
    appraisal_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    appraisals = db.scalars(
        select(Appraisal).where(
            Appraisal.appraisal_group_id == a.appraisal_group_id,
            Appraisal.scenario == a.scenario,
        ).order_by(Appraisal.version_number.asc())
    ).all()
    app_ids = [x.id for x in appraisals]
    revisions = db.scalars(
        select(AppraisalRevision)
        .where(AppraisalRevision.appraisal_id_to.in_(app_ids))
        .order_by(AppraisalRevision.to_version.asc())
    ).all()
    return {
        "appraisals": [_serialise_header(x, perms) for x in appraisals],
        "revisions": [_serialise_revision(r) for r in revisions],
    }


# ---------------------------------------------------------------------
# GET /projects/{project_id}/revisions — per-group per-scenario lineage
# ---------------------------------------------------------------------

@router.get("/projects/{project_id}/revisions")
def list_revisions_for_project(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    _load_project(db, project_id, current, perms)
    appraisals = db.scalars(
        select(Appraisal)
        .where(Appraisal.project_id == project_id)
        .order_by(Appraisal.version_number.asc())
    ).all()
    if not appraisals:
        return {"groups": []}

    groups: dict[uuid.UUID, dict[str, list[Appraisal]]] = {}
    for a in appraisals:
        groups.setdefault(a.appraisal_group_id, {}).setdefault(
            a.scenario, []).append(a)

    revisions = db.scalars(
        select(AppraisalRevision)
        .where(
            AppraisalRevision.appraisal_id_to.in_([a.id for a in appraisals])
        )
    ).all()
    rev_by_to_id = {r.appraisal_id_to: r for r in revisions}

    order = ("Base", "Upside", "Downside", "Sensitivity")
    out_groups = []
    for gid, by_scenario in groups.items():
        scenarios = []
        for label in order:
            rows = by_scenario.get(label)
            if not rows:
                continue
            scenarios.append({
                "scenario": label,
                "appraisals": [_serialise_header(x, perms) for x in rows],
                "revisions": [
                    _serialise_revision(rev_by_to_id[x.id])
                    for x in rows if x.id in rev_by_to_id
                ],
            })
        out_groups.append({
            "appraisal_group_id": str(gid),
            "scenarios": scenarios,
        })
    return {"groups": out_groups}


# ---------------------------------------------------------------------
# POST /appraisals/{base_id}/scenarios — create Upside/Downside/Sensitivity
# ---------------------------------------------------------------------

@router.post("/appraisals/{base_id}/scenarios", status_code=201)
def create_scenario(
    base_id: uuid.UUID,
    body: CreateScenarioIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.edit")),
    db: Session = Depends(get_db),
):
    base = _load_appraisal(db, base_id, current, perms)
    try:
        new, row = scenarios_svc.create_scenario(
            db, base,
            scenario_label=body.scenario_label,
            scenario_description=body.scenario_description,
            actor_user_id=current.id,
        )
    except scenarios_svc.ScenarioError as e:
        raise HTTPException(e.http_status,
                            detail={"code": e.code, "message": e.message})

    record_audit(
        db, action="Appraisal.ScenarioCreate", resource_type="appraisals",
        resource_id=new.id, actor_user_id=current.id,
        project_id=new.project_id, field_changes=[],
        metadata={
            "scenario_label": body.scenario_label,
            "appraisal_group_id": str(new.appraisal_group_id),
            "base_appraisal_id": str(base.id),
            "scenario_appraisal_id": str(new.id),
        },
        request=request,
    )
    db.commit()
    db.refresh(new)
    db.refresh(row)
    return {
        "appraisal": _serialise_full(new, perms),
        "scenario": {
            "id": str(row.id),
            "appraisal_group_id": str(row.appraisal_group_id),
            "scenario_appraisal_id": str(row.scenario_appraisal_id),
            "parent_scenario_appraisal_id": (
                str(row.parent_scenario_appraisal_id)
                if row.parent_scenario_appraisal_id else None
            ),
            "scenario_label": row.scenario_label,
            "scenario_description": row.scenario_description,
            "created_at": row.created_at.isoformat(),
            "created_by_user_id": str(row.created_by_user_id),
        },
    }


# ---------------------------------------------------------------------
# GET /appraisal-groups/{group_id}/scenarios
# ---------------------------------------------------------------------

def _verify_group_access(
    db: Session, group_id: uuid.UUID, current: User, perms: UserPermissions,
) -> None:
    """Verify caller has access to at least one appraisal in this group."""
    sample = db.execute(
        select(Appraisal).where(
            Appraisal.appraisal_group_id == group_id,
        ).limit(1)
    ).scalar_one_or_none()
    if sample is None:
        raise HTTPException(404, "Appraisal group not found")
    # Re-use the appraisal loader's project-scope check by loading the
    # sample appraisal through it; raises 404 on scope miss.
    _load_appraisal(db, sample.id, current, perms)


@router.get("/appraisal-groups/{group_id}/scenarios")
def list_group_scenarios(
    group_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    _verify_group_access(db, group_id, current, perms)
    return {
        "appraisal_group_id": str(group_id),
        "scenarios": scenarios_svc.list_group_scenarios(db, group_id),
    }


# ---------------------------------------------------------------------
# GET /appraisal-groups/{group_id}/comparator
# ---------------------------------------------------------------------

@router.get("/appraisal-groups/{group_id}/comparator")
def group_comparator(
    group_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    _verify_group_access(db, group_id, current, perms)
    return scenarios_svc.get_group_comparator(db, group_id)


# ---------------------------------------------------------------------
# POST /appraisals/{id}/decisions — permission: appraisals.approve
# ---------------------------------------------------------------------

@router.post("/appraisals/{appraisal_id}/decisions", status_code=201)
def log_decision(
    appraisal_id: uuid.UUID,
    body: LogDecisionIn,
    request: Request,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.approve")),
    db: Session = Depends(get_db),
):
    if body.decision_type not in DECISION_TYPES:
        raise HTTPException(
            400,
            detail={
                "code": "INVALID_DECISION_TYPE",
                "message": f"Unknown decision_type: {body.decision_type}",
            },
        )
    a = _load_appraisal(db, appraisal_id, current, perms)
    try:
        row = decisions_svc.log_decision(
            db,
            appraisal=a,
            appraisal_version=body.appraisal_version,
            decision_type=body.decision_type,
            decision_date=body.decision_date,
            decision_rationale=body.decision_rationale,
            conditions=body.conditions,
            key_assumptions_challenged=body.key_assumptions_challenged,
            supporting_documents=body.supporting_documents,
            correction_of_decision_id=body.correction_of_decision_id,
            actor_user_id=current.id,
        )
    except decisions_svc.DecisionError as e:
        raise HTTPException(e.http_status,
                            detail={"code": e.code, "message": e.message})

    record_audit(
        db, action="Appraisal.DecisionLog", resource_type="appraisals",
        resource_id=a.id, actor_user_id=current.id,
        project_id=a.project_id, field_changes=[],
        metadata={
            "decision_id": str(row.id),
            "decision_type": body.decision_type,
            "appraisal_version": body.appraisal_version,
            "decision_date": body.decision_date.isoformat(),
        },
        request=request,
    )
    db.commit()
    db.refresh(row)
    return _serialise_decision(row)


# ---------------------------------------------------------------------
# GET /appraisals/{id}/decisions
# ---------------------------------------------------------------------

@router.get("/appraisals/{appraisal_id}/decisions")
def list_decisions(
    appraisal_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    a = _load_appraisal(db, appraisal_id, current, perms)
    rows = decisions_svc.list_for_appraisal(db, a.id, limit=limit)
    return {
        "appraisal_id": str(a.id),
        "items": [_serialise_decision(r) for r in rows],
        "count": len(rows),
    }


# ---------------------------------------------------------------------
# GET /projects/{project_id}/nudge
# ---------------------------------------------------------------------

@router.get("/projects/{project_id}/nudge")
def get_nudge(
    project_id: uuid.UUID,
    current: User = Depends(get_current_user),
    perms: UserPermissions = Depends(require_permission("appraisals.view")),
    db: Session = Depends(get_db),
):
    _load_project(db, project_id, current, perms)
    return decisions_svc.get_nudge_state(db, project_id, current.id)
