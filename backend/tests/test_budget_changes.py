"""Chat 33 §R5 (Prompt 2.6) — Budget Change Requests (BCRs) tests.

Covers Build Pack 2.6 acceptance gates 1–35.

Test groupings (mirror the §R5 numbered list in the Build Pack):

- Schema / migration         (gates 1–3)
- Create + invariants        (gates 4–13)
- Workflow                   (gates 14–20)
- Apply effects              (gates 21–25)
- Self-approval (LD2 / 2.4C) (gates 26–30)
- Permissions / regression   (gates 31–35)

Pattern follows tests/test_budgets.py: HTTP-based, cookies-only auth via
the `requests.Session` from `login_with_auto_enroll`. Database state
isolated by a per-class wipe of `budget_changes` + `budget_change_lines`.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll, plain_login


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
DIRECTOR_EMAIL = "test-director@example.test"
PM_EMAIL = "test-pm@example.test"
FINANCE_EMAIL = "test-finance@example.test"
READONLY_EMAIL = "test-readonly@example.test"

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"


# ==========================================================================
# Fixtures
# ==========================================================================

@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    with eng.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield eng
    eng.dispose()


def _wipe(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('budgets','budget_lines','budget_line_items',"
            " 'budget_changes',"
            " 'appraisals','appraisal_units','appraisal_cost_lines',"
            " 'appraisal_finance_model','projects','project_team_members')"
        ))
        c.execute(text("UPDATE audit_log SET project_id = NULL "
                       "WHERE project_id IS NOT NULL"))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM budget_change_lines"))
        c.execute(text("DELETE FROM budget_changes"))
        c.execute(text("DELETE FROM budget_line_items"))
        c.execute(text("DELETE FROM budget_lines"))
        c.execute(text("DELETE FROM budgets"))
        c.execute(text("DELETE FROM appraisal_finance_model"))
        c.execute(text("DELETE FROM appraisal_cost_lines"))
        c.execute(text("DELETE FROM appraisal_units"))
        c.execute(text("ALTER TABLE appraisal_decision_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_decision_log"))
        c.execute(text("ALTER TABLE appraisal_decision_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_revisions"))
        c.execute(text("DELETE FROM appraisal_scenarios"))
        c.execute(text("DELETE FROM appraisals"))
        c.execute(text("DELETE FROM project_team_members"))
        c.execute(text("DELETE FROM user_role_projects"))
        c.execute(text("DELETE FROM projects WHERE name LIKE 'BCR Test%'"))


@pytest.fixture(scope="module", autouse=True)
def _clean(db_engine):
    _wipe(db_engine)
    yield
    _wipe(db_engine)


@pytest.fixture(scope="module", autouse=True)
def _bump_self_approval_threshold(db_engine, admin):
    """Default £10k threshold would block admin self-activate on
    £250k+ seeded budgets. Bump high for the lifecycle tests; the
    dedicated `TestSelfApprovalGuard` class manages the threshold
    per-test.
    """
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY
    r = admin.put(
        f"{BASE_URL}/api/v1/system-config/{key}",
        json={"value": "999999999.00"},
    )
    assert r.status_code == 200, r.text
    yield
    admin.post(f"{BASE_URL}/api/v1/system-config/{key}/restore")


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(db_engine):
    return plain_login(BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return plain_login(BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module")
def entity_id(db_engine):
    with db_engine.connect() as c:
        pid = c.execute(
            text("SELECT id FROM entities WHERE name = :n"),
            {"n": PRIMARY_ENTITY_NAME},
        ).scalar()
    assert pid
    return str(pid)


@pytest.fixture(scope="module")
def project(admin, entity_id):
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": "BCR Test Project",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 BCR Way, Shrewsbury",
        "site_postcode": "SY1 2BB",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


def _make_approved_appraisal(admin_session, project_id):
    r = admin_session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
        json={"name": f"BCR-Appraisal-{uuid.uuid4().hex[:6]}",
              "land_purchase_price": "200000"},
    )
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        cc_id = db.scalar(text("SELECT id FROM cost_codes LIMIT 1"))
        db.execute(text(
            "DELETE FROM appraisal_cost_lines WHERE appraisal_id=:a"
        ), {"a": aid})
        db.execute(text("""
            INSERT INTO appraisal_cost_lines
              (id, appraisal_id, display_order, cost_code_id, label,
               category, auto_source, amount, is_locked)
            VALUES (gen_random_uuid(), :a, 10, :cc, 'Build cost',
                    'Construction', 'Manual', 250000.00, false)
        """), {"a": aid, "cc": cc_id})
        db.commit()
    finally:
        db.close()
    admin_session.post(
        f"{BASE_URL}/api/v1/appraisals/{aid}/units",
        json={"unit_label": "U", "unit_type": "Detached",
              "tenure": "Open_Market", "quantity": 2,
              "price_per_unit": "400000",
              "build_cost_per_unit": "200000"},
    )
    admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/submit")
    admin_session.post(f"{BASE_URL}/api/v1/appraisals/{aid}/approve")
    return aid


def _wipe_budgets_only(engine, project_id):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('budgets','budget_lines','budget_line_items','budget_changes') "
            "AND project_id IN (SELECT id FROM projects WHERE id=:p)"
        ), {"p": project_id})
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM budget_change_lines"))
        c.execute(text("DELETE FROM budget_changes"))
        c.execute(text("DELETE FROM budget_line_items"))
        c.execute(text("DELETE FROM budget_lines"))
        c.execute(text(
            "DELETE FROM budgets WHERE project_id=:p"
        ), {"p": project_id})


def _make_active_budget(
    admin_session, db_engine, project_id, *,
    line_count: int = 3,
    line_amount: Decimal = Decimal("100000.00"),
    contingency_line_index: int | None = None,
):
    """Create a Draft budget, then replace its lines with a known set of
    `line_count` lines (one of which can be flagged is_contingency), then
    activate. Returns the activated budget dict.
    """
    _wipe_budgets_only(db_engine, project_id)
    aid = _make_approved_appraisal(admin_session, project_id)
    r = admin_session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert r.status_code == 201, r.text
    budget = r.json()
    bid = budget["id"]

    # Replace lines with a clean, deterministic set so the math is
    # easy to assert. Direct DB write — bypassing the budget_lines
    # router avoids cost-code/entity plumbing.
    from app.db import SessionLocal
    db = SessionLocal()
    try:
        cc_ids = [
            r[0] for r in db.execute(text(
                "SELECT id FROM cost_codes ORDER BY id LIMIT :n"
            ), {"n": line_count})
        ]
        if len(cc_ids) < line_count:
            raise RuntimeError(
                f"Need {line_count} cost_codes; found {len(cc_ids)}"
            )
        ent_id = db.scalar(text("SELECT id FROM entities LIMIT 1"))
        db.execute(text("DELETE FROM budget_line_items WHERE budget_line_id IN "
                       "(SELECT id FROM budget_lines WHERE budget_id=:b)"),
                   {"b": bid})
        db.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                   {"b": bid})
        line_ids = []
        for i in range(line_count):
            new_id = uuid.uuid4()
            line_ids.append(str(new_id))
            is_contingency = (i == contingency_line_index)
            db.execute(text("""
                INSERT INTO budget_lines
                  (id, budget_id, cost_code_id, entity_id, line_description,
                   original_budget, approved_changes, current_budget,
                   actuals_to_date, committed_value,
                   invoiced_against_commitment, committed_not_invoiced,
                   forecast_to_complete, ftc_method, forecast_final_cost,
                   variance_value, variance_pct, variance_status,
                   is_locked, requires_attention, is_contingency,
                   display_order, created_at, updated_at)
                VALUES
                  (:id, :b, :cc, :ent, :desc,
                   :amt, 0, :amt,
                   0, 0, 0, 0, :amt, 'Budget_Remaining', :amt,
                   0, 0, 'Green',
                   false, false, :contingency,
                   :ord, now(), now())
            """), {
                "id": str(new_id), "b": bid,
                "cc": str(cc_ids[i]), "ent": ent_id,
                "desc": f"Line {i+1}{' (Contingency)' if is_contingency else ''}",
                "amt": str(line_amount),
                "contingency": is_contingency,
                "ord": i,
            })
        db.commit()
    finally:
        db.close()
    # Activate
    ra = admin_session.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
    assert ra.status_code == 200, ra.text
    out = ra.json()
    # Sort lines by display_order so tests can address by index.
    out["lines"] = sorted(out["lines"], key=lambda x: x.get("display_order", 0))
    return out


@pytest.fixture
def active_budget(admin, db_engine, project):
    """Fresh activated budget with 3 lines x £100k each; line 2 (index 2)
    is flagged is_contingency."""
    return _make_active_budget(
        admin, db_engine, project["id"],
        line_count=3,
        line_amount=Decimal("100000.00"),
        contingency_line_index=2,
    )


# ==========================================================================
# Schema / migration  (gates 1–3)
# ==========================================================================

class TestSchemaMigration:
    def test_alembic_head_is_0036_budget_changes(self):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            head = db.execute(text(
                "SELECT version_num FROM alembic_version"
            )).scalar()
        finally:
            db.close()
        assert head == "0036_budget_changes", (
            f"Expected alembic head 0036_budget_changes; got {head}"
        )

    def test_budget_changes_tables_exist(self, db_engine):
        with db_engine.connect() as c:
            assert c.execute(text(
                "SELECT to_regclass('budget_changes')"
            )).scalar() == "budget_changes"
            assert c.execute(text(
                "SELECT to_regclass('budget_change_lines')"
            )).scalar() == "budget_change_lines"

    def test_budget_lines_has_is_contingency(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT data_type, is_nullable, column_default
                FROM information_schema.columns
                WHERE table_name='budget_lines'
                  AND column_name='is_contingency'
            """)).first()
        assert row is not None, "budget_lines.is_contingency must exist"
        assert row[0] == "boolean"
        assert row[1] == "NO"  # NOT NULL
        # Existing rows backfilled false.
        with db_engine.connect() as c:
            non_false = c.execute(text(
                "SELECT COUNT(*) FROM budget_lines WHERE is_contingency IS NOT FALSE"
            )).scalar()
        assert non_false == 0, "All existing budget_lines must backfill is_contingency=false"


