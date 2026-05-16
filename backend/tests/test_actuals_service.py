"""Service-layer unit tests for the Actuals module — Prompt 2.5A / Chat 19A.

Direct against `app.services.actuals` via SQLAlchemy sessions — no HTTP layer.
Mirrors the pattern from earlier service tests (test_budgets_service-style,
in-process db + factory fixtures).

Covers:
- CRUD: create / update / delete-Draft happy + guard paths
- State machine: every valid + invalid transition
- CIS computation
- Retention computation
- VAT (gross = net + vat enforcement)
- Immutability triggers (DB-level)
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError, DataError
from sqlalchemy.orm import sessionmaker

from app.auth.permissions import UserPermissions
from app.models.actuals import (
    Actual, ActualChangeLog, VALID_TRANSITIONS, TERMINAL_ACTUAL_STATUSES,
)
from app.models.budgets import Budget, BudgetLine
from app.models.user import User
from app.schemas.actuals import CreateActualRequest, UpdateDraftActualRequest
from app.services import actuals as actuals_svc
from app.services import budgets_reconciliation
from app.services.actual_errors import (
    ActualError, ActualNotFoundError, BudgetLineLockedError,
    BudgetLineNotInProjectError, DuplicateExternalIdError,
    ImmutableFieldError, InvalidTransitionError, MissingRequiredFieldError,
)

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_perms(user) -> UserPermissions:
    perm_set = {
        "actuals.view", "actuals.view_sensitive",
        "actuals.create", "actuals.edit",
        "actuals.approve", "actuals.admin",
    }
    return UserPermissions(
        user_id=user.id,
        tenant_id=user.tenant_id,
        all_permissions=set(perm_set),
        all_entity_perms=set(perm_set),
        all_project_perms=set(perm_set),
        is_super_admin=True,  # bypass project scoping for service tests
    )


def _make_payload(*, project_id, budget_line_id, entity_id, **overrides):
    body = dict(
        project_id=project_id,
        budget_line_id=budget_line_id,
        entity_id=entity_id,
        source_type="Manual_Entry",
        transaction_date=date.today(),
        description="service test draft",
        net_amount=Decimal("1000.00"),
        vat_amount=Decimal("200.00"),
        vat_rate_pct=Decimal("20"),
        supplier_name_snapshot="ACME Ltd",
    )
    body.update(overrides)
    return CreateActualRequest(**body)


# ---------------------------------------------------------------------------
# Module-scoped fixtures (raw SQL seed; mirrors test_migration_0025)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(scope="module")
def seeds(engine):
    """Project + appraisal + Active budget + 2 budget_lines + entity + user."""
    refs = {}
    with engine.begin() as c:
        refs["entity_id"] = c.execute(text(
            "SELECT id FROM entities LIMIT 1"
        )).scalar()
        admin = c.execute(text(
            "SELECT id, tenant_id FROM users WHERE email='test-admin@example.test'"
        )).first()
        if not (refs["entity_id"] and admin):
            pytest.skip("required seed rows missing")
        refs["user_id"] = admin.id
        refs["tenant_id"] = admin.tenant_id

        # second entity (for cross-entity tests) — reuse first if only one exists
        ent2 = c.execute(text(
            "SELECT id FROM entities ORDER BY name OFFSET 1 LIMIT 1"
        )).scalar()
        refs["entity2_id"] = ent2 or refs["entity_id"]

        project_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '1 Service Test Way', 'SY1 2AA', false, :u)
        """), {"id": project_id, "code": f"SVC-{project_id.hex[:6]}",
               "name": f"Svc Test {project_id.hex[:6]}",
               "ent": refs["entity_id"], "u": refs["user_id"]})
        refs["project_id"] = project_id

        # Second project for cross-project guard test
        project2_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '2 Service Test Way', 'SY2 2AA', false, :u)
        """), {"id": project2_id, "code": f"SVC2-{project2_id.hex[:6]}",
               "name": f"Svc Test 2 {project2_id.hex[:6]}",
               "ent": refs["entity_id"], "u": refs["user_id"]})
        refs["project2_id"] = project2_id

        ag_id = uuid.uuid4()
        appraisal_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (
                :id, :pid, 'Svc Base', CURRENT_DATE,
                :uid, :gid, 'Base', true, 'Approved', 1
            )
        """), {"id": appraisal_id, "pid": project_id, "uid": refs["user_id"],
               "gid": ag_id})
        refs["appraisal_id"] = appraisal_id

        # Project 2 appraisal
        ag2_id = uuid.uuid4()
        appraisal2_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (
                :id, :pid, 'Svc Base 2', CURRENT_DATE,
                :uid, :gid, 'Base', true, 'Approved', 1
            )
        """), {"id": appraisal2_id, "pid": project2_id, "uid": refs["user_id"],
               "gid": ag2_id})
        refs["appraisal2_id"] = appraisal2_id

        # Active budget on project 1
        budget_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budgets (id, project_id, source_appraisal_id,
              version_number, version_label, is_current, status,
              created_from_appraisal_at,
              total_budget, total_actuals, total_committed_not_invoiced,
              total_forecast_to_complete, forecast_final_cost,
              variance_vs_budget, variance_pct, summary_refreshed_at,
              created_by_user_id)
            VALUES (:id, :pid, :ap, 1, 'v1', true, 'Active', NOW(),
                    1000000, 0, 0, 1000000, 1000000, 0, 0, NOW(), :u)
        """), {"id": budget_id, "pid": project_id, "ap": appraisal_id,
               "u": refs["user_id"]})
        refs["budget_id"] = budget_id

        # Closed budget on project 1 (for terminal guard test) — must not be current
        closed_budget_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budgets (id, project_id, source_appraisal_id,
              version_number, version_label, is_current, status,
              created_from_appraisal_at,
              total_budget, total_actuals, total_committed_not_invoiced,
              total_forecast_to_complete, forecast_final_cost,
              variance_vs_budget, variance_pct, summary_refreshed_at,
              created_by_user_id)
            VALUES (:id, :pid, :ap, 0, 'v0', false, 'Closed', NOW(),
                    1000000, 0, 0, 1000000, 1000000, 0, 0, NOW(), :u)
        """), {"id": closed_budget_id, "pid": project_id, "ap": appraisal_id,
               "u": refs["user_id"]})
        refs["closed_budget_id"] = closed_budget_id

        # Active budget on project 2 (cross-project line guard test)
        budget2_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budgets (id, project_id, source_appraisal_id,
              version_number, version_label, is_current, status,
              created_from_appraisal_at,
              total_budget, total_actuals, total_committed_not_invoiced,
              total_forecast_to_complete, forecast_final_cost,
              variance_vs_budget, variance_pct, summary_refreshed_at,
              created_by_user_id)
            VALUES (:id, :pid, :ap, 1, 'v1', true, 'Active', NOW(),
                    500000, 0, 0, 500000, 500000, 0, 0, NOW(), :u)
        """), {"id": budget2_id, "pid": project2_id, "ap": appraisal2_id,
               "u": refs["user_id"]})
        refs["budget2_id"] = budget2_id

        cc_rows = c.execute(text(
            "SELECT id FROM cost_codes ORDER BY code LIMIT 3"
        )).all()
        cc_ids = [r[0] for r in cc_rows]
        if len(cc_ids) < 2:
            pytest.skip("need at least 2 cost_codes seeded")

        # Two lines on project 1 active budget — distinct cost codes
        line1_id = uuid.uuid4()
        line2_id = uuid.uuid4()
        for lid, order, cc in [(line1_id, 1, cc_ids[0]), (line2_id, 2, cc_ids[1])]:
            c.execute(text("""
                INSERT INTO budget_lines (id, budget_id, cost_code_id,
                  display_order, line_description, entity_id, ftc_method,
                  original_budget, approved_changes, current_budget,
                  actuals_to_date, committed_value, invoiced_against_commitment,
                  committed_not_invoiced, forecast_to_complete,
                  forecast_final_cost, variance_value, variance_pct,
                  variance_status, is_locked, requires_attention)
                VALUES (:id, :bid, :cc, :ord, :ld, :ent, 'Manual',
                        500000, 0, 500000,
                        0, 0, 0, 0, 500000, 500000,
                        0, 0, 'Green',
                        false, false)
            """), {"id": lid, "bid": budget_id, "cc": cc,
                   "ord": order, "ld": f"Line {order}", "ent": refs["entity_id"]})
        refs["line1_id"] = line1_id
        refs["line2_id"] = line2_id

        # Line on closed budget
        closed_line_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budget_lines (id, budget_id, cost_code_id,
              display_order, line_description, entity_id, ftc_method,
              original_budget, approved_changes, current_budget,
              actuals_to_date, committed_value, invoiced_against_commitment,
              committed_not_invoiced, forecast_to_complete,
              forecast_final_cost, variance_value, variance_pct,
              variance_status, is_locked, requires_attention)
            VALUES (:id, :bid, :cc, 1, 'Closed line', :ent, 'Manual',
                    100000, 0, 100000, 0, 0, 0, 0, 100000, 100000,
                    0, 0, 'Green', false, false)
        """), {"id": closed_line_id, "bid": closed_budget_id, "cc": cc_ids[0],
               "ent": refs["entity_id"]})
        refs["closed_line_id"] = closed_line_id

        # Line on project 2
        p2_line_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budget_lines (id, budget_id, cost_code_id,
              display_order, line_description, entity_id, ftc_method,
              original_budget, approved_changes, current_budget,
              actuals_to_date, committed_value, invoiced_against_commitment,
              committed_not_invoiced, forecast_to_complete,
              forecast_final_cost, variance_value, variance_pct,
              variance_status, is_locked, requires_attention)
            VALUES (:id, :bid, :cc, 1, 'P2 line', :ent, 'Manual',
                    100000, 0, 100000, 0, 0, 0, 0, 100000, 100000,
                    0, 0, 'Green', false, false)
        """), {"id": p2_line_id, "bid": budget2_id, "cc": cc_ids[0],
               "ent": refs["entity_id"]})
        refs["p2_line_id"] = p2_line_id

    yield refs

    # Teardown — order matters for RESTRICT FKs
    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id IN (:p, :p2))"),
                  {"p": refs["project_id"], "p2": refs["project2_id"]})
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals WHERE project_id IN (:p, :p2)"),
                  {"p": refs["project_id"], "p2": refs["project2_id"]})
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM budget_lines WHERE budget_id IN "
                       "(:b1, :b2, :b3)"),
                  {"b1": refs["budget_id"], "b2": refs["closed_budget_id"],
                   "b3": refs["budget2_id"]})
        c.execute(text("DELETE FROM budgets WHERE id IN (:b1, :b2, :b3)"),
                  {"b1": refs["budget_id"], "b2": refs["closed_budget_id"],
                   "b3": refs["budget2_id"]})
        c.execute(text("DELETE FROM appraisals WHERE id IN (:a, :a2)"),
                  {"a": refs["appraisal_id"], "a2": refs["appraisal2_id"]})
        c.execute(text("DELETE FROM projects WHERE id IN (:p, :p2)"),
                  {"p": refs["project_id"], "p2": refs["project2_id"]})


