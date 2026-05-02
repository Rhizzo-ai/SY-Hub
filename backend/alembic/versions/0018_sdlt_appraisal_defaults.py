"""0018 Track 2 — SDLT bands + appraisal default settings (Prompt 2.1)

Revision ID: 0018_sdlt_appraisal_defaults
Revises: 0017_audit_remediation_patch_3

Creates two reference tables used by the appraisal engine (Prompt 2.2):

- `sdlt_rate_bands` — global (no tenant_id). Append-only versioning
  via (effective_from, effective_to). New structure = new rows; the
  prior active set gets effective_to = day_before(new_effective_from).
- `appraisal_default_settings` — tenant-scoped. UNIQUE
  (tenant_id, setting_key, applies_to_project_type). `null`
  applies_to_project_type means "all project types".

Reuses the existing `project_type_enum` from migration 0010
(1.5 projects) — does NOT define a parallel type.

Seeds (inline, one summary audit each):
- SDLT: 15 bands across 4 categories, effective 2025-04-01, effective_to=null.
- Appraisal defaults: 10 keys for the live SY Homes tenant. Tenant UUID
  and bootstrap super_admin UUID are resolved at runtime — not
  hardcoded. If either cannot be resolved, the migration raises so the
  deployer addresses the missing precondition before moving on.

Audit emissions:
- One 'Seed_Run' row for the SDLT seed batch.
- One 'Seed_Run' row for the appraisal-defaults seed batch.
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID as PG_UUID


revision = "0018_sdlt_appraisal_defaults"
down_revision = "0017_audit_remediation_patch_3"
branch_labels = None
depends_on = None


MIGRATION_AUDIT_NAMESPACE = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0018")

SDLT_CATEGORIES = (
    "Residential_Standard",
    "Residential_Surcharge",
    "Non_Residential",
    "Corporate_Flat_Rate",
)
APPRAISAL_SETTING_TYPES = ("Percentage", "Absolute", "Boolean")

# effective_from for the initial seed. Matches spec.
SEED_EFFECTIVE_FROM = date(2025, 4, 1)

# (category, band_lower, band_upper, rate_pct, notes)
SDLT_SEED: list[tuple[str, Decimal, Decimal | None, Decimal, str | None]] = [
    # Residential_Standard (5)
    ("Residential_Standard", Decimal("0"),       Decimal("125000"),  Decimal("0.000"), None),
    ("Residential_Standard", Decimal("125000"),  Decimal("250000"),  Decimal("2.000"), None),
    ("Residential_Standard", Decimal("250000"),  Decimal("925000"),  Decimal("5.000"), None),
    ("Residential_Standard", Decimal("925000"),  Decimal("1500000"), Decimal("10.000"), None),
    ("Residential_Standard", Decimal("1500000"), None,               Decimal("12.000"), None),
    # Residential_Surcharge (5)  — +5% per band
    ("Residential_Surcharge", Decimal("0"),       Decimal("125000"),  Decimal("5.000"),  "Additional dwelling / company purchaser surcharge"),
    ("Residential_Surcharge", Decimal("125000"),  Decimal("250000"),  Decimal("7.000"),  None),
    ("Residential_Surcharge", Decimal("250000"),  Decimal("925000"),  Decimal("10.000"), None),
    ("Residential_Surcharge", Decimal("925000"),  Decimal("1500000"), Decimal("15.000"), None),
    ("Residential_Surcharge", Decimal("1500000"), None,               Decimal("17.000"), None),
    # Non_Residential (3)
    ("Non_Residential", Decimal("0"),      Decimal("150000"), Decimal("0.000"), None),
    ("Non_Residential", Decimal("150000"), Decimal("250000"), Decimal("2.000"), None),
    ("Non_Residential", Decimal("250000"), None,              Decimal("5.000"), None),
    # Corporate_Flat_Rate (1) — >£500k for companies buying dwellings
    ("Corporate_Flat_Rate", Decimal("500000"), None, Decimal("17.000"),
     "Applies to companies buying dwellings >£500k. "
     "Developer relief may apply — see developer_relief flag on appraisal."),
]

# (setting_key, setting_value, setting_type, applies_to_project_type, description)
APPRAISAL_SEED: list[tuple[str, Decimal, str, str | None, str]] = [
    ("default_hurdle_on_cost_pct",    Decimal("20.0000"), "Percentage", None,
     "Target minimum profit on total cost"),
    ("default_hurdle_on_gdv_pct",     Decimal("17.0000"), "Percentage", None,
     "Alternative target — profit on GDV"),
    ("default_contingency_pct",       Decimal("5.0000"),  "Percentage", None,
     "Design+construction contingency as % of build"),
    ("default_architect_fee_pct",     Decimal("6.0000"),  "Percentage", None,
     "Architect fee as % of build"),
    ("default_structural_fee_pct",    Decimal("1.5000"),  "Percentage", None,
     "Structural engineer fee as % of build"),
    ("default_qs_fee_pct",            Decimal("1.0000"),  "Percentage", None,
     "QS fee as % of build"),
    ("default_selling_agents_pct",    Decimal("1.5000"),  "Percentage", None,
     "Selling agents as % of GDV"),
    ("default_legal_on_sale_pct",     Decimal("0.2500"),  "Percentage", None,
     "Legal fees on sale as % of GDV"),
    ("default_prelims_pct",           Decimal("12.0000"), "Percentage", "Dev_Build",
     "Prelims as % of build for Dev_Build"),
    ("default_mc_oh_p_pct",           Decimal("5.0000"),  "Percentage", "Dev_Build",
     "MC OH&P as % of build for Dev_Build"),
]


def upgrade() -> None:
    # Patch #3: the Seed_Run enum value is officially added in 0017, but
    # belt-and-braces the idempotent guard here in case this migration
    # ever runs against a DB that's stuck before 0017 for any reason.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'Seed_Run'")

    sdlt_cat_enum = sa.Enum(*SDLT_CATEGORIES, name="sdlt_band_category", create_type=True)
    setting_type_enum = sa.Enum(
        *APPRAISAL_SETTING_TYPES, name="appraisal_setting_type", create_type=True,
    )

    # ------------------------------------------------------------
    # sdlt_rate_bands — global, no tenant_id.
    # ------------------------------------------------------------
    op.create_table(
        "sdlt_rate_bands",
        sa.Column("id", PG_UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("effective_from", sa.Date, nullable=False),
        sa.Column("effective_to", sa.Date),
        sa.Column("category", sdlt_cat_enum, nullable=False),
        sa.Column("band_lower", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("band_upper", sa.Numeric(14, 2)),
        sa.Column("rate_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("notes", sa.Text),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_sdlt_rate_bands_category_from_to",
        "sdlt_rate_bands",
        ["category", "effective_from", "effective_to"],
    )
    op.execute(
        "CREATE TRIGGER trg_sdlt_rate_bands_updated_at "
        "BEFORE UPDATE ON sdlt_rate_bands "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # ------------------------------------------------------------
    # appraisal_default_settings — tenant-scoped. Reuses project_type_enum.
    # ------------------------------------------------------------
    op.create_table(
        "appraisal_default_settings",
        sa.Column("id", PG_UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("setting_key", sa.String(100), nullable=False),
        sa.Column("setting_value", sa.Numeric(14, 4), nullable=False),
        sa.Column("setting_type", setting_type_enum, nullable=False),
        sa.Column(
            "applies_to_project_type",
            # Reuses `project_type_enum` defined in migration 0010 (1.5).
            # Postgres-dialect ENUM honours create_type=False reliably
            # inside op.create_table — the generic sa.Enum still emits
            # CREATE TYPE here, which would fail as the type already exists.
            PG_ENUM(
                "Pure_Dev", "Dev_Build", "DB_Contract", "JV", "Main_Contract",
                name="project_type_enum", create_type=False,
            ),
        ),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("updated_by_user_id", PG_UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "tenant_id", "setting_key", "applies_to_project_type",
            # Postgres treats NULL as distinct, so we also need a partial
            # unique index to handle the "NULL applies_to_project_type"
            # case as a single slot per (tenant_id, setting_key).
            name="uq_appraisal_setting_key_scope",
        ),
    )
    # Partial unique index: one row per (tenant, key) when the scope is NULL.
    op.execute("""
        CREATE UNIQUE INDEX uq_appraisal_setting_key_scope_null
        ON appraisal_default_settings (tenant_id, setting_key)
        WHERE applies_to_project_type IS NULL;
    """)
    op.create_index(
        "ix_appraisal_default_settings_tenant",
        "appraisal_default_settings", ["tenant_id"],
    )
    op.execute(
        "CREATE TRIGGER trg_appraisal_default_settings_updated_at "
        "BEFORE UPDATE ON appraisal_default_settings "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )

    # ------------------------------------------------------------
    # Seeds
    # ------------------------------------------------------------
    bind = op.get_bind()

    # --- SDLT ---
    sdlt_inserted = 0
    for (cat, lo, hi, rate, note) in SDLT_SEED:
        bind.execute(text("""
            INSERT INTO sdlt_rate_bands
                (effective_from, effective_to, category,
                 band_lower, band_upper, rate_pct, notes)
            VALUES
                (:eff_from, NULL, :cat, :lo, :hi, :rate, :note)
        """), {
            "eff_from": SEED_EFFECTIVE_FROM,
            "cat": cat, "lo": lo, "hi": hi, "rate": rate, "note": note,
        })
        sdlt_inserted += 1

    rev_uuid = uuid.uuid5(MIGRATION_AUDIT_NAMESPACE, revision + ":sdlt")
    bind.execute(text("""
        INSERT INTO audit_log
            (id, action, resource_type, resource_id, field_changes,
             metadata_json, created_at)
        VALUES (gen_random_uuid(), 'Seed_Run', 'sdlt_rate_bands', :rid,
                CAST('[]' AS jsonb), CAST(:meta AS jsonb), :now)
    """), {
        "rid": str(rev_uuid),
        "meta": json.dumps({
            "kind": "seed_run", "revision": revision,
            "target": "sdlt_rate_bands",
            "rows_seeded": sdlt_inserted,
            "effective_from": SEED_EFFECTIVE_FROM.isoformat(),
            "categories_count": 4,
        }),
        "now": datetime.now(timezone.utc),
    })

    # --- Appraisal defaults ---
    # Resolve the single live tenant and the bootstrap super_admin user.
    tenant_row = bind.execute(text(
        "SELECT id FROM tenants ORDER BY created_at ASC LIMIT 1"
    )).first()
    if tenant_row is None:
        raise RuntimeError(
            "0018 seed cannot run: no tenants present. Run the tenant "
            "seed (lifespan seed()) before applying this migration."
        )
    tenant_id = tenant_row[0]

    # Resolve any active super_admin user. Prefer the earliest (bootstrap).
    super_user_row = bind.execute(text("""
        SELECT u.id FROM users u
        JOIN user_roles ur ON ur.user_id = u.id AND ur.status = 'Active'
        JOIN roles r ON r.id = ur.role_id AND r.code = 'super_admin'
        WHERE u.status = 'Active'
        ORDER BY u.created_at ASC
        LIMIT 1
    """)).first()
    if super_user_row is None:
        raise RuntimeError(
            "0018 seed cannot run: no Active super_admin user present. "
            "Run scripts/seed_test_users.py or the production bootstrap "
            "before applying this migration."
        )
    super_user_id = super_user_row[0]

    appraisal_inserted = 0
    for (key, val, stype, scope, desc) in APPRAISAL_SEED:
        bind.execute(text("""
            INSERT INTO appraisal_default_settings
                (tenant_id, setting_key, setting_value, setting_type,
                 applies_to_project_type, description, updated_by_user_id)
            VALUES
                (:tid, :k, :v, :st, :scope, :d, :uid)
            ON CONFLICT (tenant_id, setting_key, applies_to_project_type)
                DO NOTHING
        """), {
            "tid": str(tenant_id),
            "k": key, "v": val, "st": stype,
            "scope": scope, "d": desc,
            "uid": str(super_user_id),
        })
        appraisal_inserted += 1

    rev_uuid2 = uuid.uuid5(MIGRATION_AUDIT_NAMESPACE, revision + ":appraisal")
    bind.execute(text("""
        INSERT INTO audit_log
            (id, action, resource_type, resource_id, field_changes,
             metadata_json, actor_user_id, created_at)
        VALUES (gen_random_uuid(), 'Seed_Run', 'appraisal_default_settings',
                :rid, CAST('[]' AS jsonb), CAST(:meta AS jsonb),
                :actor, :now)
    """), {
        "rid": str(rev_uuid2),
        "meta": json.dumps({
            "kind": "seed_run", "revision": revision,
            "target": "appraisal_default_settings",
            "tenant_id": str(tenant_id),
            "rows_seeded": appraisal_inserted,
        }),
        "actor": str(super_user_id),
        "now": datetime.now(timezone.utc),
    })


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_appraisal_default_settings_updated_at ON appraisal_default_settings;")
    op.drop_index(
        "ix_appraisal_default_settings_tenant",
        table_name="appraisal_default_settings",
    )
    op.execute("DROP INDEX IF EXISTS uq_appraisal_setting_key_scope_null;")
    op.drop_table("appraisal_default_settings")
    op.execute("DROP TYPE IF EXISTS appraisal_setting_type;")

    op.execute("DROP TRIGGER IF EXISTS trg_sdlt_rate_bands_updated_at ON sdlt_rate_bands;")
    op.drop_index("ix_sdlt_rate_bands_category_from_to", table_name="sdlt_rate_bands")
    op.drop_table("sdlt_rate_bands")
    op.execute("DROP TYPE IF EXISTS sdlt_band_category;")
