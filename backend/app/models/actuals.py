"""Actuals ORM models — Prompt 2.5A / Chat 19A.

Mirrors migration 0025_actuals. See that file for FK / index / trigger
rationale.

Status state machine:
    Draft -> Posted -> Paid
    Draft -> Void  (any time except Paid; Paid->Void requires credit note)
    Posted -> Disputed -> Posted (un-dispute)
    Posted -> Void (with reason)

Immutability rule (DB-enforced by trigger trg_actuals_immutability):
    After Posted/Paid/Disputed, financial fields are locked. Corrections must
    go via credit note (a new actual with source_type='Xero_Credit_Note' and
    negative net_amount). Void rows are completely frozen.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean, Column, Date, DateTime, Enum, ForeignKey,
    Integer, Numeric, String, Text, func, text as sa_text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db import Base


# Enum value tuples (mirror migration 0025_actuals)
ACTUAL_STATUSES = ("Draft", "Posted", "Paid", "Void", "Disputed")
ACTUAL_SOURCE_TYPES = (
    "Xero_Bill", "Xero_Credit_Note", "Manual_Entry",
    "SC_Valuation", "Day_Rate_Timesheet", "Expense_Claim",
    "Journal", "Internal_Recharge",
)
AI_CAPTURE_STATUSES = (
    "Queued", "Extracting", "Awaiting_Review",
    "Completed", "Failed", "Discarded",
)
ACTUAL_ATTACHMENT_SOURCES = ("Manual_Upload", "Email_Capture", "AI_Capture")

TERMINAL_ACTUAL_STATUSES = ("Paid", "Void")

# Valid status transitions enforced at service layer (DB only enforces
# immutability of financial fields, not the transition graph itself).
VALID_TRANSITIONS = {
    "Draft":    {"Posted", "Void"},
    "Posted":   {"Paid", "Void", "Disputed"},
    "Paid":     set(),  # terminal; reverse via credit note
    "Void":     set(),  # terminal; immutable
    "Disputed": {"Posted", "Void"},  # un-dispute back to Posted
}


class Actual(Base):
    __tablename__ = "actuals"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=sa_text("gen_random_uuid()"))

    project_id = Column(UUID(as_uuid=True),
                        ForeignKey("projects.id", ondelete="RESTRICT"),
                        nullable=False)
    budget_line_id = Column(UUID(as_uuid=True),
                            ForeignKey("budget_lines.id", ondelete="RESTRICT"),
                            nullable=False)
    entity_id = Column(UUID(as_uuid=True),
                       ForeignKey("entities.id", ondelete="RESTRICT"),
                       nullable=False)

    source_type = Column(Enum(*ACTUAL_SOURCE_TYPES, name="actual_source_type",
                              create_type=False), nullable=False)
    source_reference = Column(Text)
    external_id = Column(Text)

    transaction_date = Column(Date, nullable=False)
    posting_date = Column(Date, nullable=False, server_default=func.current_date())
    description = Column(Text, nullable=False)

    net_amount = Column(Numeric(14, 2), nullable=False)
    vat_amount = Column(Numeric(14, 2), nullable=False, server_default="0")
    gross_amount = Column(Numeric(14, 2), nullable=False)
    vat_rate_pct = Column(Numeric(6, 3), nullable=False, server_default="20")
    is_vat_recoverable = Column(Boolean, nullable=False, server_default=sa_text("true"))
    currency = Column(String(3), nullable=False, server_default="GBP")
    exchange_rate = Column(Numeric(14, 6))

    supplier_id = Column(UUID(as_uuid=True))  # FK deferred (Track 4)
    supplier_name_snapshot = Column(String(255), nullable=False)
    supplier_invoice_ref = Column(String(100))

    is_cis_applicable = Column(Boolean, nullable=False, server_default=sa_text("false"))
    cis_deduction_rate_pct = Column(Numeric(5, 2))
    cis_labour_amount = Column(Numeric(14, 2))
    cis_materials_amount = Column(Numeric(14, 2))
    cis_deduction_amount = Column(Numeric(14, 2))
    cis_reported_to_hmrc = Column(Boolean, nullable=False, server_default=sa_text("false"))

    retention_rate_pct = Column(Numeric(5, 2))
    retention_amount = Column(Numeric(14, 2))
    retention_released = Column(Boolean, nullable=False, server_default=sa_text("false"))
    retention_release_date = Column(Date)

    linked_commitment_id = Column(UUID(as_uuid=True))  # FK deferred (Chat 20)
    related_subcontract_id = Column(UUID(as_uuid=True))  # FK deferred (Track 4)

    is_reconciled_to_xero = Column(Boolean, nullable=False, server_default=sa_text("false"))
    reconciled_at = Column(DateTime(timezone=True))
    reconciliation_variance = Column(Numeric(14, 2))

    status = Column(Enum(*ACTUAL_STATUSES, name="actual_status", create_type=False),
                    nullable=False, server_default="Draft")

    posted_at = Column(DateTime(timezone=True))
    posted_by_user_id = Column(UUID(as_uuid=True),
                               ForeignKey("users.id", ondelete="RESTRICT"))
    paid_date = Column(Date)
    payment_reference = Column(String(100))
    disputed_at = Column(DateTime(timezone=True))
    disputed_by_user_id = Column(UUID(as_uuid=True),
                                 ForeignKey("users.id", ondelete="RESTRICT"))
    dispute_reason = Column(Text)
    voided_at = Column(DateTime(timezone=True))
    voided_by_user_id = Column(UUID(as_uuid=True),
                               ForeignKey("users.id", ondelete="RESTRICT"))
    void_reason = Column(Text)

    document_ids = Column(JSONB, nullable=False, server_default=sa_text("'[]'::jsonb"))
    ai_capture_metadata = Column(JSONB)

    created_by_user_id = Column(UUID(as_uuid=True),
                                ForeignKey("users.id", ondelete="RESTRICT"),
                                nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    # Relationships
    project = relationship("Project", foreign_keys=[project_id])
    budget_line = relationship("BudgetLine", foreign_keys=[budget_line_id])
    entity = relationship("Entity", foreign_keys=[entity_id])
    attachments = relationship("ActualAttachment", back_populates="actual",
                               cascade="all, delete-orphan")
    change_log = relationship("ActualChangeLog", back_populates="actual")


class ActualAttachment(Base):
    __tablename__ = "actual_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=sa_text("gen_random_uuid()"))
    actual_id = Column(UUID(as_uuid=True),
                       ForeignKey("actuals.id", ondelete="CASCADE"),
                       nullable=False)
    file_path = Column(Text, nullable=False)
    file_type = Column(String(100), nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    original_filename = Column(String(500), nullable=False)
    source = Column(Enum(*ACTUAL_ATTACHMENT_SOURCES, name="actual_attachment_source",
                         create_type=False), nullable=False)
    uploaded_by_user_id = Column(UUID(as_uuid=True),
                                 ForeignKey("users.id", ondelete="RESTRICT"))
    uploaded_at = Column(DateTime(timezone=True), nullable=False,
                         server_default=func.now())
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    actual = relationship("Actual", back_populates="attachments")


class InboundEmailMessage(Base):
    __tablename__ = "inbound_email_messages"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=sa_text("gen_random_uuid()"))
    postmark_message_id = Column(String(100))
    from_email = Column(String(320), nullable=False)
    to_email = Column(String(320), nullable=False)
    subject = Column(String(998))
    received_at = Column(DateTime(timezone=True), nullable=False)
    raw_email_path = Column(Text)
    attachment_count = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    jobs = relationship("AICaptureJob", back_populates="inbound_message")


class AICaptureJob(Base):
    __tablename__ = "ai_capture_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=sa_text("gen_random_uuid()"))
    inbound_email_message_id = Column(UUID(as_uuid=True),
                                      ForeignKey("inbound_email_messages.id",
                                                 ondelete="RESTRICT"),
                                      nullable=False)
    attachment_path = Column(Text, nullable=False)
    status = Column(Enum(*AI_CAPTURE_STATUSES, name="ai_capture_status",
                         create_type=False), nullable=False, server_default="Queued")
    attempts = Column(Integer, nullable=False, server_default="0")
    last_attempted_at = Column(DateTime(timezone=True))
    last_error_message = Column(Text)
    extracted_data = Column(JSONB)
    confidence_scores = Column(JSONB)
    suggested_entity_id = Column(UUID(as_uuid=True),
                                 ForeignKey("entities.id", ondelete="SET NULL"))
    suggested_project_id = Column(UUID(as_uuid=True),
                                  ForeignKey("projects.id", ondelete="SET NULL"))
    suggested_cost_code_id = Column(UUID(as_uuid=True),
                                    ForeignKey("cost_codes.id", ondelete="SET NULL"))
    target_actual_id = Column(UUID(as_uuid=True),
                              ForeignKey("actuals.id", ondelete="SET NULL"))
    model_used = Column(String(100))
    prompt_tokens = Column(Integer)
    completion_tokens = Column(Integer)
    cost_pence = Column(Integer)
    created_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False,
                        server_default=func.now())

    inbound_message = relationship("InboundEmailMessage", back_populates="jobs")


# Allowed event_type values (mirrors ck_actuals_change_log_event_type_valid CHECK)
CHANGE_LOG_EVENT_TYPES = (
    "Created", "Edited", "Posted", "Paid", "Voided",
    "Disputed", "Undisputed", "Reconciled", "Retention_Released",
    "Attachment_Added", "Attachment_Removed",
)


class ActualChangeLog(Base):
    __tablename__ = "actuals_change_log"

    id = Column(UUID(as_uuid=True), primary_key=True,
                server_default=sa_text("gen_random_uuid()"))
    actual_id = Column(UUID(as_uuid=True),
                       ForeignKey("actuals.id", ondelete="RESTRICT"),
                       nullable=False)
    event_type = Column(String(50), nullable=False)
    actor_user_id = Column(UUID(as_uuid=True),
                           ForeignKey("users.id", ondelete="RESTRICT"))
    event_payload = Column(JSONB, nullable=False,
                           server_default=sa_text("'{}'::jsonb"))
    occurred_at = Column(DateTime(timezone=True), nullable=False,
                         server_default=func.now())

    actual = relationship("Actual", back_populates="change_log")
