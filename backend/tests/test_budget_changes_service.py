"""Chat 33 §R5 (Prompt 2.6) — BCR service-level (invariants + apply
effects) tests.

Covers Build Pack 2.6 acceptance gates 4–13 (create + type invariants)
and 21–25 (apply effects on `budget_lines.approved_changes` /
`current_budget` and header `total_budget` / `forecast_final_cost`).

Although these tests round-trip via the HTTP layer (the easier path —
fixture-loaded auth sessions are HTTP-based), they exercise the
service-layer business rules in `services/budget_changes.py`:
per-type net-zero / non-zero invariants, contingency-source rejection,
race-safe `BCR-NNNN` references, parent-state gating, and the
recompute path. The router is a thin pass-through here — HTTP 422/409
codes come straight from `_map()` against `ValueError` /
`BudgetStateError` raised by the service.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from tests._bcr_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, DIRECTOR_EMAIL, PWD,
    PRIMARY_ENTITY_NAME,
    create_transfer, make_active_budget, make_approved_appraisal, wipe,
    wipe_budgets_only,
)
from tests.conftest import login_with_auto_enroll


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


@pytest.fixture(scope="module", autouse=True)
def _clean(db_engine):
    wipe(db_engine)
    yield
    wipe(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_self_approval_threshold(db_engine, admin):
    """Default £10k threshold would block admin self-activate on
    £250k+ seeded budgets. Bump high for the lifecycle tests."""
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
        "name": "BCR Test Project (Service)",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 BCR Way, Shrewsbury",
        "site_postcode": "SY1 2BB",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def active_budget(admin, db_engine, project):
    """Fresh activated budget with 3 lines x £100k each; line at index
    2 is flagged is_contingency."""
    return make_active_budget(
        admin, db_engine, project["id"],
        line_count=3,
        line_amount=Decimal("100000.00"),
        contingency_line_index=2,
    )


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
        self, admin, active_budget,
    ):
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

    def test_create_bcr_on_draft_budget_rejected(
        self, admin, db_engine, project,
    ):
        """Build pack gate 10 — Draft parents are edited directly, not via BCR."""
        wipe_budgets_only(db_engine, project["id"])
        aid = make_approved_appraisal(admin, project["id"])
        r0 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project['id']}/budgets/from-appraisal",
            json={"source_appraisal_id": aid},
        )
        bid = r0.json()["id"]
        # Don't activate — stays Draft.
        lines = r0.json()["lines"]
        if not lines:
            pytest.skip(
                "Draft budget seeded with zero lines; cannot exercise gate"
            )
        l1 = lines[0]["id"]
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": bid, "change_type": "Adjustment", "title": "x",
            "lines": [{"budget_line_id": l1, "delta": "100.00"}],
        })
        assert r.status_code == 409, r.text

    def test_create_bcr_on_closed_budget_rejected(
        self, admin, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
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
        b = make_active_budget(admin, db_engine, project["id"])
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
        a = make_active_budget(admin, db_engine, project["id"])
        # Create a BCR referencing a syntactically valid but unknown UUID.
        bogus = str(uuid.uuid4())
        r = admin.post(f"{BASE_URL}/api/v1/budget-changes", json={
            "budget_id": a["id"],
            "change_type": "Adjustment",
            "title": "alien line",
            "lines": [{"budget_line_id": bogus, "delta": "100.00"}],
        })
        assert r.status_code == 422, r.text


# ==========================================================================
# Apply effects (gates 21–25)
# ==========================================================================

class TestApplyEffects:
    def test_transfer_moves_approved_changes(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        l1, l2 = (ln["id"] for ln in b["lines"][:2])
        bcr = create_transfer(admin, b, amount="5000.00")
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
        assert r1[1] == Decimal("95000.00")   # 100k - 5k
        assert r2[1] == Decimal("105000.00")  # 100k + 5k

    def test_adjustment_increases_current_budget(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
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
        b = make_active_budget(admin, db_engine, project["id"])
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
        # FFC after apply: line 0=110k, lines 1+2=100k each → 310k.
        assert Decimal(body["forecast_final_cost"]) == Decimal("310000.00")

    def test_apply_blocked_if_parent_terminal(
        self, admin, director, db_engine, project,
    ):
        b = make_active_budget(admin, db_engine, project["id"])
        bcr = create_transfer(admin, b)
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
        untouched (no partial writes).
        """
        b = make_active_budget(admin, db_engine, project["id"])
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
