"""Cost-code business logic — Prompt 1.6 §G + B88 Pack 1 §3.

What lives here vs. the router:

* Pure SQLAlchemy queries + validation helpers. No HTTP, no audit calls.
* The router translates the structured return values from
  `cost_code_block_reasons` / `section_block_reasons` into 409 responses;
  the service NEVER raises HTTPException.

B88 Pack 1 changes (§3):

1. Hierarchy rule for a code's `section_id` target — must be either a
   subgroup or a parent group that does NOT allow children (i.e. has
   `allows_subgroups=False`). A parent group that DOES allow children
   may only host subgroups, not raw cost codes. This is enforced on
   both code-create and code-update via
   `validate_section_for_cost_code`.

2. Hierarchy rule for sections — only a section with
   `allows_subgroups=True` may receive children. Subgroups cannot
   themselves spawn grandchildren. Enforced on
   section-create + section-edit via `validate_section_parent`.

3. Delete-guard upgrade — `cost_code_block_reasons` returns a list of
   human-readable strings naming EACH blocker. The TODOs that were
   left by Prompts 2.2/2.4/2.5 are now resolved by walking the actual
   FKs in `information_schema`:
     * `project_cost_codes.cost_code_id`        (RESTRICT) → block
     * `budget_lines.cost_code_id`              (RESTRICT) → block
     * `appraisal_cost_lines.cost_code_id`      (RESTRICT) → block
     * `cost_code_subcategories.cost_code_id`   (RESTRICT) → block
   These are the only inbound FKs that block. The CASCADE/SET-NULL
   ones (`cost_code_entity_mapping`, `ai_capture_jobs.suggested_*`,
   `cost_codes.replaced_by_code_id`) are intentionally not blockers
   (see B88 Pack 1 §3.3 — the entity-mapping cascade is deliberate
   org-scoping cleanup; the AI-hint and retire-and-replace pointers
   are nullable by design).

4. Reactivate — `reactivate_cost_code` mirrors retire but is a pure
   helper here; the router owns audit + RBAC.

   N.B. `purchase_order_lines.cost_code` is a String(20) snapshot, not
   an FK. PO lines transitively depend on `budget_lines.cost_code_id`
   (RESTRICT), so any code with active POs is already blocked by the
   budget-line check.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.actuals import AICaptureJob  # noqa: F401  (kept for future)
from app.models.appraisals import AppraisalCostLine
from app.models.budgets import BudgetLine
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

# Section fields locked when the section has CHILD SUBGROUPS attached
# (B88 Pack 1 §3.2 — flipping `allows_subgroups` off while children
# exist would orphan them; flipping `parent_section_id` on a row with
# children would create a 3-level tree, which we forbid).
SECTION_LOCKED_FIELDS_WHEN_HAS_CHILDREN: frozenset[str] = frozenset({
    "allows_subgroups", "parent_section_id",
})


# ==========================================================================
# Delete-guard: cost codes (B88 Pack 1 §3.3) — replaces the 1.6 stub.
# ==========================================================================

def cost_code_block_reasons(db: Session, cost_code_id: uuid.UUID) -> list[str]:
    """Return a list of human-readable reasons why a code cannot be deleted.

    Empty list ⇒ delete is safe. The router renders each entry verbatim
    into the 409 detail so the operator sees exactly what's in the way.
    Each reason names the blocker AND the count.

    Linkages checked (all inbound RESTRICT FKs to cost_codes.id):
      1. project_cost_codes        (per-project enrolment)
      2. budget_lines              (drafted/approved budgets)
      3. appraisal_cost_lines      (appraisal scenarios)
      4. cost_code_subcategories   (sub-codes BLD-01.01 etc.)

    CASCADE/SET-NULL FKs are intentionally NOT blockers — see module
    docstring for the rationale.
    """
    reasons: list[str] = []

    pcc_count = db.scalar(
        select(func.count()).select_from(ProjectCostCode)
        .where(ProjectCostCode.cost_code_id == cost_code_id)
    ) or 0
    if pcc_count:
        reasons.append(
            f"{pcc_count} project enrolment(s) reference this code"
        )

    bl_count = db.scalar(
        select(func.count()).select_from(BudgetLine)
        .where(BudgetLine.cost_code_id == cost_code_id)
    ) or 0
    if bl_count:
        reasons.append(f"{bl_count} budget line(s) reference this code")

    acl_count = db.scalar(
        select(func.count()).select_from(AppraisalCostLine)
        .where(AppraisalCostLine.cost_code_id == cost_code_id)
    ) or 0
    if acl_count:
        reasons.append(
            f"{acl_count} appraisal cost line(s) reference this code"
        )

    sub_count = db.scalar(
        select(func.count()).select_from(CostCodeSubcategory)
        .where(CostCodeSubcategory.cost_code_id == cost_code_id)
    ) or 0
    if sub_count:
        reasons.append(
            f"{sub_count} subcategor{'y' if sub_count == 1 else 'ies'} "
            f"defined under this code"
        )

    return reasons


def is_cost_code_in_use(db: Session, cost_code_id: uuid.UUID) -> bool:
    """Boolean form used by the LOCKED-FIELDS check on update.

    Note: subcategories are EXCLUDED from this check on purpose. Having
    subcategories doesn't make the parent's `code`, `prefix`, etc.
    immutable — it just means delete is blocked. Field-locking remains
    keyed on actual posting/enrolment usage (project_cost_codes,
    budget_lines, appraisal_cost_lines).
    """
    if db.scalar(
        select(func.count()).select_from(ProjectCostCode)
        .where(ProjectCostCode.cost_code_id == cost_code_id)
    ):
        return True
    if db.scalar(
        select(func.count()).select_from(BudgetLine)
        .where(BudgetLine.cost_code_id == cost_code_id)
    ):
        return True
    if db.scalar(
        select(func.count()).select_from(AppraisalCostLine)
        .where(AppraisalCostLine.cost_code_id == cost_code_id)
    ):
        return True
    return False


# ==========================================================================
# Delete-guard: sections (B88 Pack 1 §3.3)
# ==========================================================================

def section_block_reasons(db: Session, section_id: uuid.UUID) -> list[str]:
    """Return a list of reasons why a section cannot be deleted.

    Blockers:
      1. Cost codes whose `section_id` points here (RESTRICT FK).
      2. Subgroups whose `parent_section_id` points here (RESTRICT FK).
    """
    reasons: list[str] = []

    cc_count = db.scalar(
        select(func.count()).select_from(CostCode)
        .where(CostCode.section_id == section_id)
    ) or 0
    if cc_count:
        reasons.append(
            f"{cc_count} cost code(s) attached to this group"
        )

    child_count = db.scalar(
        select(func.count()).select_from(CostCodeSection)
        .where(CostCodeSection.parent_section_id == section_id)
    ) or 0
    if child_count:
        reasons.append(
            f"{child_count} subgroup(s) under this group"
        )

    return reasons


def is_section_in_use(db: Session, section_id: uuid.UUID) -> bool:
    """Back-compat boolean form — True iff section has attached codes.

    Used by the field-lock check on section edit. Subgroup-children do
    NOT lock fields (you can rename a parent group while it owns
    subgroups); they only block delete.
    """
    return bool(db.scalar(
        select(func.count()).select_from(CostCode)
        .where(CostCode.section_id == section_id)
    ))


def section_has_children(db: Session, section_id: uuid.UUID) -> bool:
    """True iff any other section row has parent_section_id = section_id."""
    return bool(db.scalar(
        select(func.count()).select_from(CostCodeSection)
        .where(CostCodeSection.parent_section_id == section_id)
    ))


# ==========================================================================
# Hierarchy validators (B88 Pack 1 §3.2)
# ==========================================================================

def validate_section_parent(
    db: Session,
    *,
    parent_id: Optional[uuid.UUID],
    self_id: Optional[uuid.UUID] = None,
) -> Optional[str]:
    """Return None if `parent_id` is a legal parent target, else an error.

    Rules (only two levels allowed):
      * parent_id None ⇒ this row IS a tier-1 parent group. Always legal.
      * parent_id set  ⇒ this row IS a tier-2 subgroup; the parent must
        exist, must have `allows_subgroups=True`, and must itself be a
        tier-1 (its own `parent_section_id` MUST be NULL — no
        grandchildren).
      * Self-reference forbidden.
    """
    if parent_id is None:
        return None
    if self_id is not None and parent_id == self_id:
        return "A section cannot be its own parent."
    parent = db.scalar(
        select(CostCodeSection).where(CostCodeSection.id == parent_id)
    )
    if parent is None:
        return "parent_section_id does not reference an existing group."
    if not parent.allows_subgroups:
        return (
            f"Group '{parent.code}' is not configured to host subgroups "
            "(allows_subgroups=false)."
        )
    if parent.parent_section_id is not None:
        return (
            "Cannot nest a subgroup under another subgroup — only "
            "two tiers are allowed."
        )
    return None


def validate_section_for_cost_code(
    db: Session,
    *,
    section_id: uuid.UUID,
) -> Optional[str]:
    """A cost code's section target must be either:

      * a subgroup (parent_section_id IS NOT NULL), or
      * a tier-1 parent group with allows_subgroups=False.

    A tier-1 parent group with allows_subgroups=True must NOT host
    raw cost codes — it can only host subgroups. Returns None when
    legal, else a human-readable error string.
    """
    sec = db.scalar(
        select(CostCodeSection).where(CostCodeSection.id == section_id)
    )
    if sec is None:
        return "Section not found."
    if sec.parent_section_id is not None:
        # subgroup — legal
        return None
    if sec.allows_subgroups:
        return (
            f"Group '{sec.code}' hosts subgroups — cost codes must be "
            "filed under one of its subgroups, not the parent itself."
        )
    return None


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
# Retirement + reactivation + cycle prevention (§G.1 + B88 Pack 1 §3.4)
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


def reactivate_cost_code(c: CostCode) -> dict:
    """Flip a retired code back to Active and clear retire metadata.

    Pure mutation — caller commits + records audit. Returns a before/
    after dict the router uses to compute the audit field-diff.
    `replaced_by_code_id` is cleared so an incoming pointer chain
    doesn't survive reactivation (otherwise the un-retired code
    would still claim to be "replaced by" something).
    """
    before = {
        "status": c.status,
        "retired_at": c.retired_at.isoformat() if c.retired_at else None,
        "retired_reason": c.retired_reason,
        "replaced_by_code_id": (
            str(c.replaced_by_code_id) if c.replaced_by_code_id else None
        ),
    }
    c.status = "Active"
    c.retired_at = None
    c.retired_reason = None
    c.replaced_by_code_id = None
    after = {
        "status": c.status,
        "retired_at": None,
        "retired_reason": None,
        "replaced_by_code_id": None,
    }
    return {"before": before, "after": after,
            "reactivated_at": datetime.now(timezone.utc).isoformat()}


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