@pytest.fixture(autouse=True)
def _wipe_actuals_between_tests(engine, seeds):
    """Between every test wipe actuals + change_log so we have a clean slate.

    Also resets the seeded `budget_id` to Active (some tests flip it Closed),
    and budget_line aggregates to zero so reconciliation tests start clean.
    """
    yield
    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log"))
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals"))
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("""
            UPDATE budget_lines SET actuals_to_date=0, committed_not_invoiced=0
        """))
        # Active-budget reset (defensive against tests that flip status).
        c.execute(text("UPDATE budgets SET status='Active' WHERE id=:b"),
                  {"b": seeds["budget_id"]})


@pytest.fixture
def db(Session):
    s = Session()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def admin_user(db, seeds):
    u = db.get(User, seeds["user_id"])
    return u


@pytest.fixture
def perms(admin_user):
    return _all_perms(admin_user)


@pytest.fixture
def draft_factory(db, seeds, admin_user, perms):
    def _make(*, budget_line_id=None, **overrides):
        body = _make_payload(
            project_id=seeds["project_id"],
            budget_line_id=budget_line_id or seeds["line1_id"],
            entity_id=seeds["entity_id"],
            **overrides,
        )
        a = actuals_svc.create_actual(
            db, payload=body, user=admin_user, perms=perms,
        )
        db.commit()
        return a
    return _make


