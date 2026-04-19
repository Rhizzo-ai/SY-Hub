"""0001 initial — tenants + entities + enums + triggers (Prompt 1.1).

Reproduces the schema previously bootstrapped via Base.metadata.create_all().
The existing database was stamped to this revision; no data migration needed.

Revision ID: 0001_initial_entities
Revises:
Create Date: 2026-04-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql import func


revision = "0001_initial_entities"
down_revision = None
branch_labels = None
depends_on = None


ENTITY_TYPES = ("Parent", "SPV", "ConstructionCo", "JV_Vehicle", "Other")
VAT_SCHEMES = (
    "Standard_Quarterly",
    "Standard_Monthly",
    "Cash_Accounting",
    "Flat_Rate",
    "Not_Registered",
)
VAT_RETURN_PERIODS = (
    "Jan_Apr_Jul_Oct",
    "Feb_May_Aug_Nov",
    "Mar_Jun_Sep_Dec",
    "Monthly",
)
CIS_STATUSES = ("Contractor", "Subcontractor", "Both", "None")
ENTITY_STATUSES = ("Active", "Dormant", "Struck_off")


TRIGGER_FN_UP = """
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

TRIGGER_FN_DOWN = "DROP FUNCTION IF EXISTS set_updated_at();"


def _attach_updated_at(table_name: str) -> None:
    op.execute(
        f"""
        DROP TRIGGER IF EXISTS trg_{table_name}_updated_at ON {table_name};
        CREATE TRIGGER trg_{table_name}_updated_at
        BEFORE UPDATE ON {table_name}
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
        """
    )


def _detach_updated_at(table_name: str) -> None:
    op.execute(f"DROP TRIGGER IF EXISTS trg_{table_name}_updated_at ON {table_name};")


def upgrade() -> None:
    # Extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    # Shared trigger function
    op.execute(TRIGGER_FN_UP)

    # Enums
    entity_type = postgresql.ENUM(*ENTITY_TYPES, name="entity_type")
    vat_scheme = postgresql.ENUM(*VAT_SCHEMES, name="vat_scheme")
    vat_return_period = postgresql.ENUM(*VAT_RETURN_PERIODS, name="vat_return_period")
    cis_status = postgresql.ENUM(*CIS_STATUSES, name="cis_status")
    entity_status = postgresql.ENUM(*ENTITY_STATUSES, name="entity_status")
    for e in (entity_type, vat_scheme, vat_return_period, cis_status, entity_status):
        e.create(op.get_bind(), checkfirst=True)

    # tenants
    op.create_table(
        "tenants",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )
    _attach_updated_at("tenants")

    # entities
    op.create_table(
        "entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=False),
        sa.Column(
            "entity_type",
            postgresql.ENUM(
                *ENTITY_TYPES, name="entity_type", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "parent_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("companies_house_number", sa.String(length=10), nullable=True),
        sa.Column("vat_number", sa.String(length=15), nullable=True),
        sa.Column(
            "vat_scheme",
            postgresql.ENUM(*VAT_SCHEMES, name="vat_scheme", create_type=False),
            nullable=False,
            server_default=sa.text("'Standard_Quarterly'::vat_scheme"),
        ),
        sa.Column(
            "vat_return_period",
            postgresql.ENUM(
                *VAT_RETURN_PERIODS, name="vat_return_period", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'Mar_Jun_Sep_Dec'::vat_return_period"),
        ),
        sa.Column("utr", sa.String(length=13), nullable=True),
        sa.Column(
            "cis_status",
            postgresql.ENUM(*CIS_STATUSES, name="cis_status", create_type=False),
            nullable=True,
            server_default=sa.text("'None'::cis_status"),
        ),
        sa.Column("registered_address", sa.Text(), nullable=False),
        sa.Column("trading_address", sa.Text(), nullable=True),
        sa.Column("xero_org_id", sa.String(length=100), nullable=True),
        sa.Column("xero_org_name", sa.String(length=255), nullable=True),
        sa.Column(
            "default_currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'GBP'"),
        ),
        sa.Column("incorporation_date", sa.Date(), nullable=True),
        sa.Column("year_end", sa.String(length=5), nullable=True),
        sa.Column("el_insurance_expires", sa.Date(), nullable=True),
        sa.Column("pl_insurance_expires", sa.Date(), nullable=True),
        sa.Column("pi_insurance_expires", sa.Date(), nullable=True),
        sa.Column("all_risks_insurance_expires", sa.Date(), nullable=True),
        sa.Column("bank_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_name", sa.String(length=255), nullable=True),
        sa.Column("bank_account_number_masked", sa.String(length=10), nullable=True),
        sa.Column(
            "status",
            postgresql.ENUM(
                *ENTITY_STATUSES, name="entity_status", create_type=False
            ),
            nullable=False,
            server_default=sa.text("'Active'::entity_status"),
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
    )
    _attach_updated_at("entities")

    # Indexes
    op.create_index("ix_entities_tenant_id", "entities", ["tenant_id"])
    op.create_index("ix_entities_parent_entity_id", "entities", ["parent_entity_id"])
    op.create_index(
        "uq_entities_companies_house_number",
        "entities",
        ["tenant_id", "companies_house_number"],
        unique=True,
        postgresql_where=sa.text("companies_house_number IS NOT NULL"),
    )
    op.create_index(
        "uq_entities_vat_number",
        "entities",
        ["tenant_id", "vat_number"],
        unique=True,
        postgresql_where=sa.text("vat_number IS NOT NULL"),
    )
    op.create_index(
        "ix_entities_type_status",
        "entities",
        ["tenant_id", "entity_type", "status"],
    )
    op.create_index(
        "ix_entities_xero_org_id",
        "entities",
        ["xero_org_id"],
        postgresql_where=sa.text("xero_org_id IS NOT NULL"),
    )


def downgrade() -> None:
    _detach_updated_at("entities")
    op.drop_index("ix_entities_xero_org_id", table_name="entities")
    op.drop_index("ix_entities_type_status", table_name="entities")
    op.drop_index("uq_entities_vat_number", table_name="entities")
    op.drop_index("uq_entities_companies_house_number", table_name="entities")
    op.drop_index("ix_entities_parent_entity_id", table_name="entities")
    op.drop_index("ix_entities_tenant_id", table_name="entities")
    op.drop_table("entities")

    _detach_updated_at("tenants")
    op.drop_table("tenants")

    for name in (
        "entity_status",
        "cis_status",
        "vat_return_period",
        "vat_scheme",
        "entity_type",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name};")

    op.execute(TRIGGER_FN_DOWN)
