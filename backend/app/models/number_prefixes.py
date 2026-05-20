"""Project number prefix model — per-project, per-entity-type prefix configuration.

Chat 24 §R1 (Prompt 2.5 — Purchase Orders, Suppliers & PO/Bill Numbering).
Each row defines one numbering namespace for a project + entity_type
combo. Format: `{ENTITY}-{middle?}-{NNNN}` where:
  - ENTITY is fixed by entity_type ('PO' or 'BILL', upper-cased at format time)
  - middle is optional, alphanumeric+dash, 1-8 chars, uppercase (regex enforced
    at the DB level via prefix_shape CHECK constraint)
  - NNNN is a 4-digit zero-padded sequence drawn from `next_sequence` on this
    row (monotonic per row, allocated with row-lock in po_numbering service)

Invariants:
  - One row per (project_id, entity_type, middle_prefix). NULL middle is a
    distinct row from 'HAD', not lumped together; enforced via
    `UNIQUE NULLS NOT DISTINCT` (Postgres 15+).
  - At most one row with is_default=true per (project_id, entity_type),
    enforced by the `pnp_enforce_single_default` AFTER-trigger.
  - middle_prefix is immutable in the API layer once any PO references this
    row (R2 service-layer guard; no DB-level constraint).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


PREFIX_ENTITY_TYPES = ("po", "bill")


class ProjectNumberPrefix(Base):
    __tablename__ = "project_number_prefixes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    entity_type: Mapped[str] = mapped_column(String(10), nullable=False)
    middle_prefix: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    is_archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false"),
    )
    next_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1"),
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )
    updated_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False,
    )