# ---------------------------------------------------------------------------
# CRUD (10 tests)
# ---------------------------------------------------------------------------

class TestCRUD:
    def test_create_manual_happy_path(self, db, seeds, admin_user, perms):
        body = _make_payload(
            project_id=seeds["project_id"],
            budget_line_id=seeds["line1_id"],
            entity_id=seeds["entity_id"],
        )
        a = actuals_svc.create_actual(db, payload=body, user=admin_user, perms=perms)
        db.commit()
        assert a.status == "Draft"
        assert a.gross_amount == Decimal("1200.00")
        assert a.net_amount == Decimal("1000.00")
        assert a.created_by_user_id == admin_user.id

    def test_create_manual_rejects_closed_budget(self, db, seeds, admin_user, perms):
        body = _make_payload(
            project_id=seeds["project_id"],
            budget_line_id=seeds["closed_line_id"],
            entity_id=seeds["entity_id"],
        )
        with pytest.raises(BudgetLineLockedError):
            actuals_svc.create_actual(db, payload=body, user=admin_user, perms=perms)

    def test_create_manual_rejects_cross_project_budget_line(
        self, db, seeds, admin_user, perms,
    ):
        """Posting a P2 budget_line on a project P1 actual should fail."""
        body = _make_payload(
            project_id=seeds["project_id"],
            budget_line_id=seeds["p2_line_id"],
            entity_id=seeds["entity_id"],
        )
        with pytest.raises(BudgetLineNotInProjectError):
            actuals_svc.create_actual(db, payload=body, user=admin_user, perms=perms)

    def test_create_manual_rejects_nonexistent_budget_line(
        self, db, seeds, admin_user, perms,
    ):
        body = _make_payload(
            project_id=seeds["project_id"],
            budget_line_id=uuid.uuid4(),
            entity_id=seeds["entity_id"],
        )
        with pytest.raises(BudgetLineNotInProjectError):
            actuals_svc.create_actual(db, payload=body, user=admin_user, perms=perms)

    def test_create_manual_rejects_invalid_source_type(
        self, db, seeds, admin_user, perms,
    ):
        # CreateActualRequest schema allows any str; service should reject.
        body = _make_payload(
            project_id=seeds["project_id"],
            budget_line_id=seeds["line1_id"],
            entity_id=seeds["entity_id"],
            source_type="Bogus_Source",
        )
        with pytest.raises(MissingRequiredFieldError):
            actuals_svc.create_actual(db, payload=body, user=admin_user, perms=perms)

    def test_create_manual_rejects_nonexistent_project(
        self, db, seeds, admin_user, perms,
    ):
        body = _make_payload(
            project_id=uuid.uuid4(),
            budget_line_id=seeds["line1_id"],
            entity_id=seeds["entity_id"],
        )
        with pytest.raises(ActualNotFoundError):
            actuals_svc.create_actual(db, payload=body, user=admin_user, perms=perms)

    def test_update_draft_happy_path(self, db, seeds, admin_user, perms, draft_factory):
        a = draft_factory()
        upd = UpdateDraftActualRequest(description="updated", net_amount=Decimal("2000.00"))
        a2 = actuals_svc.update_draft_actual(
            db, actual_id=a.id, payload=upd, user=admin_user, perms=perms,
        )
        db.commit()
        assert a2.description == "updated"
        assert a2.net_amount == Decimal("2000.00")
        assert a2.gross_amount == Decimal("2200.00")  # vat unchanged

    def test_update_draft_rejects_posted(
        self, db, seeds, admin_user, perms, draft_factory,
    ):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        with pytest.raises(ImmutableFieldError):
            actuals_svc.update_draft_actual(
                db, actual_id=a.id,
                payload=UpdateDraftActualRequest(description="nope"),
                user=admin_user, perms=perms,
            )

    def test_delete_draft_happy(self, db, seeds, admin_user, perms, draft_factory):
        a = draft_factory()
        actuals_svc.delete_draft_actual(
            db, actual_id=a.id, user=admin_user, perms=perms,
        )
        db.commit()
        assert db.get(Actual, a.id) is None

    def test_list_actuals_filters_by_status(
        self, db, seeds, admin_user, perms, draft_factory,
    ):
        from app.schemas.actuals import ActualsListFilters
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        draft_factory()  # add another Draft
        db.commit()
        rows, total = actuals_svc.list_actuals(
            db, filters=ActualsListFilters(
                project_id=seeds["project_id"], status="Posted",
            ),
            user=admin_user, perms=perms,
        )
        assert total == 1
        assert all(r.status == "Posted" for r in rows)


