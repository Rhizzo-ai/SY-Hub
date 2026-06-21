"""C2 — Seal the Illusory Budget Freeze (B-variant) tests.

Covers the C2 / Chat-63 decision: `clear_unbudgeted` (the director
"acknowledge unbudgeted spend" path, B102) must be BLOCKED on terminally
sealed budgets (Superseded / Closed → 409) but still ALLOWED on a soft-frozen
Locked budget (audited as `on_frozen_budget: true`), and unchanged on
Draft / Active.

This is the B-variant asymmetry: `clear_unbudgeted` blocks on
`TERMINAL_BUDGET_STATUSES` only — NOT the full `LINE_FROZEN_BUDGET_STATUSES`
(Locked stays allowed). See `services/budget_lines.py::clear_unbudgeted`.

Fixture style is deliberately reused from `test_unbudgeted_orders.py` (the
canonical B102 factory). We import its budget/line factory helpers
(`_build_chain` / `_tear_chain` / `_perms_for`) and HTTP login helpers rather
than invent a new fixture style.

Seeding pattern for every status: `create_unbudgeted_line` itself refuses a
frozen budget at mint time (that path is correct and untouched), so we always
mint the line on an Active budget, then flip the parent budget's status via raw
SQL to the status under test, then exercise `clear_unbudgeted`. This isolates
the seal guard cleanly without going through the activate→lock router dance.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy import select as _select

from app.services.budget_errors import BudgetSealedError
from app.services.budget_lines import clear_unbudgeted, create_unbudgeted_line

# Reuse the canonical B102 factory + HTTP helpers — do NOT invent a new
# fixture style (Build Pack §2).
from tests.test_unbudgeted_orders import (
    _build_chain,
    _tear_chain,
    _perms_for,
    _login,
    _BASE_URL,
    _ADMIN_EMAIL,
    _PM_EMAIL,
)

DATABASE_URL = os.environ["DATABASE_URL"]


# ----------------------------------------------------------------------
# Fixtures (replicate the engine / session / MFA-reset pattern locally so
# this file is self-contained — the imported autouse fixtures from the
# sibling module do not apply across files).
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


@pytest.fixture(scope="module", autouse=True)
def _reset_mfa_for_http_tests(engine):
    """Reset MFA on the test users so the HTTP-level logins go through the
    enrol path and cache the TOTP secret for the module (mirrors the
    canonical headless-flow reset in test_unbudgeted_orders.py)."""
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


@pytest.fixture
def chain(engine):
    """Active budget chain — every C2 test mints on Active then flips
    status to the case under test."""
    refs = _build_chain(engine, budget_status="Active")
    yield refs
    _tear_chain(engine, refs)


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def _set_budget_status(engine, db, budget_id: str, status: str) -> None:
    """Flip the parent budget's status via a separate committed
    connection, then expire the ORM session so the next read inside
    `clear_unbudgeted` reloads the fresh (flipped) status under its lock."""
    with engine.begin() as c:
        c.execute(
            text("UPDATE budgets SET status=:s WHERE id=:b"),
            {"s": status, "b": budget_id},
        )
    db.expire_all()


def _seed_unbudgeted(db, refs, *, force: bool = False):
    """Mint one unbudgeted line on the (Active) chain budget and commit.

    `force=True` keeps the legacy B102 forced-Red + requires_attention=True
    marker so the blocked-state tests can assert the line is genuinely
    UNCHANGED (requires_attention still True) after a refused clear.
    """
    u, perms = _perms_for(db, refs["user_id"])
    line = create_unbudgeted_line(
        db,
        budget_id=uuid.UUID(refs["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(refs["cost_code_id"]),
        entity_id=uuid.UUID(refs["entity_id"]),
        reason="C2 seal-guard probe",
        source="purchase_order",
        force_flag=force,
    )
    db.commit()
    return u, perms, line


def _clear_audit_rows(db, line_id):
    from app.models.audit import AuditLog
    rows = db.scalars(
        _select(AuditLog)
        .where(AuditLog.resource_type == "budget_lines")
        .where(AuditLog.resource_id == line_id)
    ).all()
    return [
        a for a in rows
        if (a.metadata_json or {}).get("event") == "clear_unbudgeted"
    ]


# ======================================================================
# Service layer — status matrix (the core of B-variant)
# ======================================================================
class TestSealGuardServiceMatrix:
    def test_clear_allowed_on_draft(self, db_session, chain, engine):
        """Draft is not frozen → clear succeeds; audit flags it as a
        non-frozen sign-off."""
        from app.models.budgets import BudgetLine

        u, perms, line = _seed_unbudgeted(db_session, chain)
        _set_budget_status(engine, db_session, chain["budget_id"], "Draft")

        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()

        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is not None
        assert fresh.unbudgeted_cleared_by == u.id

        rows = _clear_audit_rows(db_session, line.id)
        assert len(rows) == 1
        meta = rows[0].metadata_json
        assert meta["budget_status_at_clear"] == "Draft"
        assert meta["on_frozen_budget"] is False

    def test_clear_allowed_on_active(self, db_session, chain):
        """Active (no flip) → clear succeeds, on_frozen_budget False."""
        from app.models.budgets import BudgetLine

        u, perms, line = _seed_unbudgeted(db_session, chain)

        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()

        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is not None

        rows = _clear_audit_rows(db_session, line.id)
        assert len(rows) == 1
        meta = rows[0].metadata_json
        assert meta["budget_status_at_clear"] == "Active"
        assert meta["on_frozen_budget"] is False

    def test_clear_allowed_on_locked(self, db_session, chain, engine):
        """B-variant allowance: Locked is a SOFT freeze — clear SUCCEEDS,
        and the audit row explicitly flags `on_frozen_budget: True`."""
        from app.models.budgets import BudgetLine

        u, perms, line = _seed_unbudgeted(db_session, chain)
        _set_budget_status(engine, db_session, chain["budget_id"], "Locked")

        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()

        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is not None
        assert fresh.requires_attention is False

        rows = _clear_audit_rows(db_session, line.id)
        assert len(rows) == 1
        meta = rows[0].metadata_json
        assert meta["budget_status_at_clear"] == "Locked"
        assert meta["on_frozen_budget"] is True

    def test_clear_blocked_on_superseded(self, db_session, chain, engine):
        """Superseded is terminal/sealed → BudgetSealedError; line UNCHANGED
        and NO audit row written."""
        from app.models.budgets import BudgetLine

        u, perms, line = _seed_unbudgeted(db_session, chain, force=True)
        _set_budget_status(engine, db_session, chain["budget_id"], "Superseded")

        with pytest.raises(BudgetSealedError):
            clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        # The guard raises after taking FOR UPDATE on the budget — release it
        # so the chain teardown's DELETE does not deadlock.
        db_session.rollback()

        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is None
        assert fresh.unbudgeted_cleared_by is None
        assert fresh.requires_attention is True
        assert _clear_audit_rows(db_session, line.id) == []

    def test_clear_blocked_on_closed(self, db_session, chain, engine):
        """Closed is terminal/sealed → BudgetSealedError; line UNCHANGED
        and NO audit row written."""
        from app.models.budgets import BudgetLine

        u, perms, line = _seed_unbudgeted(db_session, chain, force=True)
        _set_budget_status(engine, db_session, chain["budget_id"], "Closed")

        with pytest.raises(BudgetSealedError):
            clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.rollback()

        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is None
        assert fresh.unbudgeted_cleared_by is None
        assert fresh.requires_attention is True
        assert _clear_audit_rows(db_session, line.id) == []


# ======================================================================
# Idempotency / race must still hold under the new guard
# ======================================================================
class TestSealGuardIdempotency:
    def test_already_cleared_short_circuit_unaffected(
        self, db_session, chain, engine,
    ):
        """A line already cleared (on Active) whose budget then goes Locked
        → a second clear still short-circuits (returns unchanged, writes no
        new audit row). Proves the seal guard runs AFTER the idempotency
        short-circuit and never breaks it."""
        from app.models.budgets import BudgetLine

        u, perms, line = _seed_unbudgeted(db_session, chain)

        # First clear on Active.
        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()
        first = db_session.get(BudgetLine, line.id)
        first_at = first.unbudgeted_cleared_at
        assert first_at is not None
        assert len(_clear_audit_rows(db_session, line.id)) == 1

        # Budget then goes Locked; second clear must short-circuit.
        _set_budget_status(engine, db_session, chain["budget_id"], "Locked")
        clear_unbudgeted(db_session, line_id=line.id, user=u, perms=perms)
        db_session.commit()

        second = db_session.get(BudgetLine, line.id)
        assert second.unbudgeted_cleared_at == first_at
        assert len(_clear_audit_rows(db_session, line.id)) == 1


# ======================================================================
# HTTP layer (status codes are the contract)
# ======================================================================
class TestSealGuardHTTP:
    def test_http_clear_closed_returns_409(self, db_session, chain, engine):
        from app.models.budgets import BudgetLine

        _u, _p, line = _seed_unbudgeted(db_session, chain)
        _set_budget_status(engine, db_session, chain["budget_id"], "Closed")

        s = _login(_ADMIN_EMAIL)
        r = s.post(
            f"{_BASE_URL}/api/v1/budget-lines/{line.id}/clear-unbudgeted"
        )
        assert r.status_code == 409, (r.status_code, r.text)
        detail = r.json().get("detail", "").lower()
        assert "new budget" in detail or "version" in detail

        # Row genuinely unchanged in the DB.
        db_session.expire_all()
        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is None

    def test_http_clear_superseded_returns_409(self, db_session, chain, engine):
        from app.models.budgets import BudgetLine

        _u, _p, line = _seed_unbudgeted(db_session, chain)
        _set_budget_status(engine, db_session, chain["budget_id"], "Superseded")

        s = _login(_ADMIN_EMAIL)
        r = s.post(
            f"{_BASE_URL}/api/v1/budget-lines/{line.id}/clear-unbudgeted"
        )
        assert r.status_code == 409, (r.status_code, r.text)

        db_session.expire_all()
        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is None

    def test_http_clear_locked_returns_200(self, db_session, chain, engine):
        from app.models.budgets import BudgetLine

        _u, _p, line = _seed_unbudgeted(db_session, chain)
        _set_budget_status(engine, db_session, chain["budget_id"], "Locked")

        s = _login(_ADMIN_EMAIL)
        r = s.post(
            f"{_BASE_URL}/api/v1/budget-lines/{line.id}/clear-unbudgeted"
        )
        assert r.status_code == 200, (r.status_code, r.text)
        body = r.json()
        assert body.get("unbudgeted_cleared_at") is not None

        db_session.expire_all()
        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is not None

    def test_http_not_unbudgeted_line_still_422(self, db_session, chain):
        """A normal (non-unbudgeted) line still returns 422 — proves the new
        409 branch did NOT cannibalise the existing 422 (BudgetSealedError is
        caught BEFORE BudgetStateError, but a plain BudgetStateError still
        falls through to 422)."""
        from app.models.budgets import BudgetLine

        normal = BudgetLine(
            id=uuid.uuid4(),
            budget_id=uuid.UUID(chain["budget_id"]),
            cost_code_id=uuid.UUID(chain["cost_code_id"]),
            entity_id=uuid.UUID(chain["entity_id"]),
            line_description="Normal budgeted line — not unbudgeted",
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

    def test_http_clear_missing_line_still_404(self, chain):
        """Unknown line id still 404 (not-found path regression guard)."""
        s = _login(_ADMIN_EMAIL)
        r = s.post(
            f"{_BASE_URL}/api/v1/budget-lines/{uuid.uuid4()}/clear-unbudgeted"
        )
        assert r.status_code == 404, (r.status_code, r.text)


# ======================================================================
# Permission regression — the perm gate fires BEFORE the seal guard
# ======================================================================
class TestSealGuardPermission:
    def test_http_clear_requires_permission(self, db_session, chain, engine):
        """A caller without `budgets.clear_unbudgeted` (project_manager) gets
        403 on EVERY status — the permission dependency fires before the seal
        guard ever runs."""
        from app.models.budgets import BudgetLine

        _u, _p, line = _seed_unbudgeted(db_session, chain)

        s = _login(_PM_EMAIL)
        for status in ("Active", "Locked", "Closed", "Superseded"):
            _set_budget_status(engine, db_session, chain["budget_id"], status)
            r = s.post(
                f"{_BASE_URL}/api/v1/budget-lines/{line.id}/clear-unbudgeted"
            )
            assert r.status_code == 403, (status, r.status_code, r.text)

        # And the line is untouched throughout.
        db_session.expire_all()
        fresh = db_session.get(BudgetLine, line.id)
        assert fresh.unbudgeted_cleared_at is None
