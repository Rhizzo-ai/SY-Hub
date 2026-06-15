"""B102 — Unbudgeted-Order Handling, Gate 2 service-level tests.

Covers the §R5 acceptance gates T1–T6 for:
  - app.services.budget_lines.create_unbudgeted_line
  - app.services.budget_lines.scan_requires_attention (D-E1 isolation)

Subsequent gates (HTTP + PO + package + award + clear) extend this same
file with T7–T?; only T1–T6 must be green to pass Gate 2.

Fixture pattern mirrors test_budgets_default_items.py: a synthetic
project → appraisal → Active budget chain is built with raw SQL and
torn down on exit. The helper is invoked through the public service
entrypoint with super-admin perms so we exercise the real lock +
default-items + recompute path end-to-end.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from app.services.budget_errors import BudgetStateError
from app.services.budget_lines import (
    create_unbudgeted_line,
    scan_requires_attention,
)

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------
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


def _build_chain(engine, *, budget_status: str = "Active") -> dict:
    """Build a synthetic project → appraisal → budget chain.

    `budget_status` is parameterised so T6 can seed a Locked budget
    directly without going through the activate→lock router dance.
    """
    refs: dict = {}
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        user_id = c.execute(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        )).scalar()
        # Pick a cost code that has at least one subcategory so we could
        # exercise the subcategory branch if a future test needs it; but
        # the helper is fine with subcat=None too.
        cc_id = c.execute(text(
            "SELECT id FROM cost_codes WHERE status='Active' LIMIT 1"
        )).scalar()
        if not (entity_id and user_id and cc_id):
            pytest.skip("seed_test_users / cost_codes not present")

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
                    '1 B102 Way', 'SY1 4AA', false, :u)
        """), {"id": project_id, "code": f"B102-{project_id[:6]}",
               "name": f"B102 Test {project_id[:6]}",
               "ent": entity_id, "u": user_id})

        appraisal_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (
                :id, :pid, 'B102 Base', CURRENT_DATE,
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
                :id, :pid, :ap, 1, 'v1', true, :status, NOW(),
                0, 0, 0, 0, 0, 0, 0, NOW(), :u
            )
        """), {"id": budget_id, "pid": project_id, "ap": appraisal_id,
               "status": budget_status, "u": user_id})

        refs.update(
            project_id=project_id, appraisal_id=appraisal_id,
            budget_id=budget_id, entity_id=entity_id,
            cost_code_id=cc_id, user_id=user_id,
        )
    return refs


def _tear_chain(engine, refs: dict) -> None:
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


@pytest.fixture
def active_chain(engine):
    refs = _build_chain(engine, budget_status="Active")
    yield refs
    _tear_chain(engine, refs)


@pytest.fixture
def locked_chain(engine):
    refs = _build_chain(engine, budget_status="Locked")
    yield refs
    _tear_chain(engine, refs)


def _perms_for(db, user_id):
    from app.auth.permissions import compute_effective_permissions
    from app.models.user import User
    u = db.get(User, user_id)
    return u, compute_effective_permissions(db, u.id, u.tenant_id)


# ----------------------------------------------------------------------
# T1 — helper sets is_unbudgeted + Red + requires_attention + audit
#      fields on a fresh £0 line.
# ----------------------------------------------------------------------
class TestCreateUnbudgetedLineMarkers:
    def test_create_unbudgeted_line_sets_markers_red_attention(
        self, db_session, active_chain,
    ):
        from app.models.budgets import BudgetLine

        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            cost_code_subcategory_id=None,
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Site rectification — not in original budget",
            source="purchase_order",
        )
        db_session.commit()

        # Refetch from DB to prove the markers are persisted, not just
        # in-session attributes that vanish on reload.
        fresh = db_session.get(BudgetLine, line.id)
        assert fresh is not None
        assert fresh.is_unbudgeted is True
        assert fresh.variance_status == "Red"
        assert fresh.requires_attention is True
        assert fresh.unbudgeted_source == "purchase_order"
        assert str(fresh.unbudgeted_created_by) == str(u.id)
        assert fresh.unbudgeted_reason == (
            "Site rectification — not in original budget"
        )
        assert fresh.original_budget == Decimal("0")
        assert fresh.unbudgeted_cleared_at is None
        assert fresh.unbudgeted_cleared_by is None


# ----------------------------------------------------------------------
# T2 — reason is mandatory (empty + whitespace both rejected).
# ----------------------------------------------------------------------
class TestCreateUnbudgetedLineReasonRequired:
    @pytest.mark.parametrize("blank", ["", "   ", "\t\n  "])
    def test_create_unbudgeted_line_requires_reason(
        self, db_session, active_chain, blank,
    ):
        u, perms = _perms_for(db_session, active_chain["user_id"])
        with pytest.raises(BudgetStateError) as exc:
            create_unbudgeted_line(
                db_session,
                budget_id=uuid.UUID(active_chain["budget_id"]),
                user=u, perms=perms,
                cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
                entity_id=uuid.UUID(active_chain["entity_id"]),
                reason=blank,
                source="purchase_order",
            )
        assert "unbudgeted_reason is required" in str(exc.value)
        # Defensive: validation rejected the call before any lock was
        # acquired, but force a rollback so the next fixture teardown
        # never blocks on a stray idle-in-transaction.
        db_session.rollback()


# ----------------------------------------------------------------------
# T3 — entity_id=None resolves from project.primary_entity_id.
# ----------------------------------------------------------------------
class TestCreateUnbudgetedLineEntityDefaulting:
    def test_create_unbudgeted_line_defaults_entity_from_project(
        self, db_session, active_chain,
    ):
        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            cost_code_subcategory_id=None,
            entity_id=None,                  # ← deliberately omitted
            reason="Need to procure asbestos survey not in appraisal",
            source="package",
        )
        db_session.commit()
        # entity_id falls back to the project's primary_entity_id —
        # which the fixture set to the same `entity_id` we have in refs.
        assert str(line.entity_id) == active_chain["entity_id"]


# ----------------------------------------------------------------------
# T4 — variance scan SKIPS lines awaiting acknowledgement (D-E1).
# ----------------------------------------------------------------------
class TestScanSkipsAwaitingAck:
    def test_scan_skips_awaiting_ack_unbudgeted_line(
        self, db_session, active_chain,
    ):
        from app.models.budgets import BudgetLine

        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            cost_code_subcategory_id=None,
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Materials price spike — outside budget",
            source="purchase_order",
        )
        db_session.commit()

        # Force a "variance maths says non-Red" condition: a £0 line with
        # zero actuals/committed/ftc would normally classify Green on a
        # variance recompute. We rely on `is_unbudgeted=True` +
        # `cleared_at IS NULL` to make scan_requires_attention ignore it.
        # Pre-scan state: scan should be a no-op against this line.
        result = scan_requires_attention(db_session, user=u, perms=perms)
        db_session.commit()

        # Scanned but neither flagged nor cleared.
        assert result["scanned"] >= 1
        assert result["skipped_unbudgeted"] >= 1
        # The line we just created MUST be in skipped, never in flagged
        # nor cleared. Easiest way: requires_attention has not flipped.
        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.requires_attention is True
        assert fresh.variance_status == "Red"
        assert fresh.is_unbudgeted is True
        assert fresh.unbudgeted_cleared_at is None


# ----------------------------------------------------------------------
# T5 — once cleared_at is set, line rejoins normal scan behaviour.
# ----------------------------------------------------------------------
class TestScanResumesAfterAck:
    def test_scan_resumes_after_acknowledgement(
        self, db_session, active_chain,
    ):
        from app.models.budgets import BudgetLine

        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            cost_code_subcategory_id=None,
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Drone survey — discovered post-appraisal",
            source="purchase_order",
        )
        # Simulate Gate 4's clear-action: cleared_at + cleared_by land,
        # AND the variance status is re-derived by the post-clear
        # recompute (Gate 4 will commit to calling recompute_summary on
        # the parent so the forced-Red marker doesn't outlive the
        # acknowledgement). Here we shortcut the recompute by setting
        # variance_status directly — the contract this test pins is the
        # scan behaviour, not the recompute pathway.
        line.unbudgeted_cleared_at = datetime.now(timezone.utc)
        line.unbudgeted_cleared_by = u.id
        line.variance_status = "Green"   # would be set by recompute_summary in real flow
        db_session.commit()

        # Pre-condition for the assertion below: the line is still
        # marked requires_attention=True from creation; the scan must
        # now CLEAR it because (a) the D-E1 skip no longer applies
        # (cleared_at is non-NULL) and (b) variance_status is no
        # longer Red.
        result = scan_requires_attention(db_session, user=u, perms=perms)
        db_session.commit()

        assert result["scanned"] >= 1
        # Crucial: the line is no longer in `skipped_unbudgeted` —
        # acknowledgement has handed control back to the variance
        # scanner.
        # (We don't pin the exact value to 0 because other tests in
        # the same warm-DB run may have left unrelated unbudgeted
        # lines around; we only assert OUR line was not skipped, by
        # observing the side-effect on requires_attention.)
        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.requires_attention is False, (
            "post-ack scan must clear requires_attention when "
            f"variance_status is no longer Red (result={result}, "
            f"status={fresh.variance_status})"
        )
        # And cleared >= 1 because this line transitioned True → False.
        assert result["cleared"] >= 1, (
            f"expected cleared>=1 after ack+Green re-scan, got {result}"
        )


# ----------------------------------------------------------------------
# T6 — create_unbudgeted_line on a non-writable (Locked) budget is
#      rejected by create_line's LINE_FROZEN_BUDGET_STATUSES guard.
# ----------------------------------------------------------------------
class TestCreateUnbudgetedLineOnFrozenBudget:
    def test_create_unbudgeted_line_on_nonactive_budget_rejected(
        self, db_session, locked_chain,
    ):
        u, perms = _perms_for(db_session, locked_chain["user_id"])
        with pytest.raises(BudgetStateError) as exc:
            create_unbudgeted_line(
                db_session,
                budget_id=uuid.UUID(locked_chain["budget_id"]),
                user=u, perms=perms,
                cost_code_id=uuid.UUID(locked_chain["cost_code_id"]),
                entity_id=uuid.UUID(locked_chain["entity_id"]),
                reason="Anything — should never persist",
                source="purchase_order",
            )
        # The exact phrasing comes from create_line: "Cannot add lines
        # to a Locked budget"
        assert "Locked" in str(exc.value)
        # CRITICAL: create_line acquires FOR UPDATE on the budget row
        # before checking status, so the exception leaves the
        # db_session holding a row lock on the Locked budget. If we
        # don't rollback explicitly, the locked_chain teardown will
        # deadlock on its DELETE FROM budgets call because pytest
        # finalises the chain fixture before db_session.rollback runs.
        db_session.rollback()