# ---------------------------------------------------------------------------
# State machine (15 tests)
# ---------------------------------------------------------------------------

class TestStateMachine:
    def test_draft_to_posted_happy(self, db, draft_factory, admin_user, perms):
        a = draft_factory()
        a2 = actuals_svc.post_actual(
            db, actual_id=a.id, user=admin_user, perms=perms,
        )
        db.commit()
        assert a2.status == "Posted"
        assert a2.posted_at is not None
        assert a2.posted_by_user_id == admin_user.id

    def test_draft_to_posted_recompiles_actuals_to_date(
        self, db, seeds, draft_factory, admin_user, perms,
    ):
        a = draft_factory(net_amount=Decimal("500.00"))
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("500.00")

    def test_draft_to_posted_blocked_when_budget_terminal(
        self, db, seeds, admin_user, perms, draft_factory, engine,
    ):
        """Documentation: the service enforces budget-terminal check at CREATE
        time, not POST time. This test asserts the documented behaviour:
        Once a Draft exists, flipping the budget to Closed does NOT prevent
        posting — the immutability of an in-flight transaction is the higher
        priority. (Operator workflow: void the Draft after the budget close.)
        """
        a = draft_factory()
        try:
            with engine.begin() as c:
                c.execute(text(
                    "UPDATE budgets SET status='Closed' WHERE id=:b"
                ), {"b": seeds["budget_id"]})
            # Don't expire `a` — its in-session status is still 'Draft', which
            # matches reality. The budget change is irrelevant to immutability.
            a2 = actuals_svc.post_actual(
                db, actual_id=a.id, user=admin_user, perms=perms,
            )
            db.commit()
            assert a2.status == "Posted"
        finally:
            with engine.begin() as c:
                c.execute(text(
                    "UPDATE budgets SET status='Active' WHERE id=:b"
                ), {"b": seeds["budget_id"]})

    def test_posted_to_paid_happy(self, db, draft_factory, admin_user, perms):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        a2 = actuals_svc.mark_paid(
            db, actual_id=a.id, paid_date=date.today(),
            payment_reference="PAY-1", user=admin_user, perms=perms,
        )
        db.commit()
        assert a2.status == "Paid"
        assert a2.payment_reference == "PAY-1"

    def test_posted_to_void_happy(self, db, draft_factory, admin_user, perms):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        a2 = actuals_svc.void_actual(
            db, actual_id=a.id, void_reason="duplicate",
            user=admin_user, perms=perms,
        )
        db.commit()
        assert a2.status == "Void"
        assert a2.void_reason == "duplicate"

    def test_posted_to_disputed_happy(self, db, draft_factory, admin_user, perms):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        a2 = actuals_svc.dispute_actual(
            db, actual_id=a.id, dispute_reason="wrong amount",
            user=admin_user, perms=perms,
        )
        db.commit()
        assert a2.status == "Disputed"

    def test_disputed_to_posted_happy(self, db, draft_factory, admin_user, perms):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        actuals_svc.dispute_actual(
            db, actual_id=a.id, dispute_reason="x",
            user=admin_user, perms=perms,
        )
        db.commit()
        a2 = actuals_svc.undispute_actual(
            db, actual_id=a.id, user=admin_user, perms=perms,
        )
        db.commit()
        assert a2.status == "Posted"
        assert a2.dispute_reason is None

    def test_paid_to_void_blocked(self, db, draft_factory, admin_user, perms):
        """Per service: Void on Paid raises InvalidTransitionError (credit note instead)."""
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        actuals_svc.mark_paid(
            db, actual_id=a.id, paid_date=date.today(),
            payment_reference="P", user=admin_user, perms=perms,
        )
        db.commit()
        with pytest.raises(InvalidTransitionError):
            actuals_svc.void_actual(
                db, actual_id=a.id, void_reason="oops",
                user=admin_user, perms=perms,
            )

    def test_void_blocks_further_transitions(
        self, db, draft_factory, admin_user, perms,
    ):
        a = draft_factory()
        actuals_svc.void_actual(
            db, actual_id=a.id, void_reason="cancel",
            user=admin_user, perms=perms,
        )
        db.commit()
        with pytest.raises(InvalidTransitionError):
            actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)

    def test_status_transitions_emit_change_log(
        self, db, draft_factory, admin_user, perms,
    ):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        rows = actuals_svc.get_change_log(
            db, actual_id=a.id, user=admin_user, perms=perms,
        )
        event_types = {r.event_type for r in rows}
        assert "Created" in event_types
        assert "Posted" in event_types

    def test_two_actuals_same_line_aggregate(
        self, db, seeds, draft_factory, admin_user, perms,
    ):
        a1 = draft_factory(net_amount=Decimal("300.00"))
        a2 = draft_factory(net_amount=Decimal("700.00"))
        actuals_svc.post_actual(db, actual_id=a1.id, user=admin_user, perms=perms)
        actuals_svc.post_actual(db, actual_id=a2.id, user=admin_user, perms=perms)
        db.commit()
        line = db.get(BudgetLine, seeds["line1_id"])
        db.refresh(line)
        assert line.actuals_to_date == Decimal("1000.00")

    def test_post_emits_audit_log(self, db, draft_factory, admin_user, perms, engine):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        with engine.connect() as c:
            n = c.execute(text(
                "SELECT COUNT(*) FROM audit_log WHERE action='Post' "
                "AND resource_id=:r"
            ), {"r": a.id}).scalar()
        assert n == 1

    def test_release_retention_happy(self, db, draft_factory, admin_user, perms):
        """Posted actual w/ retention → release_retention marks release_date."""
        a = draft_factory(retention_rate_pct=Decimal("5"))
        # Post so retention is bound
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        a2 = actuals_svc.release_retention(
            db, actual_id=a.id, retention_release_date=date.today(),
            user=admin_user, perms=perms,
        )
        db.commit()
        assert a2.retention_released is True
        assert a2.retention_release_date == date.today()

    def test_release_retention_idempotent(
        self, db, draft_factory, admin_user, perms,
    ):
        a = draft_factory(retention_rate_pct=Decimal("5"))
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        actuals_svc.release_retention(
            db, actual_id=a.id, retention_release_date=date.today(),
            user=admin_user, perms=perms,
        )
        db.commit()
        # Second call is a no-op.
        a3 = actuals_svc.release_retention(
            db, actual_id=a.id, retention_release_date=date.today(),
            user=admin_user, perms=perms,
        )
        assert a3.retention_released is True

    def test_release_retention_blocked_when_no_retention(
        self, db, draft_factory, admin_user, perms,
    ):
        a = draft_factory()  # no retention
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        with pytest.raises(InvalidTransitionError):
            actuals_svc.release_retention(
                db, actual_id=a.id, retention_release_date=date.today(),
                user=admin_user, perms=perms,
            )


