"""Appraisal governance models — Prompt 2.3 Checkpoint 2.

Three new tables:
- AppraisalRevision     — audit trail of version transitions (append via service).
- AppraisalScenario     — metadata row for each (group, scenario) anchor.
- AppraisalDecisionLog  — append-only decision records (DB triggers enforce).

The Appraisal model already carries `appraisal_group_id`, `is_current`, and
`scenario` (retrofitted in C1 / migration 0021). This module adds the governance
layer only; inverse relationships are attached via `backref=` on the new tables.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint, Column, Date, DateTime, Enum as SAEnum, ForeignKey,
    Integer, Numeric, Text, func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db import Base


APPRAISAL_REVISION_REASONS = (
    "GDV_Updated",
    "Costs_Updated",
    "Planning_Change",
    "Finance_Terms_Change",
    "Market_Change",
    "Scope_Change",
    "Error_Correction",
    "Other",
)

DECISION_TYPES = (
    "Go",
    "No_Go",
    "Defer",
    "Request_Revision",
    "Conditional_Go",
    "Correction",
)


def _e(values, name):
    return SAEnum(*values, name=name, create_type=False, native_enum=True)


class AppraisalRevision(Base):
    __tablename__ = "appraisal_revisions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    from_version = Column(Integer, nullable=False)
    to_version = Column(Integer, nullable=False)
    appraisal_id_from = Column(UUID(as_uuid=True),
                               ForeignKey("appraisals.id", ondelete="RESTRICT"),
                               nullable=False)
    appraisal_id_to = Column(UUID(as_uuid=True),
                             ForeignKey("appraisals.id", ondelete="RESTRICT"),
                             nullable=False)
    revision_reason = Column(
        _e(APPRAISAL_REVISION_REASONS, "appraisal_revision_reason_enum"),
        nullable=False,
    )
    summary_of_changes = Column(Text, nullable=False)
    delta_gdv = Column(Numeric(14, 2), nullable=False, default=0)
    delta_total_cost = Column(Numeric(14, 2), nullable=False, default=0)
    delta_profit = Column(Numeric(14, 2), nullable=False, default=0)
    revised_by_user_id = Column(UUID(as_uuid=True),
                                ForeignKey("users.id", ondelete="RESTRICT"),
                                nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    from_appraisal = relationship(
        "Appraisal",
        foreign_keys=[appraisal_id_from],
        backref="revisions_from",
    )
    to_appraisal = relationship(
        "Appraisal",
        foreign_keys=[appraisal_id_to],
        backref="revision_to",
        uselist=False,
    )
    revised_by = relationship("User", foreign_keys=[revised_by_user_id])


class AppraisalScenario(Base):
    __tablename__ = "appraisal_scenarios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appraisal_group_id = Column(UUID(as_uuid=True), nullable=False)
    scenario_appraisal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appraisals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    parent_scenario_appraisal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appraisals.id", ondelete="RESTRICT"),
    )
    scenario_label = Column(
        SAEnum(
            "Base", "Upside", "Downside", "Sensitivity",
            name="appraisal_scenario_enum", create_type=False, native_enum=True,
        ),
        nullable=False,
    )
    scenario_description = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    created_by_user_id = Column(UUID(as_uuid=True),
                                ForeignKey("users.id", ondelete="RESTRICT"),
                                nullable=False)

    scenario_appraisal = relationship(
        "Appraisal",
        foreign_keys=[scenario_appraisal_id],
        backref="scenario_metadata",
    )
    parent_scenario_appraisal = relationship(
        "Appraisal",
        foreign_keys=[parent_scenario_appraisal_id],
    )
    created_by = relationship("User", foreign_keys=[created_by_user_id])


class AppraisalDecisionLog(Base):
    __tablename__ = "appraisal_decision_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appraisal_id = Column(UUID(as_uuid=True),
                          ForeignKey("appraisals.id", ondelete="RESTRICT"),
                          nullable=False)
    appraisal_version = Column(Integer, nullable=False)
    decision_type = Column(_e(DECISION_TYPES, "decision_type_enum"),
                           nullable=False)
    decision_maker_user_id = Column(UUID(as_uuid=True),
                                    ForeignKey("users.id", ondelete="RESTRICT"),
                                    nullable=False)
    decision_date = Column(Date, nullable=False)
    decision_rationale = Column(Text, nullable=False)
    conditions = Column(Text)
    key_assumptions_challenged = Column(Text)
    supporting_documents = Column(JSONB, nullable=False,
                                  server_default="'[]'::jsonb")
    correction_of_decision_id = Column(
        UUID(as_uuid=True),
        ForeignKey("appraisal_decision_log.id", ondelete="RESTRICT"),
    )
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    appraisal = relationship("Appraisal", backref="decisions")
    decision_maker = relationship("User", foreign_keys=[decision_maker_user_id])
    correction_of = relationship(
        "AppraisalDecisionLog",
        remote_side=[id],
        foreign_keys=[correction_of_decision_id],
    )
