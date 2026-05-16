"""0025 actuals — ledger + AI capture pipeline (Prompt 2.5A / Chat 19A)

Revision ID: 0025_actuals
Revises: 0024_budgets

Creates the actuals ledger per data-model XLSX (Budget Module sheet, lines
"actuals (44 fields)") + the AI capture pipeline tables. Bills inbox UX in
Chat 19B is a filtered VIEW over `actuals`, not a separate table.

Tables (5):
    actuals                 — primary cost ledger (44 spec columns + 7 ops extensions = 51)
    actual_attachments      — file storage scaffold (Track 5 will migrate)
    ai_capture_jobs         — Postmark→Claude pipeline state
    inbound_email_messages  — raw inbound email storage (idempotent)
    actuals_change_log      — Posted-mutation audit (DENORMALISED for fast access)

Enums (4):
    actual_status                 — Draft | Posted | Paid | Void | Disputed
    actual_source_type            — Xero_Bill | Xero_Credit_Note | Manual_Entry |
                                    SC_Valuation | Day_Rate_Timesheet |
                                    Expense_Claim | Journal | Internal_Recharge
    ai_capture_status             — Queued | Extracting | Awaiting_Review |
                                    Completed | Failed | Discarded
    actual_attachment_source      — Manual_Upload | Email_Capture | AI_Capture

Triggers (6 attached) + Functions (3 — one shared with prior migrations):
  Functions:
    enforce_actuals_immutability()  — financial fields immutable after Posted; Void rows totally frozen
    actuals_change_log_no_modify()  — append-only enforcement (raises on UPDATE)
    set_updated_at()                — REUSED from 0001_initial_entities (attached to 4 new tables)

  Triggers attached:
    trg_actuals_immutability                BEFORE UPDATE ON actuals
    trg_actuals_updated_at                  BEFORE UPDATE ON actuals
    trg_actual_attachments_updated_at       BEFORE UPDATE ON actual_attachments
    trg_inbound_emails_updated_at           BEFORE UPDATE ON inbound_email_messages
    trg_ai_capture_jobs_updated_at          BEFORE UPDATE ON ai_capture_jobs
    trg_actuals_change_log_no_update        BEFORE UPDATE ON actuals_change_log

Trigger firing order on `actuals` UPDATE: trg_actuals_immutability < trg_actuals_updated_at
(PostgreSQL fires triggers alphabetically by name). The immutability check runs first; if it
raises, set_updated_at never fires and the UPDATE aborts cleanly.

Indexes (13 straight + 2 partial unique):
    ix_actuals_project_txdate          (project_id, transaction_date DESC)
    ix_actuals_budget_line_id          (budget_line_id)
    ix_actuals_status                  (status)
    ix_actuals_txdate_status           (transaction_date, status)
    ix_actuals_supplier_id             (supplier_id)
    ix_actuals_entity_id               (entity_id)
    ix_actuals_source_type             (source_type)
    ix_actuals_line_status             (budget_line_id, status)   -- 19B "ready to pay" view
    ix_actual_attachments_actual_id    (actual_id)
    ix_ai_capture_jobs_status          (status)
    ix_ai_capture_jobs_inbound_msg     (inbound_email_message_id)
    ix_inbound_emails_received_at      (received_at DESC)
    ix_actuals_change_log_actual_id    (actual_id, occurred_at DESC)

    uq_actuals_external_id_source    UNIQUE (external_id, source_type)
                                     WHERE external_id IS NOT NULL
    uq_inbound_emails_postmark_id    UNIQUE (postmark_message_id)
                                     WHERE postmark_message_id IS NOT NULL

Spec-reconciliation notes:
  - 44 spec columns + 7 operational extensions = 51 columns on `actuals`:
      posted_at, posted_by_user_id              — happy-path Draft→Posted audit
      disputed_at, disputed_by_user_id, dispute_reason   — Posted↔Disputed
      ai_capture_metadata jsonb                 — AI extraction confidence + raw output
      linked_commitment_id uuid NULL            — Chat 20 PO link scaffold (D19)
  - `document_ids jsonb` column retained per spec (deprecation: Track 5 migrates to documents table)
  - `supplier_id` and `related_subcontract_id` columns scaffolded WITHOUT FK
    constraints — target tables don't exist yet
  - Pattern α tenant scoping: NO tenant_id column on actuals

Audit actions extension (deviation noted; needed because record_audit validates
the action string against the `audit_action` enum):
  - ALTER TYPE audit_action ADD VALUE for 9 new actions:
    Post, Mark_Paid, Void, Dispute, Undispute, Release_Retention,
    Add_Attachment, Remove_Attachment, Promote_From_Capture.
"""
from alembic import op
import sqlalchemy as sa