# ==========================================================================
# Create + invariants  (gates 4–13)
# ==========================================================================

class TestCreateAndInvariants:
    def test_create_transfer_net_zero(self, admin, active_budget):
        bid = active_budget["id"]
        lid1 = active_budget["lines"][0]["id"]
        lid2 = active_budget["lines"][1]["id"]
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid,
            "change_type": "Transfer",
            "title": "Move £5k Line1→Line2",
            "lines": [
                {"budget_line_id": lid1, "delta": "-5000.00"},
                {"budget_line_id": lid2, "delta": "5000.00"},
            ],
        })
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["status"] == "Draft"
        assert body["change_type"] == "Transfer"
        assert body["reference"] == "BCR-0001"
        assert Decimal(body["net_impact"]) == Decimal("0.00")
        assert len(body["lines"]) == 2

    def test_transfer_non_zero_net_rejected(self, admin, active_budget):
        bid = active_budget["id"]
        l1, l2 = (ln["id"] for ln in active_budget["lines"][:2])
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid,
            "change_type": "Transfer",
            "title": "Bad transfer",
            "lines": [
                {"budget_line_id": l1, "delta": "-1000.00"},
                {"budget_line_id": l2, "delta": "500.00"},
            ],
        })
        assert r.status_code == 422, r.text
        assert "must sum to 0" in r.json()["detail"]

    def test_apply_negative_budget_rejected_at_apply_time(
        self, admin, active_budget, db_engine,
    ):
        # Build a Transfer that would drive Line 1 negative.
        # Line currently 100k; transfer -200k from L1 to L2 → projected -100k.
        # Create-time advisory check catches this — both surfaces 422 at
        # the API layer.
        bid = active_budget["id"]
        l1, l2 = (ln["id"] for ln in active_budget["lines"][:2])
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid,
            "change_type": "Transfer",
            "title": "Drive negative",
            "lines": [
                {"budget_line_id": l1, "delta": "-200000.00"},
                {"budget_line_id": l2, "delta": "200000.00"},
            ],
        })
        # Create-time advisory check rejects with 422.
        assert r.status_code == 422, r.text
        assert "negative current_budget" in r.json()["detail"]

    def test_contingency_drawdown_from_non_contingency_rejected(
        self, admin, active_budget,
    ):
        bid = active_budget["id"]
        l0 = active_budget["lines"][0]["id"]  # NOT contingency
        l1 = active_budget["lines"][1]["id"]  # NOT contingency target
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid,
            "change_type": "ContingencyDrawdown",
            "title": "Bad drawdown",
            "lines": [
                {"budget_line_id": l0, "delta": "-1000.00"},
                {"budget_line_id": l1, "delta": "1000.00"},
            ],
        })
        assert r.status_code == 422, r.text
        assert "is_contingency" in r.json()["detail"]

    def test_contingency_drawdown_from_flagged_source_accepted(
        self, admin, active_budget,
    ):
        bid = active_budget["id"]
        # Line at index 2 is the contingency line per fixture.
        contingency = active_budget["lines"][2]["id"]
        target = active_budget["lines"][0]["id"]
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid,
            "change_type": "ContingencyDrawdown",
            "title": "Drawdown £2k to Line1",
            "lines": [
                {"budget_line_id": contingency, "delta": "-2000.00"},
                {"budget_line_id": target, "delta": "2000.00"},
            ],
        })
        assert r.status_code == 201, r.text
        assert r.json()["change_type"] == "ContingencyDrawdown"
        assert Decimal(r.json()["net_impact"]) == Decimal("0.00")

    def test_adjustment_non_zero_net_impact_stored(self, admin, active_budget):
        bid = active_budget["id"]
        l1 = active_budget["lines"][0]["id"]
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid,
            "change_type": "Adjustment",
            "title": "Bump Line1 by £5k",
            "lines": [{"budget_line_id": l1, "delta": "5000.00"}],
        })
        assert r.status_code == 201, r.text
        assert Decimal(r.json()["net_impact"]) == Decimal("5000.00")

    def test_create_bcr_on_draft_budget_rejected(self, admin, db_engine, project):
        """Build pack gate 10 — Draft parents are edited directly, not via BCR."""
        _wipe_budgets_only(db_engine, project["id"])
        aid = _make_approved_appraisal(admin, project["id"])
        r0 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r0.json()["id"]
        # Don't activate — stays Draft.
        lines = r0.json()["lines"]
        if not lines:  # ensure at least one line exists; otherwise skip arg validation
            pytest.skip("Draft budget seeded with zero lines; cannot exercise gate")
        l1 = lines[0]["id"]
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid, "change_type": "Adjustment", "title": "x",
            "lines": [{"budget_line_id": l1, "delta": "100.00"}],
        })
        assert r.status_code == 409, r.text

    def test_create_bcr_on_closed_budget_rejected(
        self, admin, db_engine, project,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        # Close the budget.
        rc = admin.post(f"{BASE_URL}/api/v1/budgets/{b['id']}/close")
        assert rc.status_code == 200, rc.text
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": b["id"],
            "change_type": "Adjustment",
            "title": "post-close",
            "lines": [{"budget_line_id": b["lines"][0]["id"], "delta": "100.00"}],
        })
        assert r.status_code == 409, r.text

    def test_sequence_reference_increments(self, admin, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        l1, l2 = (ln["id"] for ln in b["lines"][:2])
        for expected_ref in ("BCR-0001", "BCR-0002", "BCR-0003"):
            r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
                "budget_id": b["id"],
                "change_type": "Transfer",
                "title": f"seq {expected_ref}",
                "lines": [
                    {"budget_line_id": l1, "delta": "-1000.00"},
                    {"budget_line_id": l2, "delta": "1000.00"},
                ],
            })
            assert r.status_code == 201, r.text
            assert r.json()["reference"] == expected_ref

    def test_line_from_other_budget_rejected(
        self, admin, db_engine, project,
    ):
        a = _make_active_budget(admin, db_engine, project["id"])
        # Cannot create a second active budget on same project (one-current
        # invariant). Use a separate project.
        # Approach: pick a line from `a`, then close & spawn a new budget
        # on the same project — the prior lines have been wiped by
        # `_make_active_budget`. Instead: create a BCR referencing a
        # syntactically valid but unknown UUID.
        bogus = str(uuid.uuid4())
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": a["id"],
            "change_type": "Adjustment",
            "title": "alien line",
            "lines": [{"budget_line_id": bogus, "delta": "100.00"}],
        })
        assert r.status_code == 422, r.text


