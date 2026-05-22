"""Chat 24 §R4 (Prompt 2.5) — PO Receipts integration tests.

Live-DB tests (require Postgres + a running uvicorn). Cover:

  - Receipt CRUD (3):
    R4.1 create receipt against issued PO → 201 with serialised body
    R4.2 list receipts under a PO returns inserted row
    R4.3 get receipt returns lines + photos

  - Quantity invariants (3):
    R4.4 partial qty → PO becomes 'partially_receipted'
    R4.5 cumulative across two receipts ≤ ordered → ok
    R4.6 cumulative > ordered → 422 po/receipt-exceeds-ordered

  - Status transitions (3):
    R4.7 fully receipting every line → PO becomes 'receipted'
    R4.8 deleting the only receipt rolls PO back to 'issued'
    R4.9 deleting one of two receipts rolls 'receipted' → 'partially_receipted'

  - Date gating (3):
    R4.10 future received_date → 422 po/receipt-future-date
    R4.11 31-day backdate as site_manager → 403 po/receipt-backdate-forbidden
    R4.12 31-day backdate as director (pos.edit_issued) → 201

  - Auth / role gating (3):
    R4.13 site_manager can create a receipt (pos.receipt)
    R4.14 read_only cannot create (403 missing pos.receipt)
    R4.15 director can edit/delete; site_manager cannot

  - Photos (2):
    R4.16 photos persisted alongside the receipt
    R4.17 duplicate file_path within a single receipt → 422

  - Commitment invariant (2):
    R4.18 budget_line.committed_value unchanged across receipt create+full
    R4.19 budget_line.committed_value unchanged across receipt delete

  - Wrong-state guard (1):
    R4.20 receipt against draft PO → 409 po/receipt-wrong-status

  - Audit (1):
    R4.21 receipt write emits an audit_log row with action='Receipt'
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
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
SITE_EMAIL = "test-site@example.test"
READONLY_EMAIL = "test-readonly@example.test"
PM_EMAIL = "test-pm@example.test"


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
def site_manager(engine):
    try:
        return login_with_auto_enroll(None, BASE_URL, SITE_EMAIL, PWD)
    except Exception:
        pytest.skip("test-site@example.test not seeded")


@pytest.fixture(scope="module")
def readonly(engine):
    try:
        return login_with_auto_enroll(None, BASE_URL, READONLY_EMAIL, PWD)
    except Exception:
        pytest.skip("test-readonly@example.test not seeded")


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
        "name": f"Chat24-R4 Project {suffix}",
        "project_type": "Pure_Dev",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Receipt Lane",
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
        json={"name": f"R4-Supplier {name_suffix}", "default_vat_rate": 20.0},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _seed_budget_lines(engine, project_id: str, line_budgets: list[float]):
    """Insert an Approved appraisal + Active budget + N budget_lines.
    Returns (budget_id, [line_ids]).
    """
    with engine.begin() as c:
        ent_id = c.execute(text("""
            SELECT primary_entity_id FROM projects WHERE id = :pid
        """), {"pid": project_id}).scalar()
        ccs = c.execute(text("""
            SELECT id, code FROM cost_codes
            WHERE status = 'Active' ORDER BY code LIMIT :n
        """), {"n": len(line_budgets)}).all()
        admin_id = c.execute(text("""
            SELECT id FROM users WHERE email = :em
        """), {"em": ADMIN_EMAIL}).scalar()
        app_id = c.execute(text("""
            INSERT INTO appraisals (
                project_id, version_number, name, reference_date,
                status, created_by_user_id,
                land_purchase_price, sdlt_category, developer_relief,
                contingency_pct, target_profit_on_cost_pct,
                target_profit_on_gdv_pct, project_duration_months,
                appraisal_group_id, is_current, scenario
            ) VALUES (
                :pid, 1, 'R4 test appraisal', CURRENT_DATE,
                'Approved', :uid, 0, 'Residential_Standard', false,
                5, 20, 17, 18, gen_random_uuid(), true, 'Base'
            )
            RETURNING id
        """), {"pid": project_id, "uid": admin_id}).scalar()
        budget_id = c.execute(text("""
            INSERT INTO budgets (
                project_id, source_appraisal_id, version_number,
                version_label, is_current, status, created_by_user_id
            ) VALUES (:pid, :aid, 1, 'Original', true, 'Active', :uid)
            RETURNING id
        """), {"pid": project_id, "aid": app_id, "uid": admin_id}).scalar()
        line_ids = []
        for i, b in enumerate(line_budgets):
            line_ids.append(str(c.execute(text("""
                INSERT INTO budget_lines (
                    budget_id, cost_code_id, line_description, entity_id,
                    original_budget, current_budget,
                    ftc_method, display_order
                ) VALUES (:bid, :ccid, :desc, :eid, :amt, :amt,
                          'Budget_Remaining', :ord)
                RETURNING id
            """), {
                "bid": budget_id, "ccid": ccs[i].id,
                "desc": f"Line {i+1}", "eid": ent_id, "amt": b, "ord": i,
            }).scalar()))
    return str(budget_id), line_ids


def _create_po_with_lines(
    admin, engine, project_id: str, supplier_id: str,
    budget_id: str, budget_line_ids: list[str],
    line_quantities: list[int],
) -> str:
    """Create a draft PO with one line per budget_line. Returns po_id."""
    lines = []
    for i, (blid, q) in enumerate(zip(budget_line_ids, line_quantities)):
        lines.append({
            "budget_line_id": blid,
            "description": f"R4 line {i+1}",
            "quantity": q,
            "unit_rate": 100,
            "vat_rate": 20,
        })
    body = {
        "supplier_id": supplier_id, "budget_id": budget_id, "lines": lines,
    }
    r = admin.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/purchase-orders",
        json=body,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _submit_and_issue(admin, engine, po_id: str) -> None:
    """Walk PO from draft → issued.

    R7.0 Option B: within-budget submit now lands at `approved` (not
    `issued`). The fallback explicit-issue branch below handles this —
    the helper is therefore already R7.0-correct without changes.
    """
    r = admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit", json={})
    assert r.status_code == 200, r.text
    with engine.connect() as c:
        status = c.execute(
            text("SELECT status FROM purchase_orders WHERE id=:i"),
            {"i": po_id},
        ).scalar()
    if status != "issued":
        # Fallback: explicit issue path. Under R7.0 this is the ONLY
        # path to issued for the within-budget auto-approve flow.
        r2 = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}/issue", json={},
        )
        assert r2.status_code == 200, r2.text


@pytest.fixture
def issued_po(admin, engine):
    """A fresh project + Active budget + 2 budget_lines + 1 issued PO
    with two lines (qty 10 each, £100 each → £2400 gross total)."""
    eid = _entity_id(engine, ADMIN_EMAIL)
    project_id = _create_project(admin, eid)
    budget_id, line_ids = _seed_budget_lines(engine, project_id, [5000.0, 5000.0])
    supplier_id = _create_supplier(admin, uuid.uuid4().hex[:6].upper())
    po_id = _create_po_with_lines(
        admin, engine, project_id, supplier_id, budget_id, line_ids,
        line_quantities=[10, 10],
    )
    _submit_and_issue(admin, engine, po_id)
    # Get PO line ids in order.
    with engine.connect() as c:
        po_line_rows = c.execute(text("""
            SELECT id, budget_line_id, quantity
            FROM purchase_order_lines
            WHERE purchase_order_id=:p ORDER BY line_number
        """), {"p": po_id}).all()
    po_line_ids = [str(r.id) for r in po_line_rows]
    yield {
        "project_id": project_id, "supplier_id": supplier_id,
        "budget_id": budget_id, "budget_line_ids": line_ids,
        "po_id": po_id, "po_line_ids": po_line_ids,
    }
    with engine.begin() as c:
        c.execute(text("DELETE FROM purchase_order_receipts WHERE purchase_order_id=:p"),
                  {"p": po_id})
        c.execute(text("DELETE FROM purchase_order_approvals WHERE purchase_order_id=:p"),
                  {"p": po_id})
        c.execute(text("DELETE FROM purchase_orders WHERE id=:p"), {"p": po_id})
        c.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                  {"p": project_id})
        c.execute(text("DELETE FROM appraisals WHERE project_id=:p"),
                  {"p": project_id})
        c.execute(text("DELETE FROM projects WHERE id=:p"), {"p": project_id})
        c.execute(text("DELETE FROM suppliers WHERE id=:s"),
                  {"s": supplier_id})


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


# ─────────────────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────────────────

class TestReceiptCRUD:
    def test_create_receipt_returns_201(self, admin, issued_po):
        body = {
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 4}],
        }
        r = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts",
            json=body,
        )
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["purchase_order_id"] == issued_po["po_id"]
        assert len(out["lines"]) == 1
        assert Decimal(out["lines"][0]["quantity_received"]) == Decimal("4")

    def test_list_receipts_returns_inserted(self, admin, issued_po):
        body = {
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 3}],
        }
        admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts",
            json=body,
        )
        r = admin.get(
            f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts",
        )
        assert r.status_code == 200
        data = r.json()
        assert data["total"] >= 1

    def test_get_receipt_returns_lines_and_photos(self, admin, issued_po):
        body = {
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 2}],
            "photos": [{
                "file_path": f"/uploads/r4/{uuid.uuid4().hex}.jpg",
                "file_type": "image/jpeg",
                "file_size_bytes": 1234,
                "original_filename": "proof.jpg",
                "caption": "delivery 2026-02-20",
            }],
        }
        r = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts",
            json=body,
        )
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        r2 = admin.get(f"{BASE_URL}/api/v1/receipts/{rid}")
        assert r2.status_code == 200
        out = r2.json()
        assert len(out["photos"]) == 1
        assert out["photos"][0]["original_filename"] == "proof.jpg"


# ─────────────────────────────────────────────────────────────────────────
# Quantity invariants
# ─────────────────────────────────────────────────────────────────────────

class TestQuantityInvariants:
    def test_partial_flips_po_to_partially_receipted(self, admin, issued_po, engine):
        body = {
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 4}],
        }
        r = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts",
            json=body,
        )
        assert r.status_code == 201
        with engine.connect() as c:
            status = c.execute(
                text("SELECT status FROM purchase_orders WHERE id=:i"),
                {"i": issued_po["po_id"]},
            ).scalar()
        assert status == "partially_receipted"

    def test_cumulative_under_ordered_ok(self, admin, issued_po):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 4}],
        })
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 5}],
        })
        assert r.status_code == 201, r.text

    def test_cumulative_over_ordered_rejected(self, admin, issued_po):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 9}],
        })
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 2}],  # 9+2=11 > 10
        })
        assert r.status_code == 422
        detail = r.json()["detail"]
        assert isinstance(detail, dict)
        assert detail["code"] == "po/receipt-exceeds-ordered"


# ─────────────────────────────────────────────────────────────────────────
# Status transitions
# ─────────────────────────────────────────────────────────────────────────

class TestStatusTransitions:
    def test_full_receipt_flips_po_to_receipted(self, admin, issued_po, engine):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [
                {"po_line_id": issued_po["po_line_ids"][0],
                 "quantity_received": 10},
                {"po_line_id": issued_po["po_line_ids"][1],
                 "quantity_received": 10},
            ],
        })
        assert r.status_code == 201, r.text
        with engine.connect() as c:
            status = c.execute(
                text("SELECT status FROM purchase_orders WHERE id=:i"),
                {"i": issued_po["po_id"]},
            ).scalar()
        assert status == "receipted"

    def test_delete_only_receipt_rolls_back_to_issued(self, admin, issued_po, engine):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 3}],
        })
        rid = r.json()["id"]
        admin.delete(f"{BASE_URL}/api/v1/receipts/{rid}")
        with engine.connect() as c:
            status = c.execute(
                text("SELECT status FROM purchase_orders WHERE id=:i"),
                {"i": issued_po["po_id"]},
            ).scalar()
        assert status == "issued"

    def test_delete_one_of_two_receipts_rolls_receipted_to_partial(
        self, admin, issued_po, engine,
    ):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r1 = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 10}],
        })
        r2 = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][1],
                       "quantity_received": 10}],
        })
        assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
        # Now PO is 'receipted'. Delete the second receipt.
        admin.delete(f"{BASE_URL}/api/v1/receipts/{r2.json()['id']}")
        with engine.connect() as c:
            status = c.execute(
                text("SELECT status FROM purchase_orders WHERE id=:i"),
                {"i": issued_po["po_id"]},
            ).scalar()
        assert status == "partially_receipted"


# ─────────────────────────────────────────────────────────────────────────
# Date gating
# ─────────────────────────────────────────────────────────────────────────

class TestDateGating:
    def test_future_date_rejected(self, admin, issued_po):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        future = (datetime.now(timezone.utc).date()
                  + timedelta(days=2)).isoformat()
        r = admin.post(url, json={
            "received_date": future,
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
        })
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "po/receipt-future-date"

    def test_31_days_back_as_site_manager_forbidden(
        self, admin, site_manager, issued_po,
    ):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        backdate = (datetime.now(timezone.utc).date()
                    - timedelta(days=31)).isoformat()
        r = site_manager.post(url, json={
            "received_date": backdate,
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
        })
        # site_manager has pos.receipt but not pos.edit_issued.
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "po/receipt-backdate-forbidden"

    def test_31_days_back_as_director_ok(self, admin, issued_po):
        # admin has the director-tier permissions.
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        backdate = (datetime.now(timezone.utc).date()
                    - timedelta(days=31)).isoformat()
        r = admin.post(url, json={
            "received_date": backdate,
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
        })
        assert r.status_code == 201, r.text


# ─────────────────────────────────────────────────────────────────────────
# Auth / role gating
# ─────────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_site_manager_can_create_receipt(
        self, admin, site_manager, issued_po,
    ):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = site_manager.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 2}],
        })
        assert r.status_code == 201, r.text

    def test_readonly_cannot_create(self, admin, readonly, issued_po):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = readonly.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
        })
        assert r.status_code == 403
        assert "pos.receipt" in r.text

    def test_director_can_edit_receipt_site_manager_cannot(
        self, admin, site_manager, issued_po,
    ):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
        })
        rid = r.json()["id"]
        # site_manager: forbidden
        r2 = site_manager.patch(
            f"{BASE_URL}/api/v1/receipts/{rid}",
            json={"notes": "site edit"},
        )
        assert r2.status_code == 403
        # admin: ok
        r3 = admin.patch(
            f"{BASE_URL}/api/v1/receipts/{rid}",
            json={"notes": "director edit"},
        )
        assert r3.status_code == 200, r3.text
        assert r3.json()["notes"] == "director edit"


# ─────────────────────────────────────────────────────────────────────────
# Photos
# ─────────────────────────────────────────────────────────────────────────

class TestPhotos:
    def test_photos_persisted(self, admin, issued_po):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
            "photos": [
                {"file_path": f"/u/{uuid.uuid4().hex}.jpg",
                 "file_type": "image/jpeg",
                 "file_size_bytes": 200,
                 "original_filename": "a.jpg"},
                {"file_path": f"/u/{uuid.uuid4().hex}.jpg",
                 "file_type": "image/jpeg",
                 "file_size_bytes": 300,
                 "original_filename": "b.jpg"},
            ],
        })
        assert r.status_code == 201, r.text
        assert len(r.json()["photos"]) == 2

    def test_duplicate_file_path_in_payload_rejected(self, admin, issued_po):
        path = f"/u/{uuid.uuid4().hex}.jpg"
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
            "photos": [
                {"file_path": path, "file_type": "image/jpeg",
                 "file_size_bytes": 200, "original_filename": "a.jpg"},
                {"file_path": path, "file_type": "image/jpeg",
                 "file_size_bytes": 300, "original_filename": "b.jpg"},
            ],
        })
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "po/receipt-photo-duplicate"


# ─────────────────────────────────────────────────────────────────────────
# Commitment invariant — the heart of the R3↔R4 contract
# ─────────────────────────────────────────────────────────────────────────

class TestCommitmentInvariant:
    def _commitment_for_pol(self, engine, po_line_id: str) -> Decimal:
        with engine.connect() as c:
            bl_id = c.execute(text("""
                SELECT budget_line_id FROM purchase_order_lines WHERE id=:i
            """), {"i": po_line_id}).scalar()
            return Decimal(str(c.execute(text("""
                SELECT committed_value FROM budget_lines WHERE id=:i
            """), {"i": str(bl_id)}).scalar() or 0))

    def test_committed_value_unchanged_across_full_receipt(
        self, admin, issued_po, engine,
    ):
        pol = issued_po["po_line_ids"][0]
        before = self._commitment_for_pol(engine, pol)
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": pol, "quantity_received": 10}],
        })
        assert r.status_code == 201
        after = self._commitment_for_pol(engine, pol)
        assert before == after, f"commitment changed: {before} -> {after}"

    def test_committed_value_unchanged_across_delete(
        self, admin, issued_po, engine,
    ):
        pol = issued_po["po_line_ids"][0]
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": pol, "quantity_received": 3}],
        })
        before = self._commitment_for_pol(engine, pol)
        admin.delete(f"{BASE_URL}/api/v1/receipts/{r.json()['id']}")
        after = self._commitment_for_pol(engine, pol)
        assert before == after, f"commitment changed: {before} -> {after}"


# ─────────────────────────────────────────────────────────────────────────
# Wrong-state guard
# ─────────────────────────────────────────────────────────────────────────

class TestWrongState:
    def test_receipt_against_draft_po_rejected(self, admin, engine):
        eid = _entity_id(engine, ADMIN_EMAIL)
        project_id = _create_project(admin, eid)
        budget_id, line_ids = _seed_budget_lines(engine, project_id, [5000.0])
        supplier_id = _create_supplier(admin, uuid.uuid4().hex[:6].upper())
        try:
            po_id = _create_po_with_lines(
                admin, engine, project_id, supplier_id, budget_id, line_ids,
                line_quantities=[5],
            )
            with engine.connect() as c:
                po_line_id = c.execute(text("""
                    SELECT id FROM purchase_order_lines
                    WHERE purchase_order_id=:p ORDER BY line_number LIMIT 1
                """), {"p": po_id}).scalar()
            url = f"{BASE_URL}/api/v1/purchase-orders/{po_id}/receipts"
            r = admin.post(url, json={
                "received_date": _today(),
                "lines": [{"po_line_id": str(po_line_id),
                           "quantity_received": 1}],
            })
            assert r.status_code == 409
            assert r.json()["detail"]["code"] == "po/receipt-wrong-status"
        finally:
            with engine.begin() as c:
                c.execute(text("DELETE FROM purchase_orders WHERE id=:p"),
                          {"p": po_id})
                c.execute(text("DELETE FROM budgets WHERE project_id=:p"),
                          {"p": project_id})
                c.execute(text("DELETE FROM appraisals WHERE project_id=:p"),
                          {"p": project_id})
                c.execute(text("DELETE FROM projects WHERE id=:p"),
                          {"p": project_id})
                c.execute(text("DELETE FROM suppliers WHERE id=:s"),
                          {"s": supplier_id})


# ─────────────────────────────────────────────────────────────────────────
# Audit
# ─────────────────────────────────────────────────────────────────────────

class TestAudit:
    def test_receipt_emits_audit_row(self, admin, issued_po, engine):
        url = f"{BASE_URL}/api/v1/purchase-orders/{issued_po['po_id']}/receipts"
        r = admin.post(url, json={
            "received_date": _today(),
            "lines": [{"po_line_id": issued_po["po_line_ids"][0],
                       "quantity_received": 1}],
        })
        assert r.status_code == 201, r.text
        rid = r.json()["id"]
        with engine.connect() as c:
            n = c.execute(text("""
                SELECT count(*) FROM audit_log
                WHERE action='Receipt'
                  AND resource_type='purchase_order_receipt'
                  AND resource_id=:i
            """), {"i": rid}).scalar()
        assert n == 1, f"expected 1 Receipt audit row, got {n}"
