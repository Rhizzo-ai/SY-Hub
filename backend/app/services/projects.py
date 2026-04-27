"""Projects service helpers — Prompt 1.5."""
from __future__ import annotations

import re
import uuid
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.projects import Project


CODE_RE = re.compile(r"^[A-Z0-9]{3}-\d{3,}$")


def _slug_prefix(name: str) -> str:
    """First 3 alphanumeric chars of the name, upper-cased, padded with X."""
    clean = re.sub(r"[^A-Za-z0-9]", "", name or "").upper()
    if len(clean) >= 3:
        return clean[:3]
    return (clean + "XXX")[:3]


def next_project_code(db: Session, name: str) -> str:
    prefix = _slug_prefix(name)
    existing = db.scalars(
        select(Project.project_code).where(Project.project_code.like(f"{prefix}-%"))
    ).all()
    max_seq = 0
    for code in existing:
        try:
            seq = int(code.split("-", 1)[1])
            max_seq = max(max_seq, seq)
        except (IndexError, ValueError):
            continue
    return f"{prefix}-{max_seq + 1:03d}"


def validate_code_override(code: str) -> bool:
    return bool(CODE_RE.match(code or ""))


HA_TO_ACRES = Decimal("2.47105")
ACRES_TO_HA = Decimal("0.404686")


def _round4(v) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def reconcile_area(ha: Optional[Decimal], acres: Optional[Decimal]) -> tuple[Optional[Decimal], Optional[Decimal]]:
    """Section F: backend trusts ha if both supplied. Round to 4dp."""
    if ha is not None:
        ha = _round4(ha)
        return ha, _round4(ha * HA_TO_ACRES)
    if acres is not None:
        acres = _round4(acres)
        return _round4(acres * ACRES_TO_HA), acres
    return None, None


# Planning expiry formula (Section E1).
PLANNING_3_YEAR_TYPES = {"Full", "Outline", "Hybrid", "Permitted_Dev", "Prior_Approval"}
PLANNING_2_YEAR_TYPES = {"Reserved_Matters"}


def derive_planning_expiry(ptype: Optional[str], approval_date: Optional[date]) -> Optional[date]:
    if not ptype or not approval_date:
        return None
    if ptype in PLANNING_3_YEAR_TYPES:
        return approval_date.replace(year=approval_date.year + 3)
    if ptype in PLANNING_2_YEAR_TYPES:
        return approval_date.replace(year=approval_date.year + 2)
    return None


def has_project_dependents(db: Session, project_id: uuid.UUID) -> bool:
    """Section I1 — single place to extend as future tables land.

    Returns True iff the project has any financial / contractual /
    operational records that would make hard-deletion destructive.

    TODO wire checks as these tables are introduced:
      - appraisals (Prompt 2.2)
      - budgets (2.4)
      - actuals, commitments (2.5)
      - budget_changes (2.6)
      - cash_flow_entries (2.7)
      - programmes, programme_tasks (3.2)
      - documents (4.2)
      - compliance_registers, certificates (4.3)
      - xero_* (Track 5)

    project_team_members cascade (CASCADE on FK). user_role_projects also
    cascade. Neither blocks delete.
    """
    # No-op for now — nothing in the schema yet that blocks.
    return False