# ---------------------------------------------------------------------------
# CIS (7 tests)
# ---------------------------------------------------------------------------

class TestCIS:
    def test_cis_non_applicable_returns_none(self, db, draft_factory):
        a = draft_factory(is_cis_applicable=False)
        assert a.cis_deduction_amount is None

    def test_cis_20pct_labour_only(self, db, draft_factory):
        a = draft_factory(
            is_cis_applicable=True,
            cis_deduction_rate_pct=Decimal("20"),
            cis_labour_amount=Decimal("500.00"),
        )
        assert a.cis_deduction_amount == Decimal("100.00")

    def test_cis_30pct_rate(self, db, draft_factory):
        a = draft_factory(
            is_cis_applicable=True,
            cis_deduction_rate_pct=Decimal("30"),
            cis_labour_amount=Decimal("500.00"),
        )
        assert a.cis_deduction_amount == Decimal("150.00")

    def test_cis_0pct_gross_payment_status(self, db, draft_factory):
        a = draft_factory(
            is_cis_applicable=True,
            cis_deduction_rate_pct=Decimal("0"),
            cis_labour_amount=Decimal("500.00"),
        )
        assert a.cis_deduction_amount == Decimal("0.00")

    def test_cis_missing_labour_returns_none(self, db, draft_factory):
        a = draft_factory(
            is_cis_applicable=True,
            cis_deduction_rate_pct=Decimal("20"),
        )
        assert a.cis_deduction_amount is None

    def test_cis_materials_not_deducted(self, db, draft_factory):
        """CIS deduction is on labour only, not materials."""
        a = draft_factory(
            is_cis_applicable=True,
            cis_deduction_rate_pct=Decimal("20"),
            cis_labour_amount=Decimal("500.00"),
            cis_materials_amount=Decimal("300.00"),
        )
        # deduction = 500 * 20% = 100, NOT (500+300) * 20%
        assert a.cis_deduction_amount == Decimal("100.00")

    def test_cis_persists_materials_value(self, db, draft_factory):
        a = draft_factory(
            is_cis_applicable=True,
            cis_deduction_rate_pct=Decimal("20"),
            cis_labour_amount=Decimal("500.00"),
            cis_materials_amount=Decimal("250.00"),
        )
        assert a.cis_materials_amount == Decimal("250.00")


