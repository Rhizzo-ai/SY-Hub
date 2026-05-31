"""Role + Permission + junction tables — Prompt 1.2."""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, uuid4


# ---------- Enums ----------

RESOURCES = (
    "entities", "projects", "users", "roles", "audit",
    "cost_codes", "appraisals", "budgets", "actuals",
    "commitments", "budget_changes", "cash_flow",
    "programmes", "programme_tasks", "documents",
    "document_registers", "certificates",
    "xero_connections", "xero_bills", "xero_invoices", "xero_sync",
    "system_config", "notifications", "reports",
    "ai_capture",  # Chat 20 §R1.1 (B38) — cost dashboard resource
    "suppliers",   # Chat 24 §R1 (Prompt 2.5) — supplier directory resource
    "pos",         # Chat 24 §R2 (Prompt 2.5) — purchase orders resource
    # Chat 32 §R2 (Prompt 2.7) — subcontractor CIS verifications +
    # supplier compliance documents resources.
    "cis",
    "supplier_documents",
    # Chat 34 §R2 (Prompt 2.8a) — subcontracts (formal agreement layer
    # wrapping a subcontractor PO) + subcontract variations
    # (raise → cost → approve → issue workflow).
    "subcontracts",
    "subcontract_variations",
)

ACTIONS = (
    "view", "view_sensitive", "view_financials",
    "create", "edit", "delete",
    "submit", "approve", "reopen",
    "export", "admin",
    "view_costs",  # Chat 20 §R1.1 (B38) — cost dashboard action
    "archive",     # Chat 24 §R1 (Prompt 2.5) — supplier archive/unarchive
    # Chat 24 §R2 (Prompt 2.5) — PO action verbs
    "edit_issued", "issue", "void", "close", "receipt",
    # Chat 32 §R2 (Prompt 2.7) — CIS verification action.
    "verify",
    # Chat 33 §R2 (Prompt 2.6) — BCR apply action (writes
    # budget_lines.approved_changes after approval).
    "apply",
    # Chat 34 §R2 (Prompt 2.8a) — subcontract variation `cost` step
    # (set agreed_value, transition Raised→Costed). `issue` already
    # exists (PO 2.5) and is reused for the formal variation-issued
    # step.
    "cost",
)

ENTITY_SCOPES = ("All", "Specific")
PROJECT_SCOPES = ("All", "Specific", "None")
USER_ROLE_STATUSES = ("Active", "Expired", "Revoked")


resource_enum = SAEnum(*RESOURCES, name="permission_resource", create_type=True)
action_enum = SAEnum(*ACTIONS, name="permission_action", create_type=True)
entity_scope_enum = SAEnum(*ENTITY_SCOPES, name="entity_scope", create_type=True)
project_scope_enum = SAEnum(*PROJECT_SCOPES, name="project_scope", create_type=True)
user_role_status_enum = SAEnum(
    *USER_ROLE_STATUSES, name="user_role_status", create_type=True
)


# ---------- Roles ----------

class Role(Base, TimestampMixin):
    __tablename__ = "roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_system_role: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("50"))


# ---------- Permissions ----------

class Permission(Base):
    __tablename__ = "permissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    resource: Mapped[str] = mapped_column(resource_enum, nullable=False)
    action: Mapped[str] = mapped_column(action_enum, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    is_sensitive: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


# ---------- role_permissions (junction) ----------

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column(
        "role_id",
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "permission_id",
        UUID(as_uuid=True),
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    ),
    PrimaryKeyConstraint("role_id", "permission_id"),
)


# ---------- user_roles ----------

class UserRole(Base, TimestampMixin):
    __tablename__ = "user_roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
    )
    entity_scope: Mapped[str] = mapped_column(
        entity_scope_enum, nullable=False, server_default=text("'All'::entity_scope")
    )
    project_scope: Mapped[str] = mapped_column(
        project_scope_enum, nullable=False, server_default=text("'All'::project_scope")
    )
    view_overrides: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    assigned_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expires_at = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    revoked_reason = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        user_role_status_enum,
        nullable=False,
        server_default=text("'Active'::user_role_status"),
    )

    __table_args__ = (
        Index("ix_user_roles_user_status", "user_id", "status"),
        Index("ix_user_roles_role", "role_id"),
        Index(
            "ix_user_roles_expires",
            "expires_at",
            postgresql_where=text("expires_at IS NOT NULL"),
        ),
    )


# ---------- user_role_entities / user_role_projects ----------

user_role_entities = Table(
    "user_role_entities",
    Base.metadata,
    Column(
        "user_role_id",
        UUID(as_uuid=True),
        ForeignKey("user_roles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "entity_id",
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    ),
    PrimaryKeyConstraint("user_role_id", "entity_id"),
)

user_role_projects = Table(
    "user_role_projects",
    Base.metadata,
    Column(
        "user_role_id",
        UUID(as_uuid=True),
        ForeignKey("user_roles.id", ondelete="CASCADE"),
        nullable=False,
    ),
    # FK to projects added in Prompt 1.5 — plain UUID for now.
    Column("project_id", UUID(as_uuid=True), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    ),
    PrimaryKeyConstraint("user_role_id", "project_id"),
)
