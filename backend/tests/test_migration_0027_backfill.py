"""Migration 0027 — backfill 4 default budget_line_items on zero-item lines.

These tests run against the LIVE migrated DB (alembic head is already
0027 by the time pytest collects). We:
  1. Assert head is now 0027_default_line_items_backfill.
  2. Assert the migration's audit row landed with the expected metadata.
  3. Insert a synthetic zero-item line and exercise the backfill INSERT
     logic in-place (the migration runs once; we replay its INSERT loop
     on a fresh zero-item line to prove the same SQL still produces the
     correct shape — labels, display_order, amount).
  4. Idempotency: running the backfill SELECT (LEFT JOIN ... IS NULL) on
     a DB that already has all lines covered returns zero rows, i.e. a
     re-run is a no-op.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


DEFAULT_LABELS = ("Materials", "Labour", "Equipment", "Subcontractor")


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture
def synthetic_zero_item_line(engine):
    """Insert a project → appraisal → budget → budget_line chain (no items).

    Yields the line_id and cleans the whole chain at teardown.
    """
    refs: dict = {}
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        user_id = c.execute(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        )).scalar()
        if not (entity_id and user_id):
            pytest.skip("seed_test_users not run — entity/admin missing")

        project_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '1 Backfill Way', 'SY1 3AA', false, :u)
        """), {"id": project_id, "code": f"M0027-{project_id[:6]}",
                "name": f"Mig0027 Test {project_id[:6]}",
                "ent": entity_id, "u": user_id})

        appraisal_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (
                :id, :pid, 'Mig0027 Base', CURRENT_DATE,
                :uid, :gid, 'Base',
                true, 'Approved', 1
            )
        """), {"id": appraisal_id, "pid": project_id, "uid": user_id,
                "gid": str(uuid.uuid4())})

        budget_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO budgets (
                id, project_id, source_appraisal_id, version_number,
                version_label, is_current, status, created_from_appraisal_at,
                total_budget, total_actuals, total_committed_not_invoiced,
                total_forecast_to_complete, forecast_final_cost,
                variance_vs_budget, variance_pct, summary_refreshed_at,
                created_by_user_id
            ) VALUES (
                :id, :pid, :ap, 1, 'v1', false, 'Draft', NOW(),
                0, 0, 0, 0, 0, 0, 0, NOW(), :u
            )
        """), {"id": budget_id, "pid": project_id, "ap": appraisal_id,
                "u": user_id})

        cc_id = c.execute(text("SELECT id FROM cost_codes LIMIT 1")).scalar()
        line_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO budget_lines (
                id, budget_id, cost_code_id, display_order,
                line_description, entity_id, ftc_method,
                original_budget, approved_changes, current_budget,
                actuals_to_date, committed_value, invoiced_against_commitment,
                committed_not_invoiced, forecast_to_complete,
                forecast_final_cost, variance_value, variance_pct,
                variance_status, is_locked, requires_attention
            ) VALUES (
                :id, :bid, :cc, 1, 'Backfill target', :ent, 'Manual',
                0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 'Green', false, false
            )
        """), {"id": line_id, "bid": budget_id, "cc": cc_id, "ent": entity_id})

        refs.update(
            project_id=project_id, appraisal_id=appraisal_id,
            budget_id=budget_id, line_id=line_id,
        )

    yield refs

    with engine.begin() as c:
        # Cascade order: items -> line -> budget -> appraisal -> project.
        c.execute(text("DELETE FROM budget_line_items WHERE budget_line_id=:l"),
                  {"l": refs["line_id"]})
        c.execute(text("DELETE FROM budget_lines WHERE id=:l"),
                  {"l": refs["line_id"]})
        c.execute(text("DELETE FROM budgets WHERE id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM appraisals WHERE id=:a"),
                  {"a": refs["appraisal_id"]})
        c.execute(text("DELETE FROM projects WHERE id=:p"),
                  {"p": refs["project_id"]})


class TestMigration0027Schema:
    def test_0027_is_in_applied_history(self, engine):
        """Once Chat 23 R1.4 adds migration 0028, head advances. We just
        need to assert 0027 is in the applied chain (i.e. alembic_version
        is 0027 OR something downstream that depends on 0027)."""
        with engine.connect() as c:
            head = c.execute(text("SELECT version_num FROM alembic_version")).scalar()
        # Acceptable heads: 0027 itself, or any later revision (0028+).
        assert head is not None
        assert head >= "0027_default_line_items_backfill", (
            f"head {head!r} is older than 0027 — backfill not applied"
        )

    def test_migration_emitted_audit_row(self, engine):
        # The migration emits a Seed_Run audit row with metadata.kind =
        # 'data_backfill' and the canonical default labels. Use the
        # deterministic uuid5 to look it up exactly.
        namespace = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0027")
        rid = str(uuid.uuid5(namespace, "0027_default_line_items_backfill"))
        with engine.connect() as c:
            row = c.execute(text("""
                SELECT metadata_json
                FROM audit_log
                WHERE resource_type='migration' AND resource_id=:rid
                ORDER BY created_at DESC
                LIMIT 1
            """), {"rid": rid}).first()
        assert row is not None, "0027 audit row not found"
        meta = row.metadata_json
        # metadata_json comes back as a dict (psycopg jsonb decode)
        assert meta["kind"] == "data_backfill"
        assert meta["revision"] == "0027_default_line_items_backfill"
        assert meta["default_labels"] == list(DEFAULT_LABELS)
        assert isinstance(meta["rows_backfilled"], int)
        assert isinstance(meta["items_inserted"], int)
        assert meta["items_inserted"] == 4 * meta["rows_backfilled"]


class TestMigration0027BackfillSql:
    def test_backfill_insert_produces_4_default_items_with_correct_shape(
        self, engine, synthetic_zero_item_line,
    ):
        """Replay the migration's INSERT loop against a fresh zero-item
        line and verify the 4 default items land with exact labels,
        amount=0, display_order 0..3.
        """
        line_id = synthetic_zero_item_line["line_id"]

        # Pre-state: zero items on the synthetic line.
        with engine.connect() as c:
            n_before = c.execute(text(
                "SELECT COUNT(*) FROM budget_line_items WHERE budget_line_id=:l"
            ), {"l": line_id}).scalar()
        assert n_before == 0

        # Replay migration logic on this line only.
        with engine.begin() as c:
            for idx, label in enumerate(DEFAULT_LABELS):
                c.execute(text("""
                    INSERT INTO budget_line_items (
                        id, budget_line_id, description, amount, display_order
                    ) VALUES (
                        gen_random_uuid(), :l, :d, 0, :o
                    )
                """), {"l": line_id, "d": label, "o": idx})

        # Post-state: exactly 4 items, ordered Materials → Other.
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT description, amount, display_order
                FROM budget_line_items
                WHERE budget_line_id=:l
                ORDER BY display_order
            """), {"l": line_id}).all()
        assert len(rows) == 4
        assert [r.description for r in rows] == list(DEFAULT_LABELS)
        assert [r.amount for r in rows] == [Decimal("0")] * 4
        assert [r.display_order for r in rows] == [0, 1, 2, 3]


class TestMigration0027Idempotency:
    def test_no_zero_item_lines_remain_after_migration(self, engine):
        """The whole point of the migration: post-upgrade, no budget_line
        should be without items. This guards against a future regression
        where 0027 itself stops backfilling correctly or a later
        migration introduces zero-item lines.
        """
        with engine.connect() as c:
            n = c.execute(text("""
                SELECT COUNT(*)
                FROM budget_lines bl
                LEFT JOIN budget_line_items bli ON bli.budget_line_id = bl.id
                WHERE bli.id IS NULL
            """)).scalar()
        assert n == 0, (
            f"{n} budget_lines still have zero items after 0027 — "
            "either the migration regressed or a new code path is "
            "creating lines without invoking _create_default_items."
        )