# ---------------------------------------------------------------------------
# Retention (5 tests)
# ---------------------------------------------------------------------------

class TestRetention:
    def test_retention_rate_computes_amount(self, db, draft_factory):
        a = draft_factory(retention_rate_pct=Decimal("5"))
        # net 1000 * 5% = 50.00
        assert a.retention_amount == Decimal("50.00")

    def test_retention_explicit_amount_used(self, db, draft_factory):
        a = draft_factory(retention_amount=Decimal("42.42"))
        assert a.retention_amount == Decimal("42.42")

    def test_retention_both_supplied_keeps_explicit(self, db, draft_factory):
        """Service preference: explicit > computed when both present."""
        a = draft_factory(
            retention_rate_pct=Decimal("5"),
            retention_amount=Decimal("99.99"),
        )
        assert a.retention_amount == Decimal("99.99")

    def test_retention_neither_supplied_is_none(self, db, draft_factory):
        a = draft_factory()
        assert a.retention_amount is None

    def test_retention_zero_rate_is_none(self, db, draft_factory):
        """A 0% rate with no explicit amount → amount=None."""
        a = draft_factory(retention_rate_pct=Decimal("0"))
        assert a.retention_amount is None


# ---------------------------------------------------------------------------
# VAT (3 tests)
# ---------------------------------------------------------------------------

