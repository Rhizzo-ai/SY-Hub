"""Appraisal decisions service — Prompt 2.3 Checkpoint 2 (Phase D.2).

Three operations:
- log_decision — append to appraisal_decision_log with strict validation.
- list_for_appraisal — chronological decisions for a single appraisal version.
- get_nudge_state — has the current Approved Base reached the distinct-decider
  threshold? Uses `appraisal_decisions_required_threshold` system_config key.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.appraisals import Appraisal
from app.models.appraisal_governance import AppraisalDecisionLog
from app.models.system_config import SystemConfig


CORE_DECISIONS = ("Go", "No_Go", "Defer")


class DecisionError(Exception):
    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)


def log_decision(
    db: Session,
    *,
    appraisal: Appraisal,
    appraisal_version: int,
    decision_type: str,
    decision_date: date,
    decision_rationale: str,
    conditions: Optional[str],
    key_assumptions_challenged: Optional[str],
    supporting_documents: list,
    correction_of_decision_id: Optional[uuid.UUID],
    actor_user_id: uuid.UUID,
) -> AppraisalDecisionLog:
    """Validate + insert a decision row. Caller commits."""
    # 1. is_current gate.
    if not appraisal.is_current:
        raise DecisionError(
            code="DECISION_ON_NON_CURRENT_APPRAISAL",
            message=(
                "Decisions may only be logged on the current version of "
                "an appraisal."
            ),
            http_status=400,
        )
    # 2. version gate.
    if appraisal_version != appraisal.version_number:
        raise DecisionError(
            code="INVALID_DECISION_VERSION",
            message=(
                f"appraisal_version {appraisal_version} does not match "
                f"current version_number {appraisal.version_number}."
            ),
            http_status=400,
        )
    # 3. Rationale length (DB CHECK also enforces; surface as business code).
    if len((decision_rationale or "").strip()) < 10:
        raise DecisionError(
            code="RATIONALE_TOO_SHORT",
            message="decision_rationale must be at least 10 characters.",
            http_status=400,
        )
    # 4. Conditional_Go requires conditions.
    if decision_type == "Conditional_Go":
        if not conditions or not conditions.strip():
            raise DecisionError(
                code="MISSING_CONDITIONS",
                message="Conditional_Go requires conditions to be provided.",
                http_status=400,
            )
    else:
        if conditions is not None and conditions.strip():
            raise DecisionError(
                code="CONDITIONS_NOT_ALLOWED",
                message=(
                    "conditions may only be set when decision_type is "
                    "Conditional_Go."
                ),
                http_status=400,
            )
        conditions = None
    # 5. Correction requires reference.
    if decision_type == "Correction":
        if correction_of_decision_id is None:
            raise DecisionError(
                code="MISSING_CORRECTION_REFERENCE",
                message=(
                    "Correction decisions require correction_of_decision_id."
                ),
                http_status=400,
            )
        corr = db.get(AppraisalDecisionLog, correction_of_decision_id)
        if corr is None or corr.appraisal_id != appraisal.id:
            raise DecisionError(
                code="CORRECTION_REFERENCE_MISMATCH",
                message=(
                    "correction_of_decision_id must reference a decision on "
                    "the same appraisal."
                ),
                http_status=400,
            )
    else:
        if correction_of_decision_id is not None:
            raise DecisionError(
                code="CORRECTION_REFERENCE_NOT_ALLOWED",
                message=(
                    "correction_of_decision_id may only be set when "
                    "decision_type is Correction."
                ),
                http_status=400,
            )
        correction_of_decision_id = None
    # 6. Future-dated decision.
    today_london = datetime.now(ZoneInfo("Europe/London")).date()
    if decision_date > today_london:
        raise DecisionError(
            code="FUTURE_DATED_DECISION",
            message=(
                f"decision_date {decision_date} is after today "
                f"{today_london} (Europe/London)."
            ),
            http_status=400,
        )
    # 7. Validate supporting_documents as list[uuid-string].
    docs = supporting_documents or []
    if not isinstance(docs, list):
        raise DecisionError(
            code="INVALID_DOCUMENT_REFERENCE",
            message="supporting_documents must be an array.",
            http_status=400,
        )
    normalised: list[str] = []
    for d in docs:
        try:
            normalised.append(str(uuid.UUID(str(d))))
        except (ValueError, TypeError):
            raise DecisionError(
                code="INVALID_DOCUMENT_REFERENCE",
                message=(
                    f"supporting_documents entry {d!r} is not a valid UUID."
                ),
                http_status=400,
            )

    row = AppraisalDecisionLog(
        appraisal_id=appraisal.id,
        appraisal_version=appraisal_version,
        decision_type=decision_type,
        decision_maker_user_id=actor_user_id,
        decision_date=decision_date,
        decision_rationale=decision_rationale.strip(),
        conditions=conditions.strip() if conditions else None,
        key_assumptions_challenged=(
            key_assumptions_challenged.strip()
            if key_assumptions_challenged else None
        ),
        supporting_documents=normalised,
        correction_of_decision_id=correction_of_decision_id,
    )
    db.add(row)
    db.flush()
    return row


def list_for_appraisal(
    db: Session,
    appraisal_id: uuid.UUID,
    *,
    limit: int = 50,
) -> list[AppraisalDecisionLog]:
    limit = max(1, min(int(limit), 200))
    rows = db.scalars(
        select(AppraisalDecisionLog)
        .where(AppraisalDecisionLog.appraisal_id == appraisal_id)
        .order_by(
            AppraisalDecisionLog.decision_date.desc(),
            AppraisalDecisionLog.created_at.desc(),
        )
        .limit(limit)
    ).all()
    return list(rows)


def _read_threshold(db: Session) -> int:
    row = db.execute(
        select(SystemConfig).where(
            SystemConfig.config_key == "appraisal_decisions_required_threshold",
        )
    ).scalar_one_or_none()
    if row is None:
        return 3
    try:
        return int(row.config_value)
    except (TypeError, ValueError):
        return 3


def get_nudge_state(
    db: Session,
    project_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> dict:
    """Read nudge state for a project's current Approved Base appraisal."""
    threshold = _read_threshold(db)

    current = db.execute(
        select(Appraisal).where(
            Appraisal.project_id == project_id,
            Appraisal.is_current.is_(True),
            Appraisal.scenario == "Base",
            Appraisal.status == "Approved",
        )
    ).scalar_one_or_none()

    if current is None:
        return {
            "should_show": False,
            "threshold": threshold,
            "distinct_decision_makers": 0,
            "current_appraisal_id": None,
            "actor_has_decided": False,
            "message": "",
        }

    distinct = db.execute(
        select(func.count(func.distinct(AppraisalDecisionLog.decision_maker_user_id)))
        .where(
            AppraisalDecisionLog.appraisal_id == current.id,
            AppraisalDecisionLog.decision_type.in_(CORE_DECISIONS),
        )
    ).scalar_one() or 0

    actor_has_decided = db.execute(
        select(func.count(AppraisalDecisionLog.id))
        .where(
            AppraisalDecisionLog.appraisal_id == current.id,
            AppraisalDecisionLog.decision_maker_user_id == actor_user_id,
            AppraisalDecisionLog.decision_type.in_(CORE_DECISIONS),
        )
    ).scalar_one() > 0

    should_show = int(distinct) < threshold

    return {
        "should_show": bool(should_show),
        "threshold": int(threshold),
        "distinct_decision_makers": int(distinct),
        "current_appraisal_id": str(current.id),
        "actor_has_decided": bool(actor_has_decided),
        "message": (
            f"{int(distinct)} of {int(threshold)} decision-makers have logged "
            f"Go/No_Go/Defer on the current appraisal."
        ),
    }
