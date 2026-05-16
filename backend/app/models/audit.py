"""audit_log model — Prompt 1.4."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.db import Base


AUDIT_ACTIONS = (
    "Create", "Update", "Delete",
    "Submit", "Approve", "Reject", "Reopen",
    "Login", "Logout",
    "Export", "Permission_Change",
    "Stage_Change", "Status_Change",
    # Patch #3: bulk seed runs from canonical catalogues emit Seed_Run
    # (was 'Create' + metadata.kind='seed_run'). See
    # /app/backend/alembic/versions/0017_audit_remediation_patch_3.py.
    "Seed_Run",
    # 2.3 Checkpoint 1 retrofit (Migration 0021).
    "Appraisal.NewVersion",
    "Appraisal.ScenarioCreate",
    "Appraisal.DecisionLog",
    "Appraisal.Withdraw",
    # Prompt 2.5A / Chat 19A — Actuals ledger lifecycle.
    # Title-case verbs, NOT dotted permission codes (audit pass #4).
    # Enum values added in /app/backend/alembic/versions/0025_actuals.py.
    "Post", "Mark_Paid", "Void",
    "Dispute", "Undispute", "Release_Retention",
    "Add_Attachment", "Remove_Attachment", "Promote_From_Capture",
)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    impersonator_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"))
    action = Column(Enum(*AUDIT_ACTIONS, name="audit_action", create_type=False), nullable=False)
    resource_type = Column(String(100), nullable=False)
    resource_id = Column(UUID(as_uuid=True), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"))
    project_id = Column(UUID(as_uuid=True))  # FK in 1.5

    # JSONB columns — `metadata` is reserved on sqlalchemy.Model, so the
    # DB column is `metadata_json` and the attribute is likewise.
    field_changes = Column(JSONB, nullable=False, default=list)
    metadata_json = Column(JSONB, nullable=False, default=dict)

    ip_address = Column(String(45))
    user_agent = Column(Text)
    session_id = Column(UUID(as_uuid=True), ForeignKey("user_sessions.id", ondelete="SET NULL"))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    actor = relationship("User", foreign_keys=[actor_user_id])
    impersonator = relationship("User", foreign_keys=[impersonator_user_id])