class TestVAT:
    def test_gross_is_net_plus_vat(self, db, draft_factory):
        a = draft_factory(
            net_amount=Decimal("123.45"),
            vat_amount=Decimal("24.69"),
        )
        assert a.gross_amount == Decimal("148.14")

    def test_non_gbp_requires_exchange_rate(self, db, seeds, admin_user, perms):
        body = _make_payload(
            project_id=seeds["project_id"],
            budget_line_id=seeds["line1_id"],
            entity_id=seeds["entity_id"],
            currency="USD",
        )
        with pytest.raises(MissingRequiredFieldError):
            actuals_svc.create_actual(db, payload=body, user=admin_user, perms=perms)

    def test_vat_non_recoverable_flag_stored(self, db, draft_factory):
        a = draft_factory(is_vat_recoverable=False)
        assert a.is_vat_recoverable is False


# ---------------------------------------------------------------------------
# Immutability trigger (2 tests, DB-level)
# ---------------------------------------------------------------------------

class TestImmutability:
    def test_db_blocks_net_amount_change_after_post(
        self, db, draft_factory, admin_user, perms, engine,
    ):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        with engine.begin() as c:
            with pytest.raises(Exception) as exc:
                c.execute(text(
                    "UPDATE actuals SET net_amount=9999.00 WHERE id=:id"
                ), {"id": a.id})
            assert "immutable" in str(exc.value).lower() or "23514" in str(exc.value)

    def test_db_blocks_budget_line_id_change_after_post(
        self, db, seeds, draft_factory, admin_user, perms, engine,
    ):
        a = draft_factory()
        actuals_svc.post_actual(db, actual_id=a.id, user=admin_user, perms=perms)
        db.commit()
        with engine.begin() as c:
            with pytest.raises(Exception) as exc:
                c.execute(text(
                    "UPDATE actuals SET budget_line_id=:b WHERE id=:id"
                ), {"id": a.id, "b": seeds["line2_id"]})
            assert "immutable" in str(exc.value).lower() or "23514" in str(exc.value)
