"""Cost-code business logic — Prompt 1.6 §G."""
from __future__ import annotations

import re
import uuid
from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.cost_codes import (
    CostCode, CostCodeSection, CostCodeSubcategory,
    CostCodeEntityMapping, ProjectCostCode,
)
from app.models.entity import Entity
from app.models.projects import Project


# ==========================================================================
# Locking / immutability (§G.2)
# ==========================================================================

# Fields that may NEVER change once a code is in use.
LOCKED_FIELDS_WHEN_IN_USE: frozenset[str] = frozenset({
    "code", "prefix", "sequence", "section_id",
    "vat_treatment", "is_vattable",
    "is_cis_applicable", "is_retention_applicable", "is_capitalisable",
})

# Section fields locked when the section has any cost_codes referencing it.
SECTION_LOCKED_FIELDS_WHEN_IN_USE: frozenset[str] = frozenset({
    "code", "is_direct_cost", "default_p_and_l_category",
})


def is_cost_code_in_use(db: Session, cost_code_id: uuid.UUID) -> bool:
    """Return True iff any project_cost_codes row references this code.

    Extension point — Phase 2 prompts (appraisals, budgets, actuals,
    commitments) should add their own existence checks below.
    """
    if db.scalar(
        select(func.count()).select_from(ProjectCostCode)
        .where(ProjectCostCode.cost_code_id == cost_code_id)
    ):
        return True
    # TODO Prompt 2.2: appraisal_cost_lines.cost_code_id
    # TODO Prompt 2.4: budget_lines.cost_code_id
    # TODO Prompt 2.5: actuals.cost_code_id, commitments.cost_code_id
    return False


def is_section_in_use(db: Session, section_id: uuid.UUID) -> bool:
    return bool(db.scalar(
        select(func.count()).select_from(CostCode)
        .where(CostCode.section_id == section_id)
    ))


# ==========================================================================
# Code-format validators
# ==========================================================================

_CODE_PATTERN = re.compile(r"^[A-Z]{3}-\d{2}$")
_SUBCAT_PATTERN = re.compile(r"^[A-Z]{3}-\d{2}\.\d{2}$")


def validate_cost_code_format(code: str) -> bool:
    return bool(_CODE_PATTERN.match(code or ""))


def validate_subcategory_format(parent_code: str, subcat_code: str) -> bool:
    """Subcategory code must be {parent}.{2-digit-sequence}."""
    if not _SUBCAT_PATTERN.match(subcat_code or ""):
        return False
    return subcat_code.split(".")[0] == parent_code


# ==========================================================================
# Retirement + cycle prevention (§G.1)
# ==========================================================================

def detect_replaced_by_cycle(
    db: Session,
    *,
    candidate_id: uuid.UUID,
    proposed_replaced_by: uuid.UUID,
    max_hops: int = 50,
) -> bool:
    """Walk the replaced_by_code_id chain forward from `proposed_replaced_by`.
    If the walk visits `candidate_id` (the code being retired), a cycle
    would form once we set `candidate.replaced_by_code_id = proposed`.
    Returns True iff a cycle would form.
    """
    visited: set[uuid.UUID] = set()
    cursor: Optional[uuid.UUID] = proposed_replaced_by
    hops = 0
    while cursor is not None and hops < max_hops:
        if cursor == candidate_id:
            return True
        if cursor in visited:
            return False  # existing cycle in chain — caller's choice to ignore
        visited.add(cursor)
        cursor = db.scalar(
            select(CostCode.replaced_by_code_id).where(CostCode.id == cursor)
        )
        hops += 1
    return False


# ==========================================================================
# Entity mapping resolution (§G.3)
# ==========================================================================

def can_entity_use_cost_code(
    db: Session,
    *,
    cost_code_id: uuid.UUID,
    entity_id: uuid.UUID,
) -> Tuple[bool, Optional[str]]:
    """Resolve whether an entity may post against a cost code.

    Returns (allowed, xero_nominal_code or None).
    """
    explicit = db.scalar(
        select(CostCodeEntityMapping).where(
            CostCodeEntityMapping.cost_code_id == cost_code_id,
            CostCodeEntityMapping.entity_id == entity_id,
        )
    )
    cc = db.scalar(select(CostCode).where(CostCode.id == cost_code_id))
    if cc is None:
        return False, None
    if explicit is not None:
        if not explicit.is_allowed:
            return False, None
        nominal = explicit.xero_nominal_code_override or cc.xero_nominal_code
        return True, nominal

    ent = db.scalar(select(Entity).where(Entity.id == entity_id))
    if ent is None:
        return False, None

    if ent.entity_type == "Parent":
        ok = cc.applies_to_parent
    elif ent.entity_type == "SPV":
        ok = cc.applies_to_spv
    elif ent.entity_type == "ConstructionCo":
        ok = cc.applies_to_construction_co
    else:
        # JV_Vehicle, Other — no default routing; explicit mapping required.
        return False, None
    if not ok:
        return False, None
    return True, cc.xero_nominal_code


# ==========================================================================
# Project auto-populate (§F)
# ==========================================================================

PURE_DEV_ENABLED_PREFIXES = {
    "ACQ", "PLN", "DES", "FAC", "SAL", "FIN", "OHD", "ACC", "CTG",
}


def project_type_enabled_predicate(project_type: str, prefix: str) -> bool:
    """Return whether a code with this prefix should be enabled by default
    for a project of `project_type`."""
    if project_type == "Pure_Dev":
        return prefix in PURE_DEV_ENABLED_PREFIXES
    if project_type == "DB_Contract":
        return prefix != "SAL"
    # Dev_Build, JV, Main_Contract — all enabled.
    return True


def auto_populate_project_cost_codes(db: Session, project: Project) -> dict:
    """Bulk-insert one project_cost_codes row per Active cost code.

    Returns counters {enabled, disabled, project_type} for the caller
    to write the summary audit row. Does NOT commit.
    """
    rows = db.execute(
        select(CostCode.id, CostCode.prefix)
        .where(CostCode.status == "Active")
    ).all()
    enabled_count = 0
    disabled_count = 0
    payload = []
    for cid, prefix in rows:
        is_enabled = project_type_enabled_predicate(project.project_type, prefix)
        if is_enabled:
            enabled_count += 1
        else:
            disabled_count += 1
        payload.append({
            "id": uuid.uuid4(),
            "project_id": project.id,
            "cost_code_id": cid,
            "is_enabled": is_enabled,
        })
    if payload:
        db.execute(ProjectCostCode.__table__.insert(), payload)
    return {
        "enabled_count": enabled_count,
        "disabled_count": disabled_count,
        "project_type": project.project_type,
    }