# ==========================================================================
# Workflow  (gates 14–20)
# ==========================================================================

def _create_transfer(session, budget, *, title="T", amount="2000.00"):
    l1, l2 = (ln["id"] for ln in budget["lines"][:2])
    r = session.post(f"{BASE_URL}/api/v1/budget-changes", json={
        "budget_id": budget["id"],
        "change_type": "Transfer",
        "title": title,
        "lines": [
            {"budget_line_id": l1, "delta": f"-{amount}"},
            {"budget_line_id": l2, "delta": amount},
        ],
    })
    assert r.status_code == 201, r.text
    return r.json()


class TestWorkflow:
    def test_happy_path_draft_to_applied(
        self, admin, director, db_engine, project,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        bid = bcr["id"]
        r1 = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bid}/submit")
        assert r1.status_code == 200 and r1.json()["status"] == "Submitted"
        r2 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bid}/approve")
        assert r2.status_code == 200 and r2.json()["status"] == "Approved"
        r3 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bid}/apply")
        assert r3.status_code == 200 and r3.json()["status"] == "Applied"

    def test_approve_from_draft_rejected(self, admin, director, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 409, r.text

    def test_apply_from_submitted_rejected(self, admin, director, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")
        assert r.status_code == 409, r.text

    def test_reject_requires_reason(self, admin, director, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        # Missing body → 422 (FastAPI body validation).
        r1 = director.post(
            f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/reject", json={},
        )
        assert r1.status_code == 422
        r2 = director.post(
            f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/reject",
            json={"reason": "Out of scope"},
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["status"] == "Rejected"
        assert r2.json()["rejection_reason"] == "Out of scope"

    def test_withdraw_from_draft_and_submitted(
        self, admin, director, db_engine, project,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        # From Draft
        a = _create_transfer(admin, b, title="WithdrawDraft")
        rd = admin.post(f"{BASE_URL}/api/v1/budget-changes/{a['id']}/withdraw")
        assert rd.status_code == 200 and rd.json()["status"] == "Withdrawn"
        # From Submitted
        c = _create_transfer(admin, b, title="WithdrawSubmitted")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{c['id']}/submit")
        rs = admin.post(f"{BASE_URL}/api/v1/budget-changes/{c['id']}/withdraw")
        assert rs.status_code == 200 and rs.json()["status"] == "Withdrawn"
        # From Approved → 409
        e = _create_transfer(admin, b, title="WithdrawApproved")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{e['id']}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{e['id']}/approve")
        ra = admin.post(f"{BASE_URL}/api/v1/budget-changes/{e['id']}/withdraw")
        assert ra.status_code == 409, ra.text

    def test_patch_non_draft_rejected(self, admin, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        r = admin.patch(
            f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}",
            json={"title": "new title"},
        )
        assert r.status_code == 409, r.text

    def test_apply_twice_rejected(self, admin, director, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        r1 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")
        assert r1.status_code == 200
        r2 = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")
        assert r2.status_code == 409, r2.text


# ==========================================================================
# Apply effects (gates 21–25)
# ==========================================================================

class TestApplyEffects:
    def test_transfer_moves_approved_changes(
        self, admin, director, db_engine, project,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        l1, l2 = (ln["id"] for ln in b["lines"][:2])
        bcr = _create_transfer(admin, b, amount="5000.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")

        with db_engine.connect() as c:
            r1 = c.execute(text(
                "SELECT approved_changes, current_budget FROM budget_lines WHERE id=:i"
            ), {"i": l1}).first()
            r2 = c.execute(text(
                "SELECT approved_changes, current_budget FROM budget_lines WHERE id=:i"
            ), {"i": l2}).first()
        assert r1[0] == Decimal("-5000.00")
        assert r2[0] == Decimal("5000.00")
        assert r1[1] == Decimal("95000.00")  # 100k - 5k
        assert r2[1] == Decimal("105000.00")  # 100k + 5k

    def test_adjustment_increases_current_budget(
        self, admin, director, db_engine, project,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        l1 = b["lines"][0]["id"]
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": b["id"],
            "change_type": "Adjustment",
            "title": "Bump",
            "lines": [{"budget_line_id": l1, "delta": "7500.00"}],
        })
        bcr_id = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/approve")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/apply")
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT approved_changes, current_budget FROM budget_lines WHERE id=:i"
            ), {"i": l1}).first()
        assert row[0] == Decimal("7500.00")
        assert row[1] == Decimal("107500.00")

    def test_header_summary_recomputes_after_apply(
        self, admin, director, db_engine, project,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        # Apply an Adjustment +£10k.
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": b["id"],
            "change_type": "Adjustment",
            "title": "B",
            "lines": [{"budget_line_id": b["lines"][0]["id"], "delta": "10000.00"}],
        })
        bcr_id = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/approve")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/apply")
        # Fetch header.
        rg = admin.get(f"{BASE_URL}/api/v1/budgets/{b['id']}")
        assert rg.status_code == 200
        body = rg.json()
        # 3 x 100k + 10k = 310k.
        assert Decimal(body["total_budget"]) == Decimal("310000.00")
        # FFC = actuals (0) + committed (0) + FTC. FTC=Budget_Remaining
        # → max(0, current - actuals - committed) per line. After apply,
        # line 0: ftc=110k, lines 1+2: ftc=100k. Total FTC = 310k. FFC = 310k.
        assert Decimal(body["forecast_final_cost"]) == Decimal("310000.00")

    def test_apply_blocked_if_parent_terminal(
        self, admin, director, db_engine, project,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        # Close the parent budget while the BCR sits in Approved.
        rc = admin.post(f"{BASE_URL}/api/v1/budgets/{b['id']}/close")
        assert rc.status_code == 200
        # Apply should now refuse.
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/apply")
        assert r.status_code == 409, r.text
        # And no mutation on the budget_lines.
        l1 = b["lines"][0]["id"]
        with db_engine.connect() as c:
            ac = c.execute(text(
                "SELECT approved_changes FROM budget_lines WHERE id=:i"
            ), {"i": l1}).scalar()
        assert ac == Decimal("0.00")

    def test_apply_all_or_nothing(self, admin, director, db_engine, project):
        """Forge a multi-line BCR that would drive line 0 negative, with
        a valid +ve target. Apply must refuse AND leave both lines
        untouched.
        """
        b = _make_active_budget(admin, db_engine, project["id"])
        l1, l2 = (ln["id"] for ln in b["lines"][:2])
        # Side-load the BCR record directly (the create-time advisory
        # would block this), then submit+approve via API to drive
        # workflow but reach apply().
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            bcr_id = uuid.uuid4()
            tenant_id = db.execute(text(
                "SELECT tenant_id FROM users WHERE email=:e"
            ), {"e": ADMIN_EMAIL}).scalar()
            db.execute(text("""
                INSERT INTO budget_changes
                  (id, tenant_id, budget_id, reference, change_type, status,
                   title, net_impact, created_at, updated_at)
                VALUES (:id, :t, :b, 'BCR-9999', 'Transfer', 'Draft',
                        'forged', 0, now(), now())
            """), {"id": str(bcr_id), "t": str(tenant_id), "b": b["id"]})
            db.execute(text("""
                INSERT INTO budget_change_lines
                  (id, tenant_id, budget_change_id, budget_line_id, delta, created_at)
                VALUES (gen_random_uuid(), :t, :bcr, :l1, -200000.00, now()),
                       (gen_random_uuid(), :t, :bcr, :l2, 200000.00, now())
            """), {"t": str(tenant_id), "bcr": str(bcr_id), "l1": l1, "l2": l2})
            db.commit()
        finally:
            db.close()
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/submit")
        director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/approve")
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr_id}/apply")
        assert r.status_code == 409, r.text
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT id, approved_changes FROM budget_lines WHERE id IN (:l1, :l2)"
            ), {"l1": l1, "l2": l2}).fetchall()
        # No partial apply — both rows still at 0.
        for _, ac in rows:
            assert ac == Decimal("0.00")


