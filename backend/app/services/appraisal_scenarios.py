"""Appraisal scenarios service — Prompt 2.3 Checkpoint 2 (Phase D.1).

Three operations:
- create_scenario — spawns Upside/Downside/Sensitivity from a Base v1 row.
- list_group_scenarios — ordered list of scenario metadata + current appraisal.
- get_group_comparator — absolute-values comparator payload.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.appraisals import Appraisal
from app.models.appraisal_governance import AppraisalScenario
from app.services import appraisal_calc
from app.services.appraisal_versioning import clone_as_new_version


SCENARIO_ORDER = ("Base", "Upside", "Downside", "Sensitivity")


class ScenarioError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def create_scenario(
    db: Session,
    base_appraisal: Appraisal,
    *,
    scenario_label: str,
    scenario_description: str,
    actor_user_id: uuid.UUID,
) -> tuple[Appraisal, AppraisalScenario]:
    """Spawn a non-Base scenario clone from a Base v1 appraisal.

    Preconditions:
    - scenario_label IN {Upside, Downside, Sensitivity}.
    - base_appraisal.scenario == 'Base'.
    - base_appraisal is the originating Base v1 (row exists in
      appraisal_scenarios with scenario_label='Base' pointing at it).
    - base_appraisal.status NOT IN {Withdrawn, Superseded}.
    - No existing scenario row for (group_id, scenario_label) already.

    The new clone:
    - gets a fresh version_number=1 in its own (project, scenario) slot.
    - status='Draft', is_current=True.
    - inherits appraisal_group_id + project_id from Base.
    - Base.is_current stays TRUE (different (project, scenario) tuple — the
      partial unique permits both currents to coexist).

    Caller commits.
    """
    if scenario_label not in ("Upside", "Downside", "Sensitivity"):
        raise ScenarioError(
            code="INVALID_SCENARIO_LABEL",
            message=(
                f"scenario_label must be Upside, Downside, or Sensitivity; "
                f"got {scenario_label!r}."
            ),
            http_status=400,
        )
    description = (scenario_description or "").strip()
    if len(description) < 10:
        raise ScenarioError(
            code="SCENARIO_DESCRIPTION_TOO_SHORT",
            message="scenario_description must be at least 10 characters.",
            http_status=400,
        )
    if base_appraisal.scenario != "Base":
        raise ScenarioError(
            code="NOT_BASE_APPRAISAL",
            message=(
                "Scenarios must be spawned from the Base appraisal. "
                f"Source scenario is {base_appraisal.scenario!r}."
            ),
            http_status=400,
        )
    if base_appraisal.status in ("Withdrawn", "Superseded"):
        raise ScenarioError(
            code="SOURCE_APPRAISAL_NOT_AVAILABLE",
            message=(
                f"Cannot spawn scenario from a {base_appraisal.status!r} "
                f"Base. Use the current Base version."
            ),
            http_status=400,
        )
    # Base v1 check: scenario_appraisal_id must match a Base-anchor row.
    anchor = db.execute(
        select(AppraisalScenario).where(
            AppraisalScenario.appraisal_group_id
            == base_appraisal.appraisal_group_id,
            AppraisalScenario.scenario_label == "Base",
        )
    ).scalar_one_or_none()
    if anchor is None or anchor.scenario_appraisal_id != base_appraisal.id:
        raise ScenarioError(
            code="NOT_BASE_APPRAISAL",
            message=(
                "The referenced appraisal is not the Base v1 anchor for "
                "its group."
            ),
            http_status=400,
        )
    # Uniqueness pre-check (DB UNIQUE catches as fallback).
    existing = db.execute(
        select(AppraisalScenario).where(
            AppraisalScenario.appraisal_group_id
            == base_appraisal.appraisal_group_id,
            AppraisalScenario.scenario_label == scenario_label,
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ScenarioError(
            code="SCENARIO_LABEL_EXISTS",
            message=(
                f"Scenario {scenario_label!r} already exists for this group."
            ),
            http_status=409,
        )

    # Clone WITHOUT bumping version_number inside the source scenario
    # (new scenario starts its own v1). We can't use clone_as_new_version
    # directly because it increments version_number in the SOURCE scenario
    # slot. Inline the minimal clone logic mirroring appraisal_versioning.
    new = clone_as_new_version(db, base_appraisal, created_by_user_id=actor_user_id)
    # clone_as_new_version bumped version inside the Base slot. Correct: we
    # want the scenario clone to live in its own (project, scenario=X) slot
    # starting at version_number=1. Override post-insert.
    new.scenario = scenario_label
    new.version_number = 1
    new.previous_version_id = None
    new.is_current = True
    db.flush()

    row = AppraisalScenario(
        appraisal_group_id=base_appraisal.appraisal_group_id,
        scenario_appraisal_id=new.id,
        parent_scenario_appraisal_id=base_appraisal.id,
        scenario_label=scenario_label,
        scenario_description=description,
        created_by_user_id=actor_user_id,
    )
    db.add(row)
    db.flush()

    # Recompute so KPIs are fresh.
    appraisal_calc.recompute(db, new)

    return new, row


def _current_for(
    db: Session,
    appraisal_group_id: uuid.UUID,
    scenario_label: str,
) -> Optional[Appraisal]:
    """Return the is_current=true appraisal for (group, scenario)."""
    return db.execute(
        select(Appraisal).where(
            Appraisal.appraisal_group_id == appraisal_group_id,
            Appraisal.scenario == scenario_label,
            Appraisal.is_current.is_(True),
        )
    ).scalar_one_or_none()


def list_group_scenarios(
    db: Session,
    appraisal_group_id: uuid.UUID,
) -> list[dict]:
    """Ordered scenario summaries (Base → Upside → Downside → Sensitivity)."""
    rows = db.scalars(
        select(AppraisalScenario).where(
            AppraisalScenario.appraisal_group_id == appraisal_group_id,
        )
    ).all()
    by_label = {r.scenario_label: r for r in rows}
    out: list[dict] = []
    for label in SCENARIO_ORDER:
        r = by_label.get(label)
        if r is None:
            continue
        current = _current_for(db, appraisal_group_id, label)
        out.append({
            "id": str(r.id),
            "appraisal_group_id": str(r.appraisal_group_id),
            "scenario_appraisal_id": str(r.scenario_appraisal_id),
            "parent_scenario_appraisal_id": (
                str(r.parent_scenario_appraisal_id)
                if r.parent_scenario_appraisal_id else None
            ),
            "scenario_label": r.scenario_label,
            "scenario_description": r.scenario_description,
            "current_appraisal_id": str(current.id) if current else None,
            "created_at": r.created_at.isoformat(),
            "created_by_user_id": str(r.created_by_user_id),
        })
    return out


def _passes_hurdle(a: Appraisal) -> bool:
    """Pass iff poc OR pog meets/exceeds the respective target hurdle."""
    try:
        poc = Decimal(a.profit_on_cost_pct or 0)
        pog = Decimal(a.profit_on_gdv_pct or 0)
        tpoc = Decimal(a.target_profit_on_cost_pct or 0)
        tpog = Decimal(a.target_profit_on_gdv_pct or 0)
    except Exception:
        return False
    return (poc >= tpoc) or (pog >= tpog)


def get_group_comparator(
    db: Session,
    appraisal_group_id: uuid.UUID,
) -> dict:
    """Absolute-values comparator payload (frontend computes deltas)."""
    rows = db.scalars(
        select(AppraisalScenario).where(
            AppraisalScenario.appraisal_group_id == appraisal_group_id,
        )
    ).all()
    by_label = {r.scenario_label: r for r in rows}
    base_anchor = by_label.get("Base")
    project_id = None
    if base_anchor is not None:
        current_base = _current_for(db, appraisal_group_id, "Base")
        if current_base is not None:
            project_id = current_base.project_id
        else:
            anchor_row = db.get(Appraisal, base_anchor.scenario_appraisal_id)
            project_id = anchor_row.project_id if anchor_row else None

    scenarios: list[dict] = []
    for label in SCENARIO_ORDER:
        meta = by_label.get(label)
        if meta is None:
            continue
        current = _current_for(db, appraisal_group_id, label)
        # Count units on current appraisal.
        total_units = 0
        if current is not None:
            total_units = sum(int(u.quantity or 0) for u in (current.units or []))
        scenarios.append({
            "scenario_appraisal_id": str(meta.scenario_appraisal_id),
            "current_appraisal_id": str(current.id) if current else None,
            "scenario_label": meta.scenario_label,
            "scenario_description": meta.scenario_description,
            "version_number": current.version_number if current else None,
            "status": current.status if current else None,
            "gdv_total": str(current.gdv_total) if current else None,
            "total_cost": str(current.total_cost) if current else None,
            "profit_total": str(current.profit_total) if current else None,
            "profit_on_cost_pct": (
                str(current.profit_on_cost_pct) if current else None
            ),
            "profit_on_gdv_pct": (
                str(current.profit_on_gdv_pct) if current else None
            ),
            "residual_land_value": (
                str(current.rlv_computed_land_value)
                if (current
                    and current.rlv_computed_land_value is not None
                    and current.rlv_converged is True)
                else None
            ),
            "rlv_converged": (
                bool(current.rlv_converged) if current is not None else None
            ),
            "total_units": total_units,
            "passes_hurdle": _passes_hurdle(current) if current else False,
        })

    return {
        "project_id": str(project_id) if project_id else None,
        "appraisal_group_id": str(appraisal_group_id),
        "scenarios": scenarios,
    }
