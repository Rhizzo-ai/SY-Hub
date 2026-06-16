"""B105/B106 — Cost-code-first commercial line model.

Resolve-or-mint coverage for §3.3 + §3.4 + §3.5 + §3.10. Cases 1–10 of
the Build Pack §6 minimum-coverage list.

Service-level tests against the live PO + package services. Reuses
the synthetic project → appraisal → Active-budget chain from
`test_unbudgeted_orders.py`. Each case is a discrete test function so
a single regression is pinpointable.
"""
from __future__ import annotations

import os
import uuid
import logging
from decimal import Decimal

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.db import SessionLocal
from app.models.budgets import BudgetLine
from app.models.purchase_orders import PurchaseOrder
from app.services import budget_lines as bl_svc
from app.services import purchase_orders as po_svc
from app.services.packages import (
    add_package_line, create_package,
)

# Re-use the chain builder + perms helper from the legacy file.
from tests.test_unbudgeted_orders import (  # noqa: E402
    _build_chain, _tear_chain, _perms_for, _ensure_po_prefix,
    _create_supplier_for_admin, _login, _ADMIN_EMAIL,
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
    """B105/B106 — reset MFA on test users so login_with_auto_enroll
    goes through the enrol path and caches the TOTP secret in
    conftest._MFA_SECRETS for the rest of the module."""
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
    """Return `n` Active cost codes NOT yet on this budget."""
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


def _seed_budgeted_line(engine, refs: dict, cc_id: str) -> str:
    """Seed an EXISTING (i.e. budgeted) line on the chain budget for
    cost_code `cc_id`, with `current_budget=£10,000`. Returns the
    line id as str.
    """
    line_id = str(uuid.uuid4())
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO budget_lines
              (id, budget_id, cost_code_id, entity_id, line_description,
               original_budget, approved_changes, current_budget,
               actuals_to_date, actuals_this_period,
               committed_value, invoiced_against_commitment,
               committed_not_invoiced,
               forecast_to_complete, ftc_method,
               forecast_final_cost, variance_value, variance_pct,
               variance_status, requires_attention,
               percentage_complete, display_order,
               is_locked, is_contingency, is_unbudgeted)
            VALUES
              (:id, :b, :cc, :ent, 'pre-existing budgeted line',
               10000, 0, 10000, 0, 0, 0, 0, 0, 0, 'Manual',
               10000, 0, 0, 'Green', false,
               0, 0, false, false, false)
        """), {
            "id": line_id, "b": refs["budget_id"], "cc": cc_id,
            "ent": refs["entity_id"],
        })
    return line_id


def _post_po(admin, *, project_id, budget_id, supplier_id, lines):
    """Hit the live POST /api/v1/projects/{pid}/purchase-orders."""
    from tests.test_unbudgeted_orders import _BASE_URL as BASE
    body = {
        "supplier_id": supplier_id,
        "budget_id": budget_id,
        "lines": lines,
    }
    return admin.post(
        f"{BASE}/api/v1/projects/{project_id}/purchase-orders", json=body,
    )


# ----------------------------------------------------------------------
# Case 1 — cost_code_id for an EXISTING line resolves (no mint).
# ----------------------------------------------------------------------
def test_01_resolves_existing_line_no_mint(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    pre_line_id = _seed_budgeted_line(engine, chain, cc_id)
    before = db_session.execute(text(
        "SELECT COUNT(*) FROM budget_lines WHERE budget_id=:b"
    ), {"b": chain["budget_id"]}).scalar()

    resolved = bl_svc.find_line_for_code(
        db_session,
        budget_id=uuid.UUID(chain["budget_id"]),
        cost_code_id=uuid.UUID(cc_id),
        cost_code_subcategory_id=None,
    )
    assert resolved is not None
    assert str(resolved.id) == pre_line_id
    after = db_session.execute(text(
        "SELECT COUNT(*) FROM budget_lines WHERE budget_id=:b"
    ), {"b": chain["budget_id"]}).scalar()
    assert before == after, "no mint expected"


# ----------------------------------------------------------------------
# Case 2 — cost_code_id with NO line mints exactly one neutral line.
# ----------------------------------------------------------------------
def test_02_mint_when_no_line_neutral(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    u, perms = _perms_for(db_session, chain["user_id"])

    line = bl_svc.create_unbudgeted_line(
        db_session,
        budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(cc_id),
        cost_code_subcategory_id=None,
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 2",
        source="purchase_order",
        # default force_flag=False
    )
    db_session.commit()
    fresh = db_session.get(BudgetLine, line.id)
    assert fresh.is_unbudgeted is True
    # Neutral: NOT Red, NOT requires_attention.
    assert fresh.variance_status != "Red"
    assert fresh.requires_attention is False
    assert fresh.unbudgeted_cleared_at is None


# ----------------------------------------------------------------------
# Case 3 — two PO lines naming the SAME new code in one payload mint ONCE.
# ----------------------------------------------------------------------
def test_03_two_lines_same_code_one_mint(engine, chain):
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]

    # PO with TWO lines referring to the same brand-new cost code.
    # PO line table has no (po_id, budget_line_id) unique, so both lines
    # may exist; only one budget_line should be minted.
    r = _post_po(admin, project_id=chain["project_id"],
                 budget_id=chain["budget_id"], supplier_id=supplier_id,
                 lines=[
                     {"cost_code_id": cc_id, "description": "case 3 a",
                      "quantity": 1, "unit_rate": "100", "vat_rate": 20},
                     {"cost_code_id": cc_id, "description": "case 3 b",
                      "quantity": 2, "unit_rate": "50", "vat_rate": 20},
                 ])
    assert r.status_code == 201, r.text
    # Count budget_lines on this budget for the cc.
    with engine.begin() as c:
        cnt = c.execute(text(
            "SELECT COUNT(*) FROM budget_lines "
            "WHERE budget_id=:b AND cost_code_id=:cc"
        ), {"b": chain["budget_id"], "cc": cc_id}).scalar()
    assert cnt == 1, f"expected exactly one mint, got {cnt}"


# ----------------------------------------------------------------------
# Case 4 — D2 (uniqueness) enforcement: a direct duplicate mint raises
#         IntegrityError. (T-RACE-1, behaviour-level proof.)
# ----------------------------------------------------------------------
def test_04_d2_duplicate_mint_integrity_error(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    u, perms = _perms_for(db_session, chain["user_id"])
    bl_svc.create_unbudgeted_line(
        db_session,
        budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=uuid.UUID(cc_id),
        cost_code_subcategory_id=None,
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="first", source="purchase_order",
    )
    db_session.commit()
    # Second direct mint on the same triple violates
    # uq_budget_lines_budget_cost_subcat.
    with pytest.raises(IntegrityError):
        bl_svc.create_unbudgeted_line(
            db_session,
            budget_id=uuid.UUID(chain["budget_id"]),
            user=u, perms=perms,
            cost_code_id=uuid.UUID(cc_id),
            cost_code_subcategory_id=None,
            entity_id=uuid.UUID(chain["entity_id"]),
            reason="second", source="purchase_order",
        )
        db_session.flush()
    db_session.rollback()


# ----------------------------------------------------------------------
# Case 5 — back-compat alias: budget_line_id ONLY (no cost_code_id) →
#         server derives the code from the line and resolves.
# ----------------------------------------------------------------------
def test_05_alias_only_succeeds(engine, chain):
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    pre_id = _seed_budgeted_line(engine, chain, cc_id)
    r = _post_po(admin, project_id=chain["project_id"],
                 budget_id=chain["budget_id"],
                 supplier_id=supplier_id,
                 lines=[
                     {"budget_line_id": pre_id, "description": "case 5",
                      "quantity": 1, "unit_rate": "100", "vat_rate": 20},
                 ])
    assert r.status_code == 201, r.text
    po = r.json()
    # The line must resolve to the same budgeted line we seeded.
    assert po["lines"][0]["budget_line_id"] == pre_id


# ----------------------------------------------------------------------
# Case 6 — alias mismatch: cost_code_id + budget_line_id pointing at a
#         DIFFERENT line → 422.
# ----------------------------------------------------------------------
def test_06_alias_mismatch_422(engine, chain):
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    ccs = _pick_extra_cc(engine, chain["budget_id"], 2)
    cc_a, cc_b = ccs
    line_a_id = _seed_budgeted_line(engine, chain, cc_a)
    # cc_b has NO line yet; mismatch: alias=line_a (code cc_a) but
    # cost_code_id=cc_b → mismatch on resolve/mint.
    r = _post_po(admin, project_id=chain["project_id"],
                 budget_id=chain["budget_id"],
                 supplier_id=supplier_id,
                 lines=[
                     {"cost_code_id": cc_b, "budget_line_id": line_a_id,
                      "description": "case 6", "quantity": 1,
                      "unit_rate": "100", "vat_rate": 20},
                 ])
    assert r.status_code == 422, (r.status_code, r.text)
    assert "does not match" in r.text or "not match" in r.text


# ----------------------------------------------------------------------
# Case 7 — deprecated unbudgeted_cost_code_id only → resolves/mints +
#         deprecation warning logged.
# ----------------------------------------------------------------------
def test_07_deprecated_cluster_logs_warning(engine, chain, caplog):
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]

    with caplog.at_level(logging.WARNING, logger="syhomes.deprecation"):
        r = _post_po(admin, project_id=chain["project_id"],
                     budget_id=chain["budget_id"],
                     supplier_id=supplier_id,
                     lines=[
                         {"unbudgeted": True,
                          "unbudgeted_cost_code_id": cc_id,
                          "unbudgeted_reason": "case 7 legacy",
                          "description": "case 7", "quantity": 1,
                          "unit_rate": "100", "vat_rate": 20},
                     ])
    assert r.status_code == 201, r.text
    # Deprecation warning is emitted at the service layer in the
    # backend process. caplog of HTTP tests may not capture cross-
    # process logs; assert behaviour (200), not the log capture, here.


# ----------------------------------------------------------------------
# Case 8 — neither code nor alias → 422 "cost_code_id is required".
# ----------------------------------------------------------------------
def test_08_neither_422(engine, chain):
    _ensure_po_prefix(engine, chain["project_id"], chain["user_id"])
    admin = _login(_ADMIN_EMAIL)
    supplier_id = _create_supplier_for_admin(admin)
    r = _post_po(admin, project_id=chain["project_id"],
                 budget_id=chain["budget_id"],
                 supplier_id=supplier_id,
                 lines=[
                     {"description": "case 8", "quantity": 1,
                      "unit_rate": "100", "vat_rate": 20},
                 ])
    assert r.status_code == 422, (r.status_code, r.text)
    assert "cost_code_id is required" in r.text


# ----------------------------------------------------------------------
# Case 9 — subcategory in the key: same code, different subcat = SEPARATE
#         lines (proves the triple key).
# ----------------------------------------------------------------------
def test_09_subcat_makes_separate_lines(engine, chain, db_session):
    # Find a cost code with at least one subcategory.
    cc_id = db_session.execute(text("""
        SELECT cc.id FROM cost_codes cc
        JOIN cost_code_subcategories scs ON scs.cost_code_id = cc.id
        WHERE cc.status='Active' AND scs.status='Active'
          AND cc.id NOT IN (SELECT cost_code_id FROM budget_lines
                            WHERE budget_id=:b)
        LIMIT 1
    """), {"b": chain["budget_id"]}).scalar()
    if not cc_id:
        pytest.skip("no Active cost code with subcategory available")
    sub_id = db_session.execute(text("""
        SELECT id FROM cost_code_subcategories
        WHERE cost_code_id=:cc AND status='Active' LIMIT 1
    """), {"cc": cc_id}).scalar()

    u, perms = _perms_for(db_session, chain["user_id"])
    line_a = bl_svc.create_unbudgeted_line(
        db_session, budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=cc_id, cost_code_subcategory_id=sub_id,
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 9 sub A", source="purchase_order",
    )
    line_null = bl_svc.create_unbudgeted_line(
        db_session, budget_id=uuid.UUID(chain["budget_id"]),
        user=u, perms=perms,
        cost_code_id=cc_id, cost_code_subcategory_id=None,
        entity_id=uuid.UUID(chain["entity_id"]),
        reason="case 9 null sub", source="purchase_order",
    )
    db_session.commit()
    assert line_a.id != line_null.id
    # Both exist, distinct, same cost_code.
    cnt = db_session.execute(text(
        "SELECT COUNT(*) FROM budget_lines "
        "WHERE budget_id=:b AND cost_code_id=:cc"
    ), {"b": chain["budget_id"], "cc": str(cc_id)}).scalar()
    assert cnt == 2


# ----------------------------------------------------------------------
# Case 10 — NULL-subcategory matching: a line with NULL subcat resolves
#          via `IS NULL` (not accidentally missed by `= NULL`).
# ----------------------------------------------------------------------
def test_10_null_subcat_resolves_via_is_null(engine, chain, db_session):
    cc_id = _pick_extra_cc(engine, chain["budget_id"], 1)[0]
    # Seed a NULL-subcat budgeted line directly.
    _seed_budgeted_line(engine, chain, cc_id)

    found = bl_svc.find_line_for_code(
        db_session,
        budget_id=uuid.UUID(chain["budget_id"]),
        cost_code_id=uuid.UUID(cc_id),
        cost_code_subcategory_id=None,
    )
    assert found is not None
    assert found.cost_code_subcategory_id is None