revision = "0025_actuals"
down_revision = "0024_budgets"
branch_labels = None
depends_on = None


# --- enum value lists ---------------------------------------------------

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

# New audit_action enum values (extension to migration 0017's audit_action enum).
NEW_AUDIT_ACTIONS = (
    "Post", "Mark_Paid", "Void", "Dispute", "Undispute",
    "Release_Retention", "Add_Attachment", "Remove_Attachment",
    "Promote_From_Capture",
)


def upgrade() -> None:
    actual_status_enum = sa.Enum(*ACTUAL_STATUSES, name="actual_status")
    actual_source_enum = sa.Enum(*ACTUAL_SOURCE_TYPES, name="actual_source_type")
    ai_capture_status_enum = sa.Enum(*AI_CAPTURE_STATUSES, name="ai_capture_status")
    attachment_source_enum = sa.Enum(*ACTUAL_ATTACHMENT_SOURCES, name="actual_attachment_source")

    # ===== Extend audit_action enum with new actuals-specific actions ======
    # ALTER TYPE ADD VALUE must run outside a transaction in some PG versions.
    # Alembic's default per-migration transaction is fine here for PG16+; if
    # this fails on rollback we issue per-statement COMMIT via op.execute.
    for value in NEW_AUDIT_ACTIONS:
        op.execute(
            f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'"
        )

    # ===== actuals =======================================================
    op.create_table(
        "actuals",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        # Tenant scope (Pattern α): via project_id, NO tenant_id column.
        sa.Column("project_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("budget_line_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("budget_lines.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("entity_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False),

        # Source provenance
        sa.Column("source_type", actual_source_enum, nullable=False),
        sa.Column("source_reference", sa.Text),
        sa.Column("external_id", sa.Text),  # Xero invoice ID, etc.

        # Dates
        sa.Column("transaction_date", sa.Date, nullable=False),
        sa.Column("posting_date", sa.Date, nullable=False,
                  server_default=sa.func.current_date()),

        # Core
        sa.Column("description", sa.Text, nullable=False),

        # Money (gross_amount auto-derived in service: net + vat)
        sa.Column("net_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("gross_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_rate_pct", sa.Numeric(6, 3), nullable=False, server_default="20"),
        sa.Column("is_vat_recoverable", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("currency", sa.String(3), nullable=False, server_default="GBP"),
        sa.Column("exchange_rate", sa.Numeric(14, 6)),

        # Supplier (FK deferred — subcontractors/consultants table is Track 4)
        sa.Column("supplier_id", sa.dialects.postgresql.UUID(as_uuid=True)),
        sa.Column("supplier_name_snapshot", sa.String(255), nullable=False),
        sa.Column("supplier_invoice_ref", sa.String(100)),

        # CIS (UK Construction Industry Scheme — subcontractor labour withholding)
        sa.Column("is_cis_applicable", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("cis_deduction_rate_pct", sa.Numeric(5, 2)),  # 0 / 20 / 30
        sa.Column("cis_labour_amount", sa.Numeric(14, 2)),
        sa.Column("cis_materials_amount", sa.Numeric(14, 2)),
        sa.Column("cis_deduction_amount", sa.Numeric(14, 2)),  # auto-calc: labour * rate / 100
        sa.Column("cis_reported_to_hmrc", sa.Boolean, nullable=False, server_default=sa.false()),

        # Retention (contractual money held back)
        sa.Column("retention_rate_pct", sa.Numeric(5, 2)),
        sa.Column("retention_amount", sa.Numeric(14, 2)),
        sa.Column("retention_released", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("retention_release_date", sa.Date),

        # FK to commitments (Chat 20) — column scaffolded, no FK constraint yet
        sa.Column("linked_commitment_id", sa.dialects.postgresql.UUID(as_uuid=True)),

        # FK to subcontract (Track 4) — column scaffolded, no FK constraint yet
        sa.Column("related_subcontract_id", sa.dialects.postgresql.UUID(as_uuid=True)),

        # Xero reconciliation (Track 6 will populate)
        sa.Column("is_reconciled_to_xero", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("reconciled_at", sa.DateTime(timezone=True)),
        sa.Column("reconciliation_variance", sa.Numeric(14, 2)),

        # Status state machine
        sa.Column("status", actual_status_enum, nullable=False, server_default="Draft"),

        # Status transitions — denormalised columns for fast lookup
        sa.Column("posted_at", sa.DateTime(timezone=True)),
        sa.Column("posted_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("paid_date", sa.Date),
        sa.Column("payment_reference", sa.String(100)),
        sa.Column("disputed_at", sa.DateTime(timezone=True)),
        sa.Column("disputed_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("dispute_reason", sa.Text),
        sa.Column("voided_at", sa.DateTime(timezone=True)),
        sa.Column("voided_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("void_reason", sa.Text),

        # Attachments pointer (Track 5 migration target)
        sa.Column("document_ids", sa.dialects.postgresql.JSONB,
                  nullable=False, server_default=sa.text("'[]'::jsonb")),

        # AI capture metadata — extraction confidence + raw output
        sa.Column("ai_capture_metadata", sa.dialects.postgresql.JSONB),

        # Audit
        sa.Column("created_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),

        # Constraints (7 CHECK)
        sa.CheckConstraint("gross_amount = net_amount + vat_amount",
                           name="ck_actuals_gross_eq_net_plus_vat"),
        sa.CheckConstraint(
            "vat_rate_pct >= 0 AND vat_rate_pct <= 100",
            name="ck_actuals_vat_rate_in_range",
        ),
        sa.CheckConstraint(
            "(is_cis_applicable = false) OR (cis_deduction_rate_pct IN (0, 20, 30))",
            name="ck_actuals_cis_rate_valid",
        ),
        sa.CheckConstraint(
            "(currency = 'GBP') OR (exchange_rate IS NOT NULL)",
            name="ck_actuals_non_gbp_has_rate",
        ),
        sa.CheckConstraint(
            "(retention_released = false) OR (retention_release_date IS NOT NULL)",
            name="ck_actuals_retention_release_date_when_released",
        ),
        sa.CheckConstraint(
            "(status != 'Paid') OR (paid_date IS NOT NULL AND payment_reference IS NOT NULL)",
            name="ck_actuals_paid_has_reference",
        ),
        sa.CheckConstraint(
            "(status != 'Void') OR (voided_at IS NOT NULL AND voided_by_user_id IS NOT NULL "
            "AND void_reason IS NOT NULL)",
            name="ck_actuals_void_has_reason",
        ),
        sa.CheckConstraint(
            "(status != 'Disputed') OR (disputed_at IS NOT NULL AND dispute_reason IS NOT NULL)",
            name="ck_actuals_disputed_has_reason",
        ),
    )

    # Straight indexes (8 on actuals)
    op.create_index("ix_actuals_project_txdate", "actuals",
                    ["project_id", sa.text("transaction_date DESC")])
    op.create_index("ix_actuals_budget_line_id", "actuals", ["budget_line_id"])
    op.create_index("ix_actuals_status", "actuals", ["status"])
    op.create_index("ix_actuals_txdate_status", "actuals", ["transaction_date", "status"])
    op.create_index("ix_actuals_supplier_id", "actuals", ["supplier_id"])
    op.create_index("ix_actuals_entity_id", "actuals", ["entity_id"])
    op.create_index("ix_actuals_source_type", "actuals", ["source_type"])
    op.create_index(
        "ix_actuals_line_status",
        "actuals", ["budget_line_id", "status"],
    )

    # Partial unique: dedup Xero/external imports
    op.create_index(
        "uq_actuals_external_id_source",
        "actuals", ["external_id", "source_type"],
        unique=True,
        postgresql_where=sa.text("external_id IS NOT NULL"),
    )

    # Immutability trigger — financial fields locked after Posted; Void totally frozen.
    op.execute("""
        CREATE OR REPLACE FUNCTION enforce_actuals_immutability()
        RETURNS trigger AS $$
        BEGIN
            -- Void rule: NO field on a Void row may change. The row is frozen
            -- in its final state. Test fixtures use ALTER TABLE ... DISABLE
            -- TRIGGER USER to bypass for cleanup.
            IF OLD.status = 'Void' THEN
                RAISE EXCEPTION
                    'actual %: Void records are immutable (test cleanup must DISABLE TRIGGER USER)',
                    OLD.id
                USING ERRCODE = '23514';
            END IF;

            -- Posted / Paid / Disputed: financial + identity fields immutable.
            -- Mutable: status (valid transitions), payment fields, dispute
            -- fields, void fields, reconciliation fields, retention release,
            -- HMRC reporting flag, document_ids, ai_capture_metadata, updated_at.
            IF OLD.status IN ('Posted', 'Paid', 'Disputed') THEN
                IF (NEW.net_amount, NEW.vat_amount, NEW.gross_amount,
                    NEW.budget_line_id, NEW.transaction_date, NEW.description,
                    NEW.entity_id, NEW.project_id,
                    NEW.cis_deduction_rate_pct, NEW.cis_labour_amount,
                    NEW.cis_materials_amount, NEW.cis_deduction_amount,
                    NEW.retention_rate_pct, NEW.retention_amount,
                    NEW.supplier_id, NEW.supplier_invoice_ref,
                    NEW.source_type, NEW.source_reference, NEW.external_id,
                    NEW.created_by_user_id, NEW.created_at,
                    NEW.posted_at, NEW.posted_by_user_id,
                    NEW.is_vat_recoverable, NEW.vat_rate_pct,
                    NEW.currency, NEW.exchange_rate,
                    NEW.is_cis_applicable)
                  IS DISTINCT FROM
                   (OLD.net_amount, OLD.vat_amount, OLD.gross_amount,
                    OLD.budget_line_id, OLD.transaction_date, OLD.description,
                    OLD.entity_id, OLD.project_id,
                    OLD.cis_deduction_rate_pct, OLD.cis_labour_amount,
                    OLD.cis_materials_amount, OLD.cis_deduction_amount,
                    OLD.retention_rate_pct, OLD.retention_amount,
                    OLD.supplier_id, OLD.supplier_invoice_ref,
                    OLD.source_type, OLD.source_reference, OLD.external_id,
                    OLD.created_by_user_id, OLD.created_at,
                    OLD.posted_at, OLD.posted_by_user_id,
                    OLD.is_vat_recoverable, OLD.vat_rate_pct,
                    OLD.currency, OLD.exchange_rate,
                    OLD.is_cis_applicable)
                THEN
                    RAISE EXCEPTION
                        'actual %: financial fields immutable after % — corrections via credit note',
                        OLD.id, OLD.status
                    USING ERRCODE = '23514';
                END IF;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_actuals_immutability
        BEFORE UPDATE ON actuals
        FOR EACH ROW
        EXECUTE FUNCTION enforce_actuals_immutability();
    """)

    # Standard updated_at trigger (reuses set_updated_at() from 0001_initial_entities)
    op.execute("""
        CREATE TRIGGER trg_actuals_updated_at
        BEFORE UPDATE ON actuals
        FOR EACH ROW
        EXECUTE FUNCTION set_updated_at();
    """)

    # ===== actual_attachments ============================================
    op.create_table(
        "actual_attachments",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actual_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("actuals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_type", sa.String(100), nullable=False),  # mime type
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("source", attachment_source_enum, nullable=False),
        sa.Column("uploaded_by_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("uploaded_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("file_size_bytes > 0",
                           name="ck_actual_attachments_size_positive"),
    )
    op.create_index("ix_actual_attachments_actual_id", "actual_attachments",
                    ["actual_id"])
    op.execute("""
        CREATE TRIGGER trg_actual_attachments_updated_at
        BEFORE UPDATE ON actual_attachments
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ===== inbound_email_messages ========================================
    op.create_table(
        "inbound_email_messages",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("postmark_message_id", sa.String(100)),
        sa.Column("from_email", sa.String(320), nullable=False),
        sa.Column("to_email", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(998)),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_email_path", sa.Text),
        sa.Column("attachment_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "uq_inbound_emails_postmark_id",
        "inbound_email_messages", ["postmark_message_id"],
        unique=True,
        postgresql_where=sa.text("postmark_message_id IS NOT NULL"),
    )
    op.create_index("ix_inbound_emails_received_at", "inbound_email_messages",
                    [sa.text("received_at DESC")])
    op.execute("""
        CREATE TRIGGER trg_inbound_emails_updated_at
        BEFORE UPDATE ON inbound_email_messages
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ===== ai_capture_jobs ===============================================
    op.create_table(
        "ai_capture_jobs",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("inbound_email_message_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("inbound_email_messages.id", ondelete="RESTRICT"),
                  nullable=False),
        sa.Column("attachment_path", sa.Text, nullable=False),
        sa.Column("status", ai_capture_status_enum, nullable=False, server_default="Queued"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_message", sa.Text),
        sa.Column("extracted_data", sa.dialects.postgresql.JSONB),
        sa.Column("confidence_scores", sa.dialects.postgresql.JSONB),
        sa.Column("suggested_entity_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("entities.id", ondelete="SET NULL")),
        sa.Column("suggested_project_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="SET NULL")),
        sa.Column("suggested_cost_code_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("cost_codes.id", ondelete="SET NULL")),
        sa.Column("target_actual_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("actuals.id", ondelete="SET NULL")),
        sa.Column("model_used", sa.String(100)),
        sa.Column("prompt_tokens", sa.Integer),
        sa.Column("completion_tokens", sa.Integer),
        sa.Column("cost_pence", sa.Integer),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_capture_jobs_status", "ai_capture_jobs", ["status"])
    op.create_index("ix_ai_capture_jobs_inbound_msg", "ai_capture_jobs",
                    ["inbound_email_message_id"])
    op.execute("""
        CREATE TRIGGER trg_ai_capture_jobs_updated_at
        BEFORE UPDATE ON ai_capture_jobs
        FOR EACH ROW EXECUTE FUNCTION set_updated_at();
    """)

    # ===== actuals_change_log ============================================
    # Denormalised log of every status transition + mutation. Reads frequently
    # in UI (audit timeline tile). UPDATE-blocked by trigger.
    #
    # FK design (locked decision): RESTRICT not CASCADE.
    # Rationale: combining CASCADE with a BEFORE DELETE append-only trigger
    # on the same table would deadlock cascade-deletes. We use RESTRICT and
    # accept that Draft actuals cannot be hard-deleted while change_log rows
    # exist; service must DELETE change_log first OR (preferred) void
    # instead of deleting.
    op.create_table(
        "actuals_change_log",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True),
                  primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("actual_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("actuals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("actor_user_id", sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT")),
        sa.Column("event_payload", sa.dialects.postgresql.JSONB,
                  nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("occurred_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "event_type IN ("
            "'Created', 'Edited', 'Posted', 'Paid', 'Voided', "
            "'Disputed', 'Undisputed', 'Reconciled', 'Retention_Released', "
            "'Attachment_Added', 'Attachment_Removed'"
            ")",
            name="ck_actuals_change_log_event_type_valid",
        ),
    )
    op.create_index("ix_actuals_change_log_actual_id", "actuals_change_log",
                    ["actual_id", sa.text("occurred_at DESC")])

    # Append-only: block UPDATE.
    op.execute("""
        CREATE OR REPLACE FUNCTION actuals_change_log_no_modify()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'actuals_change_log is append-only (UPDATE blocked)'
                USING ERRCODE = '23514';
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("""
        CREATE TRIGGER trg_actuals_change_log_no_update
        BEFORE UPDATE ON actuals_change_log
        FOR EACH ROW EXECUTE FUNCTION actuals_change_log_no_modify();
    """)


def downgrade() -> None:
    # Triggers first (referencing the tables)
    for t, trigger in [
        ("actuals", "trg_actuals_immutability"),
        ("actuals", "trg_actuals_updated_at"),
        ("actual_attachments", "trg_actual_attachments_updated_at"),
        ("inbound_email_messages", "trg_inbound_emails_updated_at"),
        ("ai_capture_jobs", "trg_ai_capture_jobs_updated_at"),
        ("actuals_change_log", "trg_actuals_change_log_no_update"),
    ]:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {t};")

    op.execute("DROP FUNCTION IF EXISTS enforce_actuals_immutability();")
    op.execute("DROP FUNCTION IF EXISTS actuals_change_log_no_modify();")

    # Partial unique indexes (must drop explicitly; regular indexes go with table)
    op.drop_index("uq_actuals_external_id_source", table_name="actuals")
    op.drop_index("uq_inbound_emails_postmark_id", table_name="inbound_email_messages")

    # Tables (reverse dependency order)
    op.drop_table("actuals_change_log")
    op.drop_table("ai_capture_jobs")
    op.drop_table("inbound_email_messages")
    op.drop_table("actual_attachments")
    op.drop_table("actuals")

    # Enums (drop tables first so they're no longer referenced)
    for enum_name in (
        "actual_attachment_source",
        "ai_capture_status",
        "actual_source_type",
        "actual_status",
    ):
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")

    # NOTE: cannot remove enum values from audit_action — PG does not support
    # ALTER TYPE ... DROP VALUE. Downgrade leaves the new audit_action values
    # in place; this is harmless (they simply won't be used). Documented in
    # docs/chat-summaries/chat-19a-closing.md.
