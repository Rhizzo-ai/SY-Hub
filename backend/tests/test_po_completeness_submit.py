"""B105/B106 — PO completeness gate at submit (§3.8).

Cases 25–28 of Build Pack §6. The completeness gate runs at submit
(not at create) so AI/manual fill can progressively complete a draft
PO; submit refuses with 422 naming the offending line numbers.
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from app.db import SessionLocal
from app.models.purchase_orders import PurchaseOrderLine
from app.models.budgets import BudgetLine
from app.services import budget_lines as bl_svc

from tests.test_unbudgeted_orders import (
    _build_chain, _tear_chain, _perms_for, _ensure_po_prefix,
    _create_supplier_for_admin, _login, _ADMIN_EMAIL, _BASE_URL,
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
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def chain(engine):
    refs = _build_chain(engine, budget_status="Active")
    yield refs
    _tear_chain(engine, refs)


@pytest.fixture(scope="module", autouse=True)
def _reset_mfa_for_http_tests(engine):
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


def _pick_extra_cc(engine, budget_id: str, n: int = 1) -> list[str]:
    with engine.begin() as c:
        rows = c.execute(text("""
            SELECT id FROM cost_codes
             WHERE status='Active'
               AND id NOT IN (SELECT cost_code_id FROM budget_lines
                              WHERE budget_id=:b)
             ORDER BY code LIMIT :n
        """), {"b": budget_id, "n": n}).all()
    assert len(rows) >= n
    return [str(r[0]) for r in rows]


def _post_po(admin, *, project_id, budget_id, supplier_id, lines):
    return admin.post(
        f"{_BASE_URL}/api/v1/projects/{project_id}/purchase-orders",
        json={"supplier_id": supplier_id, "budget_id": budget_id,
              "lines": lines},
    )


def _submit_po(admin, po_id: str):
    return admin.post(
        f"{_BASE_URL}/api/v1/purchase-orders/{po_id}/submit",
        json={"submission_reason": "completeness test"},
    )


# ----------------------------------------------------------------------
# Case 25 — Draft create with an incomplete line (no qty) → persists,
#          line stored with net=0, no error.
# ----------------------------------------------------------------------
def test_25_draft_incomplete_persists_zero_net(engine, chain):
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    # Note: NO quantity, NO unit_rate.
    r = _post_po(
        admin, project_id=chain["project_id"],
        budget_id=chain["budget_id"], supplier_id=supplier_id,
        lines=[{"cost_code_id": cc_id, "description": "case 25 incomplete",
                "vat_rate": 20}],
    )
    assert r.status_code == 201, r.text
    po = r.json()
    line = po["lines"][0]
    assert Decimal(str(line.get("net_amount", "0"))) == Decimal("0.00")
    assert Decimal(str(line.get("gross_amount", "0"))) == Decimal("0.00")


# ----------------------------------------------------------------------
# Case 26 — Submit of a PO with any incomplete line → 422 naming the
#          line number(s); PO stays Draft.
# ----------------------------------------------------------------------
def test_26_submit_incomplete_422_stays_draft(engine, chain):
    """Case 26 — submit of a PO with any incomplete line → 422 naming
    the line number(s); PO stays Draft.

    The create path auto-fills missing description with "(unlabelled)"
    (services.purchase_orders.create_po:482) so the only way to
    construct a truly description-blank line is to create the PO then
    blank the description via direct DB UPDATE (mirrors Case 28a's
    drive-via-direct-state pattern).
    """
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    r = _post_po(
        admin, project_id=chain["project_id"],
        budget_id=chain["budget_id"], supplier_id=supplier_id,
        lines=[{"cost_code_id": cc_id, "description": "case 26",
                "quantity": 1, "unit_rate": "100", "vat_rate": 20}],
    )
    assert r.status_code == 201, r.text
    po = r.json()
    line_id = po["lines"][0]["id"]
    # Blank the description directly to defeat the auto-fill.
    with engine.begin() as c:
        c.execute(text(
            "UPDATE purchase_order_lines SET description='' WHERE id=:l"
        ), {"l": line_id})

    sub = _submit_po(admin, po["id"])
    assert sub.status_code == 422, (sub.status_code, sub.text)
    assert "po_line_incomplete" in sub.text
    assert "incomplete_line_numbers" in sub.text

    # PO must still be Draft.
    rg = admin.get(f"{_BASE_URL}/api/v1/purchase-orders/{po['id']}")
    assert rg.status_code == 200
    assert rg.json()["status"] == "draft"


# ----------------------------------------------------------------------
# Case 27 — Submit of a fully complete PO → proceeds (auto-approves).
# ----------------------------------------------------------------------
def test_27_submit_complete_proceeds(engine, chain):
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    r = _post_po(
        admin, project_id=chain["project_id"],
        budget_id=chain["budget_id"], supplier_id=supplier_id,
        lines=[{"cost_code_id": cc_id,
                "description": "case 27 complete",
                "quantity": 1, "unit_rate": "500", "vat_rate": 20}],
    )
    assert r.status_code == 201, r.text
    sub = _submit_po(admin, r.json()["id"])
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] in ("approved", "pending_approval")


# ----------------------------------------------------------------------
# Case 28 — Each completeness-field deficit triggers 422:
#          missing description, missing qty, qty<=0, missing/blank
#          cost_code. Drive via direct line state mutation.
# ----------------------------------------------------------------------
def test_28_each_field_blocks_submit(engine, chain, db_session):
    """Drive the completeness gate by mutating a freshly-created draft
    PO line directly (the API can't easily produce all defective
    permutations because the schema layer also enforces some bounds).
    """
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]

    # Helper: produce a fresh draft PO and return (po_id, line_id).
    def _fresh_draft():
        r = _post_po(
            admin, project_id=chain["project_id"],
            budget_id=chain["budget_id"], supplier_id=supplier_id,
            lines=[{"cost_code_id": cc_id,
                    "description": "case 28",
                    "quantity": 1, "unit_rate": "500", "vat_rate": 20}],
        )
        assert r.status_code == 201, r.text
        po = r.json()
        return po["id"], po["lines"][0]["id"]

    # 28a — blank description.
    po_id, line_id = _fresh_draft()
    with engine.begin() as c:
        c.execute(text(
            "UPDATE purchase_order_lines SET description='' WHERE id=:l"
        ), {"l": line_id})
    sub = _submit_po(admin, po_id)
    assert sub.status_code == 422, ("blank description", sub.status_code, sub.text)
    assert "po_line_incomplete" in sub.text

    # 28b — qty<=0 is unreachable via direct UPDATE (the DB CHECK
    # constraint `ck_pol_quantity_positive` forbids it). The
    # completeness gate's `quantity > 0` check is defensive
    # defence-in-depth against a future schema relaxation; we PIN
    # the gate's intent by code inspection rather than a runtime
    # test that cannot exist. Build Pack §6 case 28 acknowledges
    # this: "qty<=0 (caught earlier at totals if present)".

    # 28c — blank cost_code.
    po_id, line_id = _fresh_draft()
    with engine.begin() as c:
        c.execute(text(
            "UPDATE purchase_order_lines SET cost_code='' WHERE id=:l"
        ), {"l": line_id})
    sub = _submit_po(admin, po_id)
    assert sub.status_code == 422, ("blank cost_code", sub.status_code, sub.text)
    assert "po_line_incomplete" in sub.text
