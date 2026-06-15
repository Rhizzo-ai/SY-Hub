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
    clear_unbudgeted,
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


# =====================================================================
# Gate 4 — director acknowledgement ("clear") of an unbudgeted line.
#
# T13     — clear-action lifts attention + stamps who/when, writes
#           exactly one audit row tagged event=clear_unbudgeted.
# T13b    — THE Gate-2-deviation catch: clearing actually recomputes
#           variance_status off the forced Red. No manual variance set.
# T14     — second clear is idempotent (200, same cleared_at, no
#           extra audit row).
# T15     — clear against a normal (non-unbudgeted) line returns 422.
# T16     — HTTP-level: a user lacking budgets.clear_unbudgeted (the
#           finance test user) gets 403.
# T17     — actuals / committed on the line are untouched by the
#           clear-action.
# T18     — _serialise_line exposes the seven new fields.
# T19     — _grid_line_node exposes the same seven fields.
# =====================================================================
import os as _os

import requests as _requests
from sqlalchemy import select as _select

_BASE_URL = (
    _os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
_PWD = _os.environ["TEST_USER_PASSWORD"]
_DIRECTOR_EMAIL = "test-director@example.test"
_FINANCE_EMAIL = "test-finance@example.test"
_ADMIN_EMAIL = "test-admin@example.test"
_PM_EMAIL = "test-pm@example.test"


@pytest.fixture(scope="module", autouse=True)
def _reset_mfa_for_http_tests(engine):
    """Reset MFA on the test users used by the HTTP-level B102 tests
    so `login_with_auto_enroll` will go through the enrol path and
    cache the TOTP secret in conftest._MFA_SECRETS for the rest of
    the module. Without this, the helper raises pytest.skip on the
    second login attempt because the per-process secret cache is
    empty.

    Pattern from /app/memory/test_credentials.md (the canonical
    headless-flow reset).
    """
    with engine.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled = false,
                             mfa_method = NULL,
                             mfa_secret_encrypted = NULL,
                             mfa_backup_codes_encrypted = NULL,
                             mfa_enrolled_at = NULL,
                             failed_login_attempts = 0,
                             locked_until = NULL,
                             lockout_level = 0
             WHERE email LIKE 'test-%@example.test'
        """))
    yield
    # No re-enrolment on teardown — other tests in the full-suite run
    # may rely on MFA-disabled state; if so, the next test session
    # picks up a fresh seed. The reset is idempotent.


def _login(email):
    """Login under the cookie-only contract — minimal helper local to
    this file so the test isn't coupled to the heavyweight
    `tests.conftest.login_with_auto_enroll` (which assumes MFA reset
    has happened in the same module-scope db_engine fixture). Reuses
    the cached-MFA secrets module from conftest."""
    from tests.conftest import login_with_auto_enroll
    return login_with_auto_enroll(None, _BASE_URL, email, _PWD)


class TestClearUnbudgetedLifecycle:
    """Service-level coverage of the clear-action (T13, T13b, T14)."""

    def test_clear_unbudgeted_lifts_attention_logs_who_when(
        self, db_session, active_chain,
    ):
        """T13 — clear sets cleared_by/at, requires_attention False;
        is_unbudgeted stays True (permanent provenance marker);
        exactly one audit row tagged event=clear_unbudgeted."""
        from app.models.budgets import BudgetLine
        from app.models.audit import AuditLog

        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Unexpected ground conditions — beyond appraisal",
            source="purchase_order",
        )
        db_session.commit()

        # ── Act ──
        clear_unbudgeted(
            db_session, line_id=line.id, user=u, perms=perms,
        )
        db_session.commit()

        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.requires_attention is False
        assert fresh.unbudgeted_cleared_by == u.id
        assert fresh.unbudgeted_cleared_at is not None
        # Permanent provenance marker — must NOT reset to False.
        assert fresh.is_unbudgeted is True

        # Exactly one audit row with event=clear_unbudgeted.
        audits = db_session.scalars(
            _select(AuditLog)
            .where(AuditLog.resource_type == "budget_lines")
            .where(AuditLog.resource_id == line.id)
        ).all()
        clear_rows = [
            a for a in audits
            if (a.metadata_json or {}).get("event") == "clear_unbudgeted"
        ]
        assert len(clear_rows) == 1, (
            f"expected 1 clear_unbudgeted audit row, got {len(clear_rows)}"
        )

    def test_clear_unbudgeted_recomputes_variance_off_red(
        self, db_session, active_chain,
    ):
        """T13b — variance_status must be recomputed off the forced Red.

        Pre-conditions: create_unbudgeted_line wrote variance_status="Red"
        by direct assignment, not by maths. A £0-budget line with zero
        actuals/committed/ftc has variance_pct=0 → _classify_variance
        returns "Green". So after clear+recompute, the line must NOT be
        Red. (Without the recompute, the forced Red would outlive the
        acknowledgement — see Gate 2 deviation log.)
        """
        from app.models.budgets import BudgetLine

        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Site security upgrades — not in original brief",
            source="package",
        )
        db_session.commit()

        # Pre-clear assertion: the forced Red is still on the row.
        pre = db_session.get(BudgetLine, line.id)
        assert pre.variance_status == "Red"

        # ── Act: clear and let the service recompute ──
        clear_unbudgeted(
            db_session, line_id=line.id, user=u, perms=perms,
        )
        db_session.commit()

        post = db_session.get(BudgetLine, line.id)
        # The exact post-clear colour comes from _classify_variance(0)
        # which, per its first branch (variance_pct <= 0), returns
        # "Green". Pin that explicitly so a future tightening of the
        # banding (e.g. Amber as the new default for £0) trips this
        # test and forces a Build-Pack deviation log entry.
        assert post.variance_status == "Green", (
            f"expected Green after clear+recompute, got "
            f"{post.variance_status!r} — the forced-Red marker has "
            "survived acknowledgement, see Gate 2 deviation."
        )

    def test_clear_unbudgeted_idempotent(self, db_session, active_chain):
        """T14 — second clear returns the line unchanged, writes no
        extra audit row, does NOT re-stamp cleared_at/cleared_by."""
        from app.models.budgets import BudgetLine
        from app.models.audit import AuditLog

        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Idempotency probe",
            source="purchase_order",
        )
        db_session.commit()

        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()
        after_first = db_session.get(BudgetLine, line.id)
        first_cleared_at = after_first.unbudgeted_cleared_at
        first_cleared_by = after_first.unbudgeted_cleared_by

        # ── Act: second clear ──
        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()

        after_second = db_session.get(BudgetLine, line.id)
        # Idempotent: timestamps must be byte-for-byte identical.
        assert after_second.unbudgeted_cleared_at == first_cleared_at
        assert after_second.unbudgeted_cleared_by == first_cleared_by

        # Audit row count for clear_unbudgeted must be exactly 1.
        audits = db_session.scalars(
            _select(AuditLog)
            .where(AuditLog.resource_type == "budget_lines")
            .where(AuditLog.resource_id == line.id)
        ).all()
        clear_rows = [
            a for a in audits
            if (a.metadata_json or {}).get("event") == "clear_unbudgeted"
        ]
        assert len(clear_rows) == 1, (
            f"idempotent path wrote {len(clear_rows)} audit rows; "
            "expected exactly 1."
        )


class TestClearUnbudgetedHTTP:
    """HTTP-level coverage of the clear-action (T15, T16)."""

    def test_clear_unbudgeted_on_non_unbudgeted_line_422(
        self, db_session, active_chain,
    ):
        """T15 — clearing a normal (is_unbudgeted=False) line returns
        422. Uses HTTP so the service ValueError-to-422 mapping is
        exercised."""
        # Build a normal (non-unbudgeted) line directly so we don't
        # have to seed a full appraisal. Just insert a row.
        from app.models.budgets import BudgetLine

        normal = BudgetLine(
            id=uuid.uuid4(),
            budget_id=uuid.UUID(active_chain["budget_id"]),
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            line_description="Normal budgeted line — not B102",
            original_budget=Decimal("1000"),
            current_budget=Decimal("1000"),
            actuals_to_date=Decimal("0"),
            committed_not_invoiced=Decimal("0"),
            forecast_to_complete=Decimal("0"),
            forecast_final_cost=Decimal("0"),
            variance_value=Decimal("0"),
            variance_pct=Decimal("0"),
            variance_status="Green",
            requires_attention=False,
            is_contingency=False,
            is_locked=False,
            is_unbudgeted=False,
            display_order=999,
        )
        db_session.add(normal)
        db_session.commit()

        s = _login(_ADMIN_EMAIL)
        r = s.post(
            f"{_BASE_URL}/api/v1/budget-lines/{normal.id}/clear-unbudgeted"
        )
        assert r.status_code == 422, (r.status_code, r.text)
        assert "not an unbudgeted line" in r.json().get("detail", "")

    def test_clear_unbudgeted_requires_permission_403(
        self, db_session, active_chain,
    ):
        """T16 — a project_manager (no `budgets.clear_unbudgeted`) → 403.

        PM is preferred over finance for this test because PM has no
        MFA (per /app/memory/test_credentials.md), so the login path
        avoids the TOTP enrolment dance entirely — the auth-failure
        signal is cleaner.
        """
        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Test of 403 perm path",
            source="purchase_order",
        )
        db_session.commit()

        s = _login(_PM_EMAIL)
        r = s.post(
            f"{_BASE_URL}/api/v1/budget-lines/{line.id}/clear-unbudgeted"
        )
        assert r.status_code == 403, (r.status_code, r.text)


class TestClearUnbudgetedDoesNotTouchSpend:
    def test_clear_unbudgeted_spend_remains_on_line(
        self, db_session, active_chain,
    ):
        """T17 — actuals + committed_not_invoiced (the source-of-truth
        spend columns) are byte-identical before vs after the clear.

        forecast_to_complete and forecast_final_cost are NOT pinned here:
        they are derived quantities that `recompute_summary` re-derives
        from (current_budget, actuals, committed) on every recompute —
        so they SHOULD update when the clear-action triggers a
        recompute. That re-derivation is correct behaviour, not a leak.
        """
        from app.models.budgets import BudgetLine

        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Spend-invariance probe",
            source="purchase_order",
        )
        # Stamp some realistic spend numbers post-create.
        line.actuals_to_date = Decimal("345.67")
        line.committed_not_invoiced = Decimal("89.10")
        db_session.commit()

        before = (line.actuals_to_date, line.committed_not_invoiced)
        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()

        fresh = db_session.get(BudgetLine, line.id)
        after = (fresh.actuals_to_date, fresh.committed_not_invoiced)
        assert after == before, (
            f"source-of-truth spend figures must be untouched; "
            f"before={before} after={after}"
        )


class TestSerialiserExposesUnbudgetedFields:
    """T18 + T19 — both the detail serialiser and the grid node
    surface the seven new fields."""

    EXPECTED_KEYS = {
        "is_unbudgeted",
        "unbudgeted_reason",
        "unbudgeted_source",
        "unbudgeted_created_by",
        "unbudgeted_cleared_by",
        "unbudgeted_cleared_at",
        "unbudgeted_awaiting_ack",
    }

    def test_serialise_line_exposes_unbudgeted_fields(
        self, db_session, active_chain,
    ):
        """T18 — _serialise_line (detail) carries all 7 keys.

        Verified by GETting the budget detail (which lists all lines
        through _serialise_line) and walking to our line; this
        exercises the real serialiser without coupling to an internal
        Python symbol.
        """
        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Serialiser exposure probe",
            source="purchase_order",
        )
        db_session.commit()

        s = _login(_ADMIN_EMAIL)
        r = s.get(
            f"{_BASE_URL}/api/v1/budgets/{active_chain['budget_id']}"
        )
        assert r.status_code == 200, (r.status_code, r.text)
        body = r.json()
        # Budget-detail response typically has a "lines" list.
        lines = body.get("lines") or []
        ours = next((l for l in lines if str(l.get("id")) == str(line.id)), None)
        assert ours is not None, (
            f"line {line.id} missing from budget detail; "
            f"got {len(lines)} lines"
        )
        missing = self.EXPECTED_KEYS - set(ours.keys())
        assert not missing, (
            f"_serialise_line missing keys: {missing} "
            f"(line keys: {sorted(ours.keys())})"
        )
        # Sanity-pin a few values.
        assert ours["is_unbudgeted"] is True
        assert ours["unbudgeted_source"] == "purchase_order"
        assert ours["unbudgeted_awaiting_ack"] is True
        assert ours["unbudgeted_cleared_at"] is None

    def test_grid_node_exposes_unbudgeted_fields(
        self, db_session, active_chain,
    ):
        """T19 — _grid_line_node carries all 7 keys."""
        u, perms = _perms_for(db_session, active_chain["user_id"])
        line = create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(active_chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(active_chain["cost_code_id"]),
            entity_id=uuid.UUID(active_chain["entity_id"]),
            reason="Grid node exposure probe",
            source="package",
        )
        db_session.commit()

        s = _login(_ADMIN_EMAIL)
        r = s.get(
            f"{_BASE_URL}/api/v1/budgets/{active_chain['budget_id']}/grid"
        )
        assert r.status_code == 200, (r.status_code, r.text)
        body = r.json()
        # Walk the grid tree until we find our line.
        # Grid structure: {groups: [{lines: [...]}, ...]} or similar.
        # Be defensive — flatten any list of dicts.
        def _find_line(obj, line_id):
            if isinstance(obj, dict):
                if str(obj.get("id")) == str(line_id) and "is_unbudgeted" in obj:
                    return obj
                for v in obj.values():
                    found = _find_line(v, line_id)
                    if found:
                        return found
            elif isinstance(obj, list):
                for v in obj:
                    found = _find_line(v, line_id)
                    if found:
                        return found
            return None

        node = _find_line(body, line.id)
        assert node is not None, (
            "grid response did not contain a node for the test line "
            f"{line.id}; top-level keys: {sorted(body.keys()) if isinstance(body, dict) else type(body)}"
        )
        missing = self.EXPECTED_KEYS - set(node.keys())
        assert not missing, (
            f"_grid_line_node missing keys: {missing} "
            f"(node keys: {sorted(node.keys())})"
        )
        assert node["is_unbudgeted"] is True
        assert node["unbudgeted_source"] == "package"
        assert node["unbudgeted_awaiting_ack"] is True
