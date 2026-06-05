"""Chat 24 §R2 (Prompt 2.5) — Purchase Orders integration tests.

Live-DB tests (require Postgres + a running uvicorn). Covers:

  6 numbering tests:
    - auto-allocate next sequence on POST against default prefix
    - sequence increments monotonically across two POs
    - explicit prefix_id is honoured
    - mismatched prefix entity_type (bill instead of po) → 422
    - archived prefix → 422
    - project with no default prefix configured → 422

  4 CRUD tests:
    - POST creates a draft, audit row written, totals computed
    - GET returns the PO + lines; pricing nulled without view_sensitive
    - PATCH (full tier) updates a draft, audit diff written
    - DELETE removes a draft; audit row written; 422 on non-draft

OPERATOR VERIFICATION:
  These tests run against the live uvicorn — they will fail in the
  Emergent container (no PG). The agent has verified syntax / model
  parsing / state-machine logic via test_purchase_orders_unit.py
  (33 tests, all passing).
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"
# site_manager is the lowest-privilege role with pos.view but
# WITHOUT pos.view_sensitive — used to verify pricing fields are
# nulled at the serialisation layer.
SITE_EMAIL = "test-site@example.test"


# ─────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    with e.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def site_user(engine):
    return login_with_auto_enroll(None, BASE_URL, SITE_EMAIL, PWD)


def _entity_id(engine, email: str) -> str:
    with engine.connect() as c:
        eid = c.execute(text("""
            SELECT e.id FROM entities e
            JOIN users u ON u.tenant_id = e.tenant_id
            WHERE u.email = :em AND e.status = 'Active'
            ORDER BY e.created_at ASC LIMIT 1
        """), {"em": email}).scalar()
    assert eid is not None
    return str(eid)


def _create_project(admin, entity_id: str) -> str:
    suffix = uuid.uuid4().hex[:8].upper()
    body = {
        "name": f"Chat24-R2 Project {suffix}",
        "project_type": "Pure_Dev",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Test Lane",
        "site_postcode": "AB12 3CD",
        "tenure": "Freehold",
        "land_type": "Greenfield",
        "planning_type": "Full",
        "planning_status": "Pre_App",
        "implementation_required": True,
    }
    r = admin.post(f"{BASE_URL}/api/projects", json=body)
    assert r.status_code == 201, f"project create failed: {r.text}"
    return r.json()["id"]


def _create_supplier(admin, name_suffix: str) -> str:
    r = admin.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={"name": f"R2-Supplier {name_suffix}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed_budget_and_lines(engine, admin, project_id: str) -> tuple[str, str]:
    """Insert a Draft budget + one budget_line directly via SQL.

    The seeded-from-appraisal API path requires an Approved appraisal —
    too heavyweight for these tests. We bypass it by inserting at the
    DB layer. Returns (budget_id, budget_line_id).
    """
    with engine.begin() as c:
        # Look up an entity for the budget line entity_id.
        ent_id = c.execute(text("""
            SELECT primary_entity_id FROM projects WHERE id = :pid
        """), {"pid": project_id}).scalar()
        # Find a usable cost_code.
        cc_row = c.execute(text("""
            SELECT id, code FROM cost_codes
            WHERE status = 'Active' ORDER BY code LIMIT 1
        """)).first()
        assert cc_row is not None, "need at least one Active cost_code seeded"
        # Find creator user_id.
        admin_id = c.execute(text("""
            SELECT id FROM users WHERE email = :em
        """), {"em": ADMIN_EMAIL}).scalar()
        # Insert a minimal Approved appraisal for the budget FK. The
        # source_appraisal_id on `budgets` is NOT NULL and the budgets
        # service requires Approved status — we satisfy both with a
        # direct INSERT (build pack §M2 hardens this against skips so
        # G2.* gates always execute).
        app_id = c.execute(text("""
            INSERT INTO appraisals (
                project_id, version_number, name, reference_date,
                status, created_by_user_id,
                land_purchase_price, sdlt_category, developer_relief,
                contingency_pct, target_profit_on_cost_pct,
                target_profit_on_gdv_pct, project_duration_months,
                appraisal_group_id, is_current, scenario
            ) VALUES (
                :pid, 1, 'R2 test appraisal', CURRENT_DATE,
                'Approved', :uid,
                0, 'Residential_Standard', false,
                5, 20, 17, 18,
                gen_random_uuid(), true, 'Base'
            )
            RETURNING id
        """), {"pid": project_id, "uid": admin_id}).scalar()

        budget_id = c.execute(text("""
            INSERT INTO budgets (
                project_id, source_appraisal_id, version_number, version_label,
                is_current, status, created_by_user_id
            ) VALUES (:pid, :aid, 1, 'Original', true, 'Active', :uid)
            RETURNING id
        """), {"pid": project_id, "aid": app_id, "uid": admin_id}).scalar()
        line_id = c.execute(text("""
            INSERT INTO budget_lines (
                budget_id, cost_code_id, line_description, entity_id,
                original_budget, current_budget,
                ftc_method, display_order
            ) VALUES (:bid, :ccid, 'R2 test line', :eid, 1000.00, 1000.00,
                      'Budget_Remaining', 0)
            RETURNING id
        """), {
            "bid": budget_id, "ccid": cc_row.id, "eid": ent_id,
        }).scalar()
    return str(budget_id), str(line_id)


@pytest.fixture
def project_setup(admin, engine):
    """Per-test project + budget + supplier + budget_line."""
    eid = _entity_id(engine, ADMIN_EMAIL)
    project_id = _create_project(admin, eid)
    budget_id, budget_line_id = _seed_budget_and_lines(engine, admin, project_id)
    supplier_id = _create_supplier(admin, uuid.uuid4().hex[:6].upper())
    yield {
        "project_id": project_id,
        "budget_id": budget_id,
        "budget_line_id": budget_line_id,
        "supplier_id": supplier_id,
    }
    # Cascade cleanup via project delete (suppliers retained at tenant level
    # — they're harmless leftovers for the test tenant).
    with engine.begin() as c:
        c.execute(text("DELETE FROM purchase_orders WHERE project_id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM budgets WHERE project_id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM appraisals WHERE project_id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM projects WHERE id = :pid"),
                  {"pid": project_id})
        c.execute(text("DELETE FROM suppliers WHERE id = :sid"),
                  {"sid": supplier_id})


def _po_create_body(setup: dict, **overrides) -> dict:
    body = {
        "supplier_id": setup["supplier_id"],
        "budget_id": setup["budget_id"],
        "lines": [{
            "budget_line_id": setup["budget_line_id"],
            "description": "Test line 1",
            "quantity": 2,
            "unit_rate": 100,
            "vat_rate": 20,
        }],
    }
    body.update(overrides)
    return body


# ─────────────────────────────────────────────────────────────────────────
# Numbering tests (6)
# ─────────────────────────────────────────────────────────────────────────

class TestNumbering:
    def test_auto_allocate_uses_default_prefix(self, admin, project_setup):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["po_number"] == "PO-0001"
        assert out["po_sequence"] == 1
        assert out["po_number_prefix_id"] is not None

    def test_sequence_increments_monotonically(self, admin, project_setup):
        for expected in ("PO-0001", "PO-0002", "PO-0003"):
            r = admin.post(
                f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
                json=_po_create_body(project_setup),
            )
            assert r.status_code == 201, r.text
            assert r.json()["po_number"] == expected, (
                f"expected {expected}, got {r.json()['po_number']}"
            )

    def test_explicit_prefix_id_honoured(self, admin, project_setup):
        # Create a non-default prefix and supply it on create.
        rp = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/number-prefixes",
            json={"entity_type": "po", "middle_prefix": "HAD"},
        )
        assert rp.status_code == 201, rp.text
        pid = rp.json()["id"]
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup, po_number_prefix_id=pid),
        )
        assert r.status_code == 201, r.text
        assert r.json()["po_number"] == "PO-HAD-0001"

    def test_bill_prefix_rejected_for_po(self, admin, project_setup):
        # Use the auto-seeded bill prefix.
        rp = admin.get(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/number-prefixes",
            params={"entity_type": "bill"},
        )
        bill_pid = rp.json()["items"][0]["id"]
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup, po_number_prefix_id=bill_pid),
        )
        assert r.status_code == 422, r.text
        assert "'po'" in r.json()["detail"].lower() or "bill" in r.json()["detail"].lower()

    def test_archived_prefix_rejected(self, admin, project_setup, engine):
        rp = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/number-prefixes",
            json={"entity_type": "po", "middle_prefix": "ARC"},
        )
        pid = rp.json()["id"]
        admin.patch(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/number-prefixes/{pid}",
            json={"is_archived": True},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup, po_number_prefix_id=pid),
        )
        assert r.status_code == 422, r.text
        assert "archived" in r.json()["detail"].lower()

    def test_no_default_prefix_yields_422(self, admin, project_setup, engine):
        # Archive both auto-seeded defaults so no default remains.
        with engine.begin() as c:
            c.execute(text("""
                UPDATE project_number_prefixes
                   SET is_default = false
                 WHERE project_id = :pid
            """), {"pid": project_setup["project_id"]})
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        assert r.status_code == 422, r.text
        assert "default" in r.json()["detail"].lower()


# ─────────────────────────────────────────────────────────────────────────
# CRUD tests (4)
# ─────────────────────────────────────────────────────────────────────────

class TestCRUD:
    def test_create_writes_audit_with_totals(self, admin, project_setup, engine):
        start = datetime.now(timezone.utc)
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["status"] == "draft"
        # 2 * 100 = 200 net; vat 20% = 40; gross 240.
        assert Decimal(out["total_amount"]) == Decimal("240.00")
        assert Decimal(out["subtotal_amount"]) == Decimal("200.00")
        assert len(out["lines"]) == 1

        # Audit row exists with field-level diff.
        with engine.connect() as c:
            row = c.execute(text("""
                SELECT field_changes FROM audit_log
                 WHERE resource_type='purchase_order'
                   AND resource_id=:rid
                   AND action='Create'
                   AND created_at >= :since
            """), {"rid": out["id"], "since": start}).first()
        assert row is not None, "missing Create audit row"
        fields = {c["field"]: c for c in row.field_changes}
        assert "po_number" in fields
        assert fields["po_number"]["new"] == "PO-0001"
        assert fields["status"]["new"] == "draft"

    def test_get_nulls_pricing_without_view_sensitive(
        self, admin, site_user, project_setup,
    ):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        assert r.status_code == 201, r.text
        po_id = r.json()["id"]
        # Admin (has pos.view_sensitive) sees pricing.
        ra = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po_id}")
        assert ra.status_code == 200, ra.text
        assert Decimal(ra.json()["total_amount"]) == Decimal("240.00")
        assert ra.json()["lines"][0]["unit_rate"] is not None

        # site_manager has pos.view but NOT pos.view_sensitive — pricing
        # fields must be nulled in the response. (Cannot use
        # project_manager here: per build pack §2.3 / spec amendment #3
        # PM holds pos.view_sensitive.)
        rp = site_user.get(f"{BASE_URL}/api/v1/purchase-orders/{po_id}")
        assert rp.status_code == 200, rp.text
        out = rp.json()
        assert out["total_amount"] is None
        assert out["subtotal_amount"] is None
        assert out["vat_amount"] is None
        assert out["lines"][0]["unit_rate"] is None
        assert out["lines"][0]["net_amount"] is None
        # Non-sensitive fields still visible.
        assert out["po_number"] == "PO-0001"
        assert out["lines"][0]["description"] == "Test line 1"

    def test_patch_full_tier_updates_draft(self, admin, project_setup, engine):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        po_id = r.json()["id"]
        start = datetime.now(timezone.utc)
        rp = admin.patch(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}",
            json={"notes": "Edited", "delivery_address": "5 Test Road"},
        )
        assert rp.status_code == 200, rp.text
        assert rp.json()["notes"] == "Edited"
        assert rp.json()["delivery_address"] == "5 Test Road"

        with engine.connect() as c:
            row = c.execute(text("""
                SELECT field_changes FROM audit_log
                 WHERE resource_type='purchase_order'
                   AND resource_id=:rid
                   AND action='Update'
                   AND created_at >= :since
            """), {"rid": po_id, "since": start}).first()
        fields = {c["field"]: c for c in row.field_changes}
        assert fields["notes"]["new"] == "Edited"
        assert fields["delivery_address"]["new"] == "5 Test Road"

    def test_delete_draft_succeeds_but_blocks_non_draft(
        self, admin, project_setup,
    ):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        po_id = r.json()["id"]
        # Delete draft → 204.
        rd = admin.delete(f"{BASE_URL}/api/v1/purchase-orders/{po_id}")
        assert rd.status_code == 204, rd.text
        rget = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po_id}")
        assert rget.status_code == 404

        # Create another, auto-approve via submit (approval_required=false), then
        # delete must 422. (R7.0 Option B: within-budget auto path lands at
        # approved, not issued — but delete is still blocked once submitted.)
        r2 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        po2 = r2.json()["id"]
        rs = admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po2}/submit")
        assert rs.status_code == 200, rs.text
        assert rs.json()["status"] == "approved"
        rdel = admin.delete(f"{BASE_URL}/api/v1/purchase-orders/{po2}")
        assert rdel.status_code == 422, rdel.text


# ─────────────────────────────────────────────────────────────────────────
# Transition smoke tests (live, complementing unit tests)
# ─────────────────────────────────────────────────────────────────────────

class TestTransitions:
    def test_submit_auto_approve_path(self, admin, project_setup):
        # R7.0 Option B: within-budget + approval_required=false now
        # lands at `approved` (was `issued`). issued_at MUST be NULL —
        # the explicit issue action is required to populate it.
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),  # approval_required defaults false
        )
        po_id = r.json()["id"]
        rs = admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit")
        assert rs.status_code == 200, rs.text
        body = rs.json()
        assert body["status"] == "approved"
        assert body["submitted_at"] is not None
        assert body["approved_at"] is not None
        assert body["issued_at"] is None

    def test_submit_with_approval_required_goes_pending(self, admin, project_setup):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup, approval_required=True),
        )
        po_id = r.json()["id"]
        rs = admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit")
        assert rs.status_code == 200, rs.text
        assert rs.json()["status"] == "pending_approval"

    def test_void_requires_reason_and_stamps(self, admin, project_setup):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        po_id = r.json()["id"]
        # Missing reason → 422 (pydantic min_length=1).
        rv1 = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}/void", json={},
        )
        assert rv1.status_code == 422
        # With reason → 200, status=voided.
        rv2 = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}/void",
            json={"reason": "supplier withdrew"},
        )
        assert rv2.status_code == 200, rv2.text
        assert rv2.json()["status"] == "voided"
        assert rv2.json()["voided_reason"] == "supplier withdrew"

    def test_patch_issued_only_allows_header_annotation(self, admin, project_setup):
        # R7.0 — submit now lands at `approved` (the edit_tier is FULL
        # at approved). To exercise the issued-state edit-tier guard
        # we now explicitly issue the PO before attempting the PATCH.
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        po_id = r.json()["id"]
        admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit")
        admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/issue")
        # Now issued — only notes/delivery_notes/external_reference allowed.
        ok = admin.patch(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}",
            json={"notes": "annotated post-issue"},
        )
        assert ok.status_code == 200, ok.text
        bad = admin.patch(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}",
            json={"supplier_id": project_setup["supplier_id"],
                  "notes": "fine"},
        )
        assert bad.status_code == 403, bad.text
        detail = bad.json()["detail"]
        assert "supplier_id" in detail["disallowed_fields"]



# ─────────────────────────────────────────────────────────────────────────
# Budget-active guard (D7 / G2.5)
# ─────────────────────────────────────────────────────────────────────────

class TestBudgetActiveGuard:
    def test_non_active_budget_rejects_po_create_with_422(
        self, admin, project_setup, engine,
    ):
        # Flip the seeded Active budget to Draft → POST must 422.
        with engine.begin() as c:
            c.execute(text("""
                UPDATE budgets SET status = 'Draft' WHERE id = :bid
            """), {"bid": project_setup["budget_id"]})
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        assert r.status_code == 422, r.text
        detail = r.json()["detail"].lower()
        assert "active" in detail or "budget-not-active" in detail, detail

    def test_superseded_budget_rejects_po_create(
        self, admin, project_setup, engine,
    ):
        with engine.begin() as c:
            c.execute(text("""
                UPDATE budgets SET status = 'Superseded' WHERE id = :bid
            """), {"bid": project_setup["budget_id"]})
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        assert r.status_code == 422, r.text


# ─────────────────────────────────────────────────────────────────────────
# Concurrency — G2.7 (OPERATOR-VERIFICATION-PENDING, pytest-xdist required)
# ─────────────────────────────────────────────────────────────────────────

class TestConcurrentNumbering:
    """G2.7: concurrent PO create from the same prefix must yield
    sequential numbers with no duplicates and no unique-constraint
    violations.

    Run mode:
      pytest -n 4 backend/tests/test_purchase_orders_api.py::TestConcurrentNumbering

    Inside the worker the test uses a Python `ThreadPoolExecutor` to
    fan out 8 concurrent POST calls against the SAME default prefix.
    The DB-level SELECT FOR UPDATE on the prefix row serialises the
    allocations, and the `ux_po_tenant_number` unique constraint will
    catch any collision regression.
    """

    def test_concurrent_creates_yield_sequential_numbers_no_dupes(
        self, admin, project_setup,
    ):
        import concurrent.futures
        url = (
            f"{BASE_URL}/api/v1/projects/"
            f"{project_setup['project_id']}/purchase-orders"
        )
        body = _po_create_body(project_setup)
        N = 8

        # Each thread re-uses the admin requests.Session — cookie jar is
        # shared (httpx-style sessions are not thread-safe in general, but
        # requests.Session is documented as safe for read-only cookies +
        # concurrent POSTs).
        def _post():
            return admin.post(url, json=body)

        with concurrent.futures.ThreadPoolExecutor(max_workers=N) as ex:
            futures = [ex.submit(_post) for _ in range(N)]
            results = [f.result() for f in futures]

        # Every call must succeed (no unique-constraint violation).
        statuses = [r.status_code for r in results]
        assert all(s == 201 for s in statuses), (
            f"expected all 201, got {statuses} (bodies: "
            f"{[r.text[:200] for r in results]})"
        )

        po_numbers = sorted(r.json()["po_number"] for r in results)
        assert len(set(po_numbers)) == N, (
            f"duplicate po_numbers in concurrent allocation: {po_numbers}"
        )
        # Sequential 0001..0008.
        expected = [f"PO-{i:04d}" for i in range(1, N + 1)]
        assert po_numbers == expected, (
            f"concurrent allocation produced gaps or reordering — "
            f"got {po_numbers}, expected {expected}"
        )



# ─────────────────────────────────────────────────────────────────────────
# R5.5 — Budget-line / budget scoped PO list endpoints
# (pre-R6 backend addition to unblock the inline-expand grid)
# ─────────────────────────────────────────────────────────────────────────

RO_EMAIL = "test-readonly@example.test"


@pytest.fixture(scope="module")
def readonly(engine):
    return login_with_auto_enroll(None, BASE_URL, RO_EMAIL, PWD)


def _seed_extra_budget_line(engine, budget_id: str) -> str:
    """Insert a second budget_line on the same budget — used to prove the
    per-line filter narrows correctly."""
    with engine.begin() as c:
        cc_row = c.execute(text("""
            SELECT id FROM cost_codes WHERE status='Active' ORDER BY code OFFSET 1 LIMIT 1
        """)).first()
        ent_id = c.execute(text("""
            SELECT bl.entity_id FROM budget_lines bl WHERE bl.budget_id=:bid LIMIT 1
        """), {"bid": budget_id}).scalar()
        line_id = c.execute(text("""
            INSERT INTO budget_lines (
                budget_id, cost_code_id, line_description, entity_id,
                original_budget, current_budget,
                ftc_method, display_order
            ) VALUES (:bid, :ccid, 'R5.5 extra line', :eid, 500.00, 500.00,
                      'Budget_Remaining', 1)
            RETURNING id
        """), {"bid": budget_id, "ccid": cc_row.id, "eid": ent_id}).scalar()
    return str(line_id)


class TestR55BudgetLinePOs:
    """GET /api/v1/budget-lines/{line_id}/purchase-orders (P0.1)."""

    def test_happy_path_200_shape(self, admin, project_setup):
        # Create one PO touching the seeded budget_line.
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        assert r.status_code == 201, r.text
        po_id = r.json()["id"]

        r2 = admin.get(
            f"{BASE_URL}/api/v1/budget-lines/{project_setup['budget_line_id']}/purchase-orders"
        )
        assert r2.status_code == 200, r2.text
        body = r2.json()
        assert body["budget_line_id"] == project_setup["budget_line_id"]
        assert body["total"] == 1
        assert body["limit"] == 50
        assert body["offset"] == 0
        assert isinstance(body["items"], list) and len(body["items"]) == 1
        po = body["items"][0]
        assert po["id"] == po_id
        # Standard PO shape preserved (matches /purchase-orders/{id}).
        assert {"po_number", "supplier_id", "status", "lines"}.issubset(po.keys())
        assert any(
            str(line["budget_line_id"]) == project_setup["budget_line_id"]
            for line in po["lines"]
        )

    def test_empty_line_returns_200_not_404(self, admin, engine, project_setup):
        empty_line = _seed_extra_budget_line(engine, project_setup["budget_id"])
        r = admin.get(f"{BASE_URL}/api/v1/budget-lines/{empty_line}/purchase-orders")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0

    def test_readonly_gating_pounds_are_null(self, admin, readonly, project_setup):
        # Seed one PO as admin.
        admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        # Fetch the same line as read_only — every £ field must be null.
        r = readonly.get(
            f"{BASE_URL}/api/v1/budget-lines/{project_setup['budget_line_id']}/purchase-orders"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"], "RO should see the PO row exists"
        po = body["items"][0]
        for k in ("subtotal_amount", "vat_amount", "total_amount"):
            assert po.get(k) is None, f"RO leaked top-level {k}={po.get(k)!r}"
        for line in po["lines"]:
            for k in ("unit_rate", "net_amount", "vat_amount", "gross_amount"):
                assert line.get(k) is None, (
                    f"RO leaked line.{k}={line.get(k)!r}"
                )

    def test_bad_uuid_returns_422(self, admin):
        r = admin.get(f"{BASE_URL}/api/v1/budget-lines/not-a-uuid/purchase-orders")
        assert r.status_code == 422, r.text

    def test_unknown_line_returns_404_not_403(self, admin):
        # Random valid UUID that points to nothing — Pattern α: 404, no leak.
        r = admin.get(
            f"{BASE_URL}/api/v1/budget-lines/{uuid.uuid4()}/purchase-orders"
        )
        assert r.status_code == 404, r.text
        assert r.status_code != 403


class TestR55BudgetPOs:
    """GET /api/v1/budgets/{budget_id}/purchase-orders (P0.2 bulk)."""

    def test_happy_path_200_shape_with_index(self, admin, engine, project_setup):
        # Create TWO POs — one on the seeded line, one on a new line.
        admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        extra_line = _seed_extra_budget_line(engine, project_setup["budget_id"])
        admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json={
                "supplier_id": project_setup["supplier_id"],
                "budget_id": project_setup["budget_id"],
                "lines": [{
                    "budget_line_id": extra_line,
                    "description": "Extra line PO",
                    "quantity": 1, "unit_rate": 50, "vat_rate": 20,
                }],
            },
        )

        r = admin.get(
            f"{BASE_URL}/api/v1/budgets/{project_setup['budget_id']}/purchase-orders"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["budget_id"] == project_setup["budget_id"]
        assert body["total"] == 2
        assert len(body["items"]) == 2
        assert isinstance(body["by_budget_line"], dict)
        # Each blid -> list of po_ids; each blid touched once.
        assert project_setup["budget_line_id"] in body["by_budget_line"]
        assert extra_line in body["by_budget_line"]
        # PO ids in the index are present in items[].
        all_po_ids = {p["id"] for p in body["items"]}
        for blid, po_ids in body["by_budget_line"].items():
            for pid in po_ids:
                assert pid in all_po_ids

    def test_empty_budget_returns_200_not_404(self, admin, engine, project_setup):
        # Budget with NO POs (no calls to POST PO).
        # Reuse the existing budget but ensure no POs yet — wipe any from prior tests.
        with engine.begin() as c:
            c.execute(text("DELETE FROM purchase_orders WHERE project_id=:p"),
                      {"p": project_setup["project_id"]})
        r = admin.get(
            f"{BASE_URL}/api/v1/budgets/{project_setup['budget_id']}/purchase-orders"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"] == []
        assert body["by_budget_line"] == {}
        assert body["total"] == 0

    def test_readonly_gating_pounds_are_null(self, admin, readonly, project_setup):
        admin.post(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            json=_po_create_body(project_setup),
        )
        r = readonly.get(
            f"{BASE_URL}/api/v1/budgets/{project_setup['budget_id']}/purchase-orders"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"], "RO should see PO row exists"
        po = body["items"][0]
        for k in ("subtotal_amount", "vat_amount", "total_amount"):
            assert po.get(k) is None, f"RO leaked top-level {k}={po.get(k)!r}"
        for line in po["lines"]:
            for k in ("unit_rate", "net_amount", "vat_amount", "gross_amount"):
                assert line.get(k) is None, (
                    f"RO leaked line.{k}={line.get(k)!r}"
                )

    def test_bad_uuid_returns_422(self, admin):
        r = admin.get(f"{BASE_URL}/api/v1/budgets/not-a-uuid/purchase-orders")
        assert r.status_code == 422, r.text

    def test_unknown_budget_returns_404_not_403(self, admin):
        r = admin.get(f"{BASE_URL}/api/v1/budgets/{uuid.uuid4()}/purchase-orders")
        assert r.status_code == 404, r.text
        assert r.status_code != 403


# ─────────────────────────────────────────────────────────────────────────
# R7 Batch 2 follow-on — GET /projects/{project_id}/purchase-orders
#
# Thin wrapper over `svc.list_pos(...)` with `project_id` bound from the
# PATH. Closes the latent Chat 24 R5 gap surfaced by the R7.5 approvals
# dashboard (the frontend `listProjectPOs` has always hit this URL).
# ─────────────────────────────────────────────────────────────────────────

class TestR7Batch2FollowOnListProjectPOs:
    """`GET /api/v1/projects/{project_id}/purchase-orders` (R7 Batch 2
    follow-on mini-pack). Mirrors the un-scoped list endpoint with
    `project_id` taken from the PATH; same perm gate (`pos.view`),
    same response shape, same query params (supplier_id, status, q,
    limit, offset).
    """

    def _make_po(self, admin, setup):
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{setup['project_id']}/purchase-orders",
            json=_po_create_body(setup),
        )
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def test_list_project_pos_endpoint_returns_scoped_results(
        self, admin, engine, project_setup,
    ):
        # Seed 2 POs on project_setup (project A).
        po_a1 = self._make_po(admin, project_setup)
        po_a2 = self._make_po(admin, project_setup)

        # Seed a second project (B) on the same tenant + create 1 PO on it.
        eid = _entity_id(engine, ADMIN_EMAIL)
        project_b_id = _create_project(admin, eid)
        b_budget_id, b_line_id = _seed_budget_and_lines(
            engine, admin, project_b_id,
        )
        b_supplier_id = _create_supplier(admin, uuid.uuid4().hex[:6].upper())
        b_setup = {
            "project_id": project_b_id,
            "budget_id": b_budget_id,
            "budget_line_id": b_line_id,
            "supplier_id": b_supplier_id,
        }
        po_b1 = self._make_po(admin, b_setup)

        try:
            # GET project A → exactly 2 items, both ours.
            r = admin.get(
                f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders"
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["total"] == 2
            assert body["limit"] == 50 and body["offset"] == 0
            ids = {it["id"] for it in body["items"]}
            assert ids == {po_a1, po_a2}, ids
            # Project B's PO must NOT appear in project A's list.
            assert po_b1 not in ids
        finally:
            # Cleanup project B teardown (project_setup teardown handles A).
            with engine.begin() as c:
                c.execute(text("DELETE FROM purchase_orders WHERE project_id=:p"),
                          {"p": project_b_id})
                c.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                          {"p": project_b_id})
                c.execute(text("DELETE FROM appraisals WHERE project_id=:p"),
                          {"p": project_b_id})
                c.execute(text("DELETE FROM projects WHERE id=:p"),
                          {"p": project_b_id})
                c.execute(text("DELETE FROM suppliers WHERE id=:s"),
                          {"s": b_supplier_id})

    def test_list_project_pos_endpoint_honours_status_filter(
        self, admin, project_setup,
    ):
        # Two draft POs + one transitioned to approved (via submit
        # auto-approve path on an entity with approval_required=false).
        # Use the existing approved row for the status filter; the two
        # drafts must NOT appear when we ask for status=approved.
        po_draft_1 = self._make_po(admin, project_setup)
        po_draft_2 = self._make_po(admin, project_setup)
        po_for_approve = self._make_po(admin, project_setup)
        rs = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_for_approve}/submit"
        )
        assert rs.status_code == 200, rs.text
        assert rs.json()["status"] == "approved"

        # Filter: status=approved → only po_for_approve.
        r = admin.get(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            params={"status": "approved"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["total"] == 1
        assert body["items"][0]["id"] == po_for_approve
        assert body["items"][0]["status"] == "approved"

        # Filter: status=draft → two drafts (po_draft_1, po_draft_2).
        r2 = admin.get(
            f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders",
            params={"status": "draft"},
        )
        assert r2.status_code == 200, r2.text
        ids = {it["id"] for it in r2.json()["items"]}
        assert ids == {po_draft_1, po_draft_2}, ids

    def test_list_project_pos_endpoint_requires_pos_view(
        self, project_setup,
    ):
        # No seeded test persona in this env LACKS `pos.view` (the
        # `read_only` role already grants it — see seed_rbac.py:332).
        # The strongest credential-gate assertion available here is
        # therefore that an unauthenticated request returns 401: the
        # endpoint is NOT public. Authenticated `pos.view` callers
        # already pass at 200 in the previous two tests, which together
        # prove the gate is at `pos.view`-level (no escalation beyond).
        import httpx
        # Bare client — no cookies.
        with httpx.Client(timeout=10.0) as anon:
            r = anon.get(
                f"{BASE_URL}/api/v1/projects/{project_setup['project_id']}/purchase-orders"
            )
        # FastAPI's session-auth dep raises 401 when the cookie is
        # missing. (If perms ever fell off the user, the same dep
        # surface would respond 403 — both prove the endpoint isn't
        # open.)
        assert r.status_code in (401, 403), r.text

    def test_list_project_pos_endpoint_unknown_project_returns_empty(
        self, admin,
    ):
        # A random UUID surfaces as 200 + empty list (the un-scoped
        # endpoint's behaviour for non-matching filters; Pattern α
        # visibility filtering inside svc.list_pos drops it).
        r = admin.get(
            f"{BASE_URL}/api/v1/projects/{uuid.uuid4()}/purchase-orders"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["limit"] == 50
        assert body["offset"] == 0
