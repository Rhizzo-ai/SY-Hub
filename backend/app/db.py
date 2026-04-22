"""Database engine, session factory, declarative Base.

Uses SQLAlchemy 2.x with psycopg3. Every table inherits from Base and gets
id (uuid), tenant_id (uuid FK), created_at, updated_at automatically via
TimestampMixin + BaseModel.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime

from sqlalchemy import create_engine, event, DateTime, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    sessionmaker,
    Session,
)


DATABASE_URL = os.environ["DATABASE_URL"]

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class TenantScopedMixin:
    # Populated by router layer on insert; defined here so every business
    # table shares the same column shape.
    @classmethod
    def tenant_fk(cls):
        return mapped_column(
            UUID(as_uuid=True),
            ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        )


def uuid4() -> uuid.UUID:
    return uuid.uuid4()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Register a global trigger function + per-table triggers for auto-updated_at.
UPDATED_AT_FN_SQL = """
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def ensure_updated_at_trigger(conn, table_name: str) -> None:
    trg_name = f"trg_{table_name}_updated_at"
    conn.exec_driver_sql(
        f"DROP TRIGGER IF EXISTS {trg_name} ON {table_name};"
    )
    conn.exec_driver_sql(
        f"""
        CREATE TRIGGER {trg_name}
        BEFORE UPDATE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )
