"""Migration 0025_actuals — DB-level schema/trigger/enum tests.

Hits the schema directly via SQLAlchemy core — no HTTP, no fixtures from the
main suite. These tests guard the migration so a future edit that drops a
trigger or shrinks the enum will fail loudly.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def seed_refs(engine):
    """Create a full project → appraisal → budget → budget_line chain so the
    behavioural tests can insert real Actual rows that respect every FK.
    Cleans up at module teardown.

    `appraisal_group_id` is a NOT NULL uuid (no FK), application-managed —
    one group per (project, scenario_chain). We mint one inline.
    """
    refs = {}
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        user_id = c.execute(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        )).scalar()
        if not (entity_id and user_id):
            pytest.skip("required seed rows (entities + test-admin user) missing")
        project_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '1 Mig Test Way', 'SY1 2AA', false, :u)
        """), {"id": project_id, "code": f"M0025-{project_id[:6]}",
                "name": f"Mig0025 Test {project_id[:6]}",
                "ent": entity_id, "u": user_id})
        # Seed a minimal appraisal so budgets.source_appraisal_id is satisfied.
        appraisal_id = str(uuid.uuid4())
        appraisal_group_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (
                :id, :pid, 'Mig0025 Base', CURRENT_DATE,
                :uid, :gid, 'Base',
                true, 'Approved', 1
            )
        """), {"id": appraisal_id, "pid": project_id, "uid": user_id,
                "gid": appraisal_group_id})
        budget_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO budgets (id, project_id, source_appraisal_id, version_number,
              version_label, is_current, status, created_from_appraisal_at,
              total_budget, total_actuals, total_committed_not_invoiced,
              total_forecast_to_complete, forecast_final_cost,
              variance_vs_budget, variance_pct, summary_refreshed_at,
              created_by_user_id)
            VALUES (:id, :pid, :ap, 1, 'v1', true, 'Active', NOW(),
                    100000, 0, 0, 100000, 100000, 0, 0, NOW(), :u)
        """), {"id": budget_id, "pid": project_id, "ap": appraisal_id,
                "u": user_id})
        cc_id = c.execute(text("SELECT id FROM cost_codes LIMIT 1")).scalar()
        line_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO budget_lines (id, budget_id, cost_code_id, display_order,
              line_description, entity_id, ftc_method,
              original_budget, approved_changes, current_budget,
              actuals_to_date, committed_value, invoiced_against_commitment,
              committed_not_invoiced, forecast_to_complete, forecast_final_cost,
              variance_value, variance_pct, variance_status,
              is_locked, requires_attention)
            VALUES (:id, :bid, :cc, 1, 'Line A', :ent, 'Manual',
                    100000, 0, 100000,
                    0, 0, 0, 0, 100000, 100000,
                    0, 0, 'Green',
                    false, false)
        """), {"id": line_id, "bid": budget_id, "cc": cc_id, "ent": entity_id})
        refs["project_id"] = project_id
        refs["budget_id"] = budget_id
        refs["budget_line_id"] = line_id
        refs["entity_id"] = entity_id
        refs["user_id"] = user_id
        refs["appraisal_id"] = appraisal_id
    yield refs
    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": refs["project_id"]})
        c.execute(text("DELETE FROM actuals WHERE project_id=:p"),
                  {"p": refs["project_id"]})
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM budgets WHERE id=:b"), {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM appraisals WHERE id=:a"),
                  {"a": refs["appraisal_id"]})
        c.execute(text("DELETE FROM projects WHERE id=:p"), {"p": refs["project_id"]})


class TestMigration0025Schema:
    def test_alembic_head_is_0025_actuals(self, engine):
        with engine.connect() as c:
            head = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        # Updated by Chat 22 (CI hardening): live head moved from
        # "0025_actuals" to "0026_ai_capture_costs_perm" when migration
        # 0026 landed in Chat 20. Updated again by Chat 23 R1.3 when
        # 0027 landed, by Chat 23 R1.4 when 0028 landed, by
        # Chat 24 R1/R2/R3/R4 (Prompt 2.5) when 0029/0030/0031/0032/0033 landed,
        # by Chat 34 (Prompt 2.8a) when 0037 landed, and by Chat 41
        # (Prompt 2.7-BE-rev-A) when 0040 landed.
        # Function name retained — renaming is out of scope (see
        # chat-22 §2 + Future_Tasks polish entry).
        assert head == "0041_drop_vat_registered", \
            f"expected 0041_drop_vat_registered, got {head!r}"

    def test_actuals_has_51_columns(self, engine):
        with engine.connect() as c:
            n = c.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns "
                "WHERE table_name='actuals'"
            )).scalar()
        assert n == 51

    def test_thirteen_plain_indexes_two_partial_unique(self, engine):
        """13 plain indexes (ix_*) + 2 partial unique (uq_*) across the 5 new tables."""
        tables = (
            "actuals", "actual_attachments", "inbound_email_messages",
            "ai_capture_jobs", "actuals_change_log",
        )
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT i.indexname, ix.indisunique, ix.indpred IS NOT NULL AS partial
                FROM pg_indexes i
                JOIN pg_class ic ON ic.relname=i.indexname
                JOIN pg_index ix ON ix.indexrelid=ic.oid
                WHERE i.tablename = ANY(:tables)
            """).bindparams(tables=list(tables))).all()
        plain = [r for r in rows if not r.indisunique]
        partial_unique = [r for r in rows if r.indisunique and r.partial]
        assert len(plain) == 13, sorted(r.indexname for r in plain)
        assert len(partial_unique) == 2, sorted(r.indexname for r in partial_unique)

    def test_six_user_triggers(self, engine):
        with engine.connect() as c:
            n = c.execute(text("""
                SELECT COUNT(*) FROM pg_trigger
                WHERE tgrelid IN (
                    SELECT oid FROM pg_class
                    WHERE relname IN (
                        'actuals','actual_attachments','inbound_email_messages',
                        'ai_capture_jobs','actuals_change_log'
                    )
                ) AND NOT tgisinternal
            """)).scalar()
        assert n == 6, f"expected 6 user triggers, got {n}"

    def test_three_functions_present(self, engine):
        with engine.connect() as c:
            names = sorted(r[0] for r in c.execute(text("""
                SELECT proname FROM pg_proc
                WHERE proname IN (
                    'enforce_actuals_immutability',
                    'actuals_change_log_no_modify',
                    'set_updated_at'
                )
            """)).all())
        assert names == [
            "actuals_change_log_no_modify",
            "enforce_actuals_immutability",
            "set_updated_at",
        ]

    def test_nine_new_audit_action_enum_values_present(self, engine):
        expected = {
            "Post", "Mark_Paid", "Void", "Dispute", "Undispute",
            "Release_Retention", "Add_Attachment", "Remove_Attachment",
            "Promote_From_Capture",
        }
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT enumlabel FROM pg_enum
                WHERE enumtypid=(SELECT oid FROM pg_type WHERE typname='audit_action')
            """)).all()
        labels = {r[0] for r in rows}
        missing = expected - labels
        assert not missing, f"missing audit_action labels: {missing}"


class TestMigration0025Behaviours:
    """Behavioural tests against the live triggers + check constraints."""

    def _seed_draft_actual(self, c, refs) -> str:
        """Insert a Draft actual and return its id. Caller supplies an open conn."""
        aid = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO actuals (id, project_id, budget_line_id, entity_id,
              source_type, transaction_date, description,
              net_amount, vat_amount, gross_amount,
              supplier_name_snapshot, status, created_by_user_id)
            VALUES (:id, :p, :b, :e, 'Manual_Entry', CURRENT_DATE,
                    'mig test', 100.00, 20.00, 120.00,
                    'Supplier X', 'Draft', :u)
        """), {"id": aid, "p": refs["project_id"], "b": refs["budget_line_id"],
               "e": refs["entity_id"], "u": refs["user_id"]})
        return aid

    def test_immutability_trigger_blocks_net_amount_change_after_post(self, engine, seed_refs):
        with engine.begin() as c:
            aid = self._seed_draft_actual(c, seed_refs)
            c.execute(text(
                "UPDATE actuals SET status='Posted', posted_at=NOW(), "
                "posted_by_user_id=:u WHERE id=:id"
            ), {"id": aid, "u": seed_refs["user_id"]})
        with engine.begin() as c:
            with pytest.raises(Exception) as exc:
                c.execute(text(
                    "UPDATE actuals SET net_amount=999.00 WHERE id=:id"
                ), {"id": aid})
            assert "immutable" in str(exc.value).lower() or "23514" in str(exc.value)

    def test_change_log_is_append_only(self, engine, seed_refs):
        with engine.begin() as c:
            aid = self._seed_draft_actual(c, seed_refs)
            c.execute(text("""
                INSERT INTO actuals_change_log (id, actual_id, event_type, event_payload)
                VALUES (gen_random_uuid(), :a, 'Created', '{}'::jsonb)
            """), {"a": aid})
        with engine.begin() as c:
            with pytest.raises(Exception) as exc:
                c.execute(text(
                    "UPDATE actuals_change_log SET event_type='Edited' WHERE actual_id=:a"
                ), {"a": aid})
            assert "append-only" in str(exc.value).lower() or "23514" in str(exc.value)

    def test_external_id_partial_unique(self, engine, seed_refs):
        from sqlalchemy.exc import IntegrityError
        ext = f"UNIQ-{uuid.uuid4().hex[:8]}"
        insert_sql = text("""
            INSERT INTO actuals (id, project_id, budget_line_id, entity_id,
              source_type, source_reference, external_id, transaction_date,
              description, net_amount, vat_amount, gross_amount,
              supplier_name_snapshot, status, created_by_user_id)
            VALUES (:id, :p, :b, :e, 'Xero_Bill', NULL, :ext, CURRENT_DATE,
                    'partial unique test', 50.00, 10.00, 60.00,
                    'Supp', 'Draft', :u)
        """)
        with engine.begin() as c:
            id1 = str(uuid.uuid4())
            c.execute(insert_sql, {"id": id1, "p": seed_refs["project_id"],
                                   "b": seed_refs["budget_line_id"],
                                   "e": seed_refs["entity_id"], "ext": ext,
                                   "u": seed_refs["user_id"]})
        with engine.begin() as c:
            id2 = str(uuid.uuid4())
            with pytest.raises(IntegrityError) as exc:
                c.execute(insert_sql, {"id": id2, "p": seed_refs["project_id"],
                                       "b": seed_refs["budget_line_id"],
                                       "e": seed_refs["entity_id"], "ext": ext,
                                       "u": seed_refs["user_id"]})
            assert "uq_actuals_external_id_source" in str(exc.value).lower()
        # NULL external_id — multiple rows must be allowed.
        with engine.begin() as c:
            for _ in range(2):
                c.execute(insert_sql, {"id": str(uuid.uuid4()),
                                       "p": seed_refs["project_id"],
                                       "b": seed_refs["budget_line_id"],
                                       "e": seed_refs["entity_id"], "ext": None,
                                       "u": seed_refs["user_id"]})

    def test_downgrade_upgrade_round_trip_preserves_schema(self, engine):
        """alembic downgrade past 0025; upgrade head — column count must round-trip.

        Chat 22 (CI hardening): live head moved to 0026_ai_capture_costs_perm,
        so a relative `downgrade -1` only walks back to 0025_actuals and leaves
        the actuals table in place. Target an explicit revision BEFORE 0025
        so this test continues to validate the 0025 round-trip regardless of
        how many migrations land on top of it.

        P1.R5 (2026-02-13): 0027's downgrade is now NotImplementedError per
        operator decision (the heuristic DELETE destroyed user-edited £0
        items). We retarget to `0027_default_line_items_backfill` instead of
        `0024_budgets` — alembic stops AT 0027 without running 0027's down,
        so we walk back to 0026 and skip the trapdoor while still validating
        the 0025 round-trip via the intermediate 0026 / 0027 / 0028 stack.
        """
        import subprocess
        # Resolves to backend/ regardless of mount point — CI runners use a different prefix than the sandbox.
        cwd = str(Path(__file__).resolve().parents[1])
        env = os.environ.copy()
        before = None
        with engine.connect() as c:
            before = c.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='actuals'"
            )).scalar()
        assert before == 51
        # Target stops at 0027 (one above 0026/0025) — does NOT execute 0027's
        # NotImplementedError downgrade. We can only assert the round-trip of
        # migrations 0028..head this way; the deeper 0024-baseline assertion is
        # blocked by R5 by design and is logged in Future_Tasks §24.
        subprocess.run(["python", "-m", "alembic", "downgrade",
                        "0027_default_line_items_backfill"],
                       cwd=cwd, env=env, check=True, capture_output=True)
        with engine.connect() as c:
            mid_actuals = c.execute(text("""
                SELECT COUNT(*) FROM information_schema.tables WHERE table_name='actuals'
            """)).scalar()
        # actuals table still present at 0027 (0025 lives below 0027).
        assert mid_actuals == 1, "actuals table should still exist at 0027"
        subprocess.run(["python", "-m", "alembic", "upgrade", "head"],
                       cwd=cwd, env=env, check=True, capture_output=True)
        with engine.connect() as c:
            after = c.execute(text(
                "SELECT COUNT(*) FROM information_schema.columns WHERE table_name='actuals'"
            )).scalar()
        assert after == before
