"""Polymorphic document folder model — Chat 45 §R1.1 (Build Pack 2.7-DOCS-BE).

Logical folder tree attachable to any owner record via (owner_type,
owner_id). Suppliers first (`owner_type='supplier'`); projects and
subcontracts append the owner_type tuple in a future migration when
those tracks adopt the folder engine.

Self-referential `parent_id` FK supports unlimited nesting (D1). NULL
parent = a root folder for that owner. Sibling-name uniqueness is
enforced by a partial unique index (live rows only) — see
0043_document_folders migration.

Files (currently supplier_documents.folder_id) link in via SET NULL —
deleting a folder un-files its documents rather than cascading.

Mirrors supplier_documents.py conventions exactly (UUID PK with
gen_random_uuid() server default, tenant FK ON DELETE RESTRICT,
soft-delete via is_archived, standard audit-timestamp/user columns).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, String, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


# Controlled vocabulary for the polymorphic owner discriminator.
# Future owner types (project, subcontract) append here AND a parallel
# enum-widening of the CHECK constraint ck_document_folders_owner_type
# in a follow-on alembic migration when those tracks adopt the engine.
FOLDER_OWNER_TYPES: tuple[str, ...] = ("supplier",)


class DocumentFolder(Base):
    __tablename__ = "document_folders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )

    # Polymorphic owner. No FK on owner_id (can't FK to multiple tables);
    # service-layer validation enforces tenant + owner existence.
    owner_type: Mapped[str] = mapped_column(String(40), nullable=False)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False,
    )

    # Self-referential FK. NULL = root folder for the owner.
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_folders.id", ondelete="RESTRICT"),
        nullable=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)

    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    archived_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    archived_by: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"),
        nullable=False,
    )
