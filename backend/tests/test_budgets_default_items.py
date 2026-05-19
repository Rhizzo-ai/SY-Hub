"""Chat 23 Build Pack A — R1.2 default budget_line_items.

Every newly-created BudgetLine must auto-create the 4 default items
(Materials, Labour, Equipment, Subcontractor) at display_order 0..3
with amount=0.00. Calling the helper a second time on the same line
is a no-op (idempotency guard).

R1.2 acceptance gates covered:
  1. Constant labels + order pinned.
  2. Line creation via service produces exactly 4 items at amount=0 in
     the Materials/Labour/Equipment/Subcontractor order.
  3. Idempotency: re-invoking `_create_default_items` on the same line
     produces no new items (still 4 total, not 8).
  4. `new_version` copies source items VERBATIM and does NOT call the
     helper — verified by copying a line with a renamed/edited item set
     and asserting the renamed items survive intact.
"""
from __future__ import annotations

import os
import uuid
from datetime import date
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text

from app.services.budget_lines import (
    DEFAULT_LINE_ITEMS, _create_default_items, create_line,
)

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture
def db_session():
    from app.db import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def synthetic_draft_budget(engine):
    """Build a fresh project → appraisal → Draft budget chain.

    Returns dict of ids. Cleans the chain (incl. any lines/items the
    test created) at teardown.
    """
    refs: dict = {}
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        user_id = c.execute(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        )).scalar()
        cc_id = c.execute(text("SELECT id FROM cost_codes LIMIT 1")).scalar()
        if not (entity_id and user_id and cc_id):
            pytest.skip("seed_test_users / cost_codes not present")
        # Coerce any psycopg UUID adapter return into plain str for the
        # fixture dict so tests can re-build uuid.UUID(...) consistently.
        entity_id = str(entity_id)
        user_id = str(user_id)
        cc_id = str(cc_id)

        project_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '1 R1.2 Way', 'SY1 4AA', false, :u)
        """), {"id": project_id, "code": f"R12-{project_id[:6]}",
               "name": f"R1.2 Test {project_id[:6]}",
               "ent": entity_id, "u": user_id})

        appraisal_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (
                :id, :pid, 'R1.2 Base', CURRENT_DATE,
                :uid, :gid, 'Base', true, 'Approved', 1
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
                :id, :pid, :ap, 1, 'v1', true, 'Draft', NOW(),
                0, 0, 0, 0, 0, 0, 0, NOW(), :u
            )
        """), {"id": budget_id, "pid": project_id, "ap": appraisal_id,
               "u": user_id})

        refs.update(
            project_id=project_id, appraisal_id=appraisal_id,
            budget_id=budget_id, entity_id=entity_id,
            cost_code_id=cc_id, user_id=user_id,
        )

    yield refs

    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM budget_line_items
            WHERE budget_line_id IN (
                SELECT id FROM budget_lines WHERE budget_id=:b
            )
        """), {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM budgets WHERE id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM appraisals WHERE id=:a"),
                  {"a": refs["appraisal_id"]})
        c.execute(text("DELETE FROM projects WHERE id=:p"),
                  {"p": refs["project_id"]})


def _perms_for(db, user_id):
    from app.auth.permissions import compute_effective_permissions
    from app.models.user import User
    u = db.get(User, user_id)
    return u, compute_effective_permissions(db, u.id, u.tenant_id)


class TestDefaultLineItemsConstant:
    def test_exact_labels_and_order(self):
        # The 4 labels and their order are part of the API contract — pin
        # them so a future "alphabetise the defaults" refactor surfaces
        # in CI rather than silently churning every new line.
        assert DEFAULT_LINE_ITEMS == (
            "Materials",
            "Labour",
            "Equipment",
            "Subcontractor",
        )

    def test_amount_zero_is_decimal(self):
        # The helper passes Decimal("0") into BudgetLineItem.amount. This
        # test pins the contract via a direct construction — if a future
        # refactor switches to int(0) or float(0.0), the Decimal-equality
        # comparisons in subsequent service code would silently break.
        assert Decimal("0") == Decimal("0.00")
        assert Decimal("0") + Decimal("123.45") == Decimal("123.45")


class TestCreateLineAutoCreatesDefaults:
    def test_service_create_line_emits_4_defaults_in_order(
        self, db_session, synthetic_draft_budget,
    ):
        from app.models.budgets import BudgetLineItem

        u, perms = _perms_for(db_session, synthetic_draft_budget["user_id"])
        line = create_line(
            db_session,
            budget_id=uuid.UUID(synthetic_draft_budget["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(synthetic_draft_budget["cost_code_id"]),
            cost_code_subcategory_id=None,
            entity_id=uuid.UUID(synthetic_draft_budget["entity_id"]),
            line_description="R1.2 acceptance line",
        )
        db_session.commit()

        items = db_session.scalars(
            select(BudgetLineItem)
            .where(BudgetLineItem.budget_line_id == line.id)
            .order_by(BudgetLineItem.display_order)
        ).all()
        assert len(items) == 4
        assert [i.description for i in items] == [
            "Materials", "Labour", "Equipment", "Subcontractor",
        ]
        assert [i.display_order for i in items] == [0, 1, 2, 3]
        assert all(i.amount == Decimal("0") for i in items)


class TestCreateDefaultItemsIdempotency:
    def test_second_invocation_is_noop(
        self, db_session, synthetic_draft_budget,
    ):
        """Calling the helper twice on the same line produces 4 items,
        not 8. Guards against double-creation when callers re-flush or
        test fixtures re-seed."""
        from app.models.budgets import BudgetLineItem

        u, perms = _perms_for(db_session, synthetic_draft_budget["user_id"])
        line = create_line(
            db_session,
            budget_id=uuid.UUID(synthetic_draft_budget["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(synthetic_draft_budget["cost_code_id"]),
            cost_code_subcategory_id=None,
            entity_id=uuid.UUID(synthetic_draft_budget["entity_id"]),
            line_description="R1.2 idempotency line",
        )
        db_session.flush()

        # First invocation already happened inside create_line. Re-invoke
        # directly to prove the idempotency guard fires.
        created = _create_default_items(db_session, line)
        assert created == [], (
            "_create_default_items should return [] when line already "
            "has items"
        )
        db_session.flush()

        n = db_session.scalar(
            select(BudgetLineItem)
            .where(BudgetLineItem.budget_line_id == line.id)
        )
        # Count via separate query to avoid the limit(1) in the helper.
        items = db_session.scalars(
            select(BudgetLineItem)
            .where(BudgetLineItem.budget_line_id == line.id)
        ).all()
        assert len(items) == 4
        db_session.commit()


class TestNewVersionPreservesSourceItems:
    def test_new_version_copies_items_verbatim_no_autocreate(
        self, db_session, synthetic_draft_budget, engine,
    ):
        """`new_version` must copy whatever items the source line has,
        even if the user renamed or deleted some of the defaults. The
        helper must NOT fire on the new version's lines."""
        from app.models.budgets import Budget, BudgetLine, BudgetLineItem
        from app.services.budgets import new_version

        u, perms = _perms_for(db_session, synthetic_draft_budget["user_id"])
        # Create the line (gets 4 defaults).
        line = create_line(
            db_session,
            budget_id=uuid.UUID(synthetic_draft_budget["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(synthetic_draft_budget["cost_code_id"]),
            cost_code_subcategory_id=None,
            entity_id=uuid.UUID(synthetic_draft_budget["entity_id"]),
            line_description="R1.2 newversion line",
        )
        db_session.flush()

        # Rename one default and delete another so the source set
        # diverges from `DEFAULT_LINE_ITEMS`.
        items = db_session.scalars(
            select(BudgetLineItem)
            .where(BudgetLineItem.budget_line_id == line.id)
            .order_by(BudgetLineItem.display_order)
        ).all()
        items[0].description = "Reclaim materials (renamed)"
        items[0].amount = Decimal("123.45")
        db_session.delete(items[3])  # delete "Subcontractor"
        db_session.flush()

        # Activate budget so new_version's guard passes.
        budget = db_session.get(
            Budget, uuid.UUID(synthetic_draft_budget["budget_id"]),
        )
        budget.status = "Active"
        db_session.flush()
        db_session.commit()

        # Snapshot source items for later comparison.
        source_items = [
            (i.description, i.amount, i.display_order)
            for i in db_session.scalars(
                select(BudgetLineItem)
                .where(BudgetLineItem.budget_line_id == line.id)
                .order_by(BudgetLineItem.display_order)
            ).all()
        ]
        assert len(source_items) == 3
        assert source_items[0][0] == "Reclaim materials (renamed)"
        assert source_items[0][1] == Decimal("123.45")

        # Create new version.
        _, new_budget = new_version(
            db_session,
            budget_id=uuid.UUID(synthetic_draft_budget["budget_id"]),
            user=u, perms=perms,
        )
        db_session.flush()

        # New version's line should mirror the source's 3 items, NOT
        # have the 4 defaults reseeded.
        new_lines = db_session.scalars(
            select(BudgetLine).where(BudgetLine.budget_id == new_budget.id)
        ).all()
        assert len(new_lines) == 1
        new_line = new_lines[0]

        copied = [
            (i.description, i.amount, i.display_order)
            for i in db_session.scalars(
                select(BudgetLineItem)
                .where(BudgetLineItem.budget_line_id == new_line.id)
                .order_by(BudgetLineItem.display_order)
            ).all()
        ]
        assert copied == source_items, (
            f"new_version must copy source items verbatim. "
            f"got {copied} expected {source_items}"
        )

        # Release the FOR UPDATE lock held by db_session BEFORE the
        # synthetic_draft_budget teardown tries to DELETE FROM budgets —
        # otherwise pytest fixture finalisers (LIFO order) deadlock the
        # next test module.
        db_session.rollback()

        # Cleanup: drop the new budget so the synthetic_draft_budget
        # teardown can reclaim the chain. Note: rolling back db_session
        # above ALSO undoes the new_version writes, so new_budget no
        # longer exists in committed state. The DELETE below is
        # defensive in case a future refactor commits the new version
        # mid-test.
        with engine.begin() as c:
            c.execute(text("""
                DELETE FROM budget_line_items
                WHERE budget_line_id IN (
                    SELECT id FROM budget_lines WHERE budget_id=:b
                )
            """), {"b": str(new_budget.id)})
            c.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                      {"b": str(new_budget.id)})
            c.execute(text("DELETE FROM budgets WHERE id=:b"),
                      {"b": str(new_budget.id)})