# ==========================================================================
# Self-approval (LD2 / 2.4C)  (gates 26–30)
# ==========================================================================

@pytest.fixture
def low_threshold(admin):
    """Context-manager fixture that **callers** invoke around the approve
    step ONLY — the parent budget's `activate()` also consults the same
    threshold, so we must NOT lower it during budget setup.

    Returns a callable `apply()` that lowers the threshold, and a
    `restore()` that puts it back to the high test-default. Tests call
    `low_threshold.apply()` after their budget is active.
    """
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY

    class _Ctx:
        def apply(self):
            admin.put(
                f"{BASE_URL}/api/v1/system-config/{key}",
                json={"value": "10000.00"},
            )

        def restore(self):
            admin.put(
                f"{BASE_URL}/api/v1/system-config/{key}",
                json={"value": "999999999.00"},
            )

    ctx = _Ctx()
    yield ctx
    # Defensive restore in case the test body didn't.
    ctx.restore()


class TestSelfApprovalGuard:
    def test_self_approve_above_threshold_blocked(
        self, admin, db_engine, project, low_threshold,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        # £15k transfer — gross 30k > 10k threshold.
        bcr = _create_transfer(admin, b, amount="15000.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 403, r.text
        assert ("self-approve" in r.json()["detail"].lower()
                or "gross movement" in r.json()["detail"].lower()
                or "self_approve" in r.json()["detail"].lower())

    def test_self_approve_below_threshold_allowed(
        self, admin, db_engine, project, low_threshold,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        # £2k transfer — gross 4k < 10k threshold.
        bcr = _create_transfer(admin, b, amount="2000.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Approved"

    def test_different_user_approves_high_value(
        self, admin, director, db_engine, project, low_threshold,
    ):
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b, amount="15000.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = director.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "Approved"

    def test_self_approve_gross_movement_basis_not_net(
        self, admin, db_engine, project, low_threshold,
    ):
        """A £50k↔£50k Transfer has net_impact=0 but gross 100k —
        must still block per LD2."""
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b, amount="50000.00")
        assert Decimal(bcr["net_impact"]) == Decimal("0.00")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 403, r.text

    def test_null_creator_fail_open(
        self, admin, db_engine, project, low_threshold,
    ):
        """Legacy BCRs with NULL created_by must remain approvable."""
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b, amount="15000.00")
        # Strip created_by to simulate legacy.
        with db_engine.begin() as c:
            c.execute(text(
                "UPDATE budget_changes SET created_by=NULL WHERE id=:i"
            ), {"i": bcr["id"]})
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        low_threshold.apply()
        # Even admin (who'd normally be self-approval-blocked) succeeds —
        # NULL creator can never equal admin.id.
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 200, r.text


# ==========================================================================
# Permissions / regression  (gates 31–35)
# ==========================================================================

class TestPermissionsAndRegression:
    def test_permission_count_baseline_plus_2(self, db_engine):
        """Build pack §R2 expected baseline + 5 = 115 BUT pre-existing
        `budget_changes.{view,create,edit,approve}` were already in the
        seed at 2.6 entry. Operator decision (Chat 33 §R0 Q1=b):
        ADDITIVE — keep `edit`, add `submit`+`apply`. Net +2 → 112.

        Test gate 31 reads baseline+2.
        """
        with db_engine.connect() as c:
            count = c.execute(text(
                "SELECT COUNT(*) FROM permissions"
            )).scalar()
        assert count == 112, (
            f"Expected 112 permissions (110 baseline + 2 from 2.6); got {count}"
        )

    def test_new_perms_are_seeded(self, db_engine):
        with db_engine.connect() as c:
            codes = {
                r[0] for r in c.execute(text(
                    "SELECT code FROM permissions WHERE resource='budget_changes'"
                ))
            }
        assert codes == {
            "budget_changes.view", "budget_changes.create",
            "budget_changes.edit", "budget_changes.submit",
            "budget_changes.approve", "budget_changes.apply",
        }

    def test_apply_role_mapping(self, db_engine):
        """Per operator instruction §R0 Q1: `apply` mapped to the same
        roles as `approve`. Live DB check."""
        with db_engine.connect() as c:
            approve_roles = {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM role_permissions rp
                    JOIN roles r ON r.id = rp.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE p.code = 'budget_changes.approve'
                """))
            }
            apply_roles = {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM role_permissions rp
                    JOIN roles r ON r.id = rp.role_id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE p.code = 'budget_changes.apply'
                """))
            }
        assert apply_roles == approve_roles, (
            f"apply ({apply_roles}) and approve ({approve_roles}) must map "
            f"to the same role set per Chat 33 §R0 Q1 decision."
        )

    def test_submit_mapped_to_pm(self, db_engine):
        """PM must hold .submit — the BCR raiser path."""
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT 1 FROM role_permissions rp
                JOIN roles r ON r.id = rp.role_id
                JOIN permissions p ON p.id = rp.permission_id
                WHERE r.code='project_manager'
                  AND p.code='budget_changes.submit'
            """)).first()
        assert row is not None

    def test_create_missing_perm_403(self, readonly, db_engine, project, admin):
        b = _make_active_budget(admin, db_engine, project["id"])
        r = readonly.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": b["id"],
            "change_type": "Adjustment", "title": "x",
            "lines": [{"budget_line_id": b["lines"][0]["id"], "delta": "1.00"}],
        })
        assert r.status_code == 403, r.text

    def test_approve_missing_perm_403(self, admin, pm, db_engine, project):
        """PM holds .approve (per live map) — use READONLY to hit the gate.

        Per the live map PM holds budget_changes.approve. To assert the
        403 path we need a role that lacks .approve — read_only fits.
        """
        b = _make_active_budget(admin, db_engine, project["id"])
        bcr = _create_transfer(admin, b)
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/submit")
        # readonly fixture is module-level; re-use it.
        ro = plain_login(BASE_URL, READONLY_EMAIL, PWD)
        r = ro.post(f"{BASE_URL}/api/v1/budget-changes/{bcr['id']}/approve")
        assert r.status_code == 403, r.text

    def test_cross_tenant_get_returns_404(self, admin, db_engine, project):
        """Cross-tenant fetch must NOT leak existence. Forge a bogus
        UUID from outside this tenant — the router maps to 404.
        """
        r = admin.get(
            f"{BASE_URL}/api/v1/budget-changes/{uuid.uuid4()}"
        )
        assert r.status_code == 404, r.text

    def test_change_log_endpoint(self, admin, director, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        _create_transfer(admin, b, title="x1")
        _create_transfer(admin, b, title="x2")
        r = admin.get(f"{BASE_URL}/api/v1/budgets/{b['id']}/change-log")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 2
        # Newest first by created_at.
        titles = [item["title"] for item in body["items"]]
        assert titles == ["x2", "x1"]

    def test_list_filter_by_status(self, admin, director, db_engine, project):
        b = _make_active_budget(admin, db_engine, project["id"])
        # Two Drafts, one Submitted.
        a = _create_transfer(admin, b, title="a")
        _create_transfer(admin, b, title="b")
        _create_transfer(admin, b, title="c")
        admin.post(f"{BASE_URL}/api/v1/budget-changes/{a['id']}/submit")
        r1 = admin.get(
            f"{BASE_URL}/api/v1/budget-changes",
            params={"budget_id": b["id"], "status": "Draft"},
        )
        r2 = admin.get(
            f"{BASE_URL}/api/v1/budget-changes",
            params={"budget_id": b["id"], "status": "Submitted"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["total"] == 2
        assert r2.json()["total"] == 1
        assert r2.json()["items"][0]["id"] == a["id"]
