"""Shared helpers for the 2.6 BCR test suite (split across
`test_budget_changes_migration.py`, `test_budget_changes_service.py`,
`test_budget_changes_api.py`, and `test_permissions_2_6.py`).

NB. This module name starts with `_` so pytest does NOT collect it as a
test file. Pure Python — fixtures live in the individual test files
(pytest only auto-discovers fixtures in `conftest.py` and in test
modules themselves).
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy import text


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


def wipe(engine) -> None:
    """Module-scoped wipe of all BCR + budget + appraisal + project state.

    Mirrors the chat-31 `tests/test_budgets.py` wipe pattern + extends
    with `budget_change_lines` + `budget_changes`.
    """
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


def wipe_budgets_only(engine, project_id) -> None:
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


def make_approved_appraisal(admin_session, project_id):
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


def make_active_budget(
    admin_session, db_engine, project_id, *,
    line_count: int = 3,
    line_amount: Decimal = Decimal("100000.00"),
    contingency_line_index=None,
):
    """Create a Draft budget, then replace its lines with a known set of
    `line_count` lines (optionally flagging one as is_contingency), then
    activate. Returns the activated budget dict.

    Caller must have already set the budget self-approval threshold high
    enough to allow activate (£999m+).
    """
    wipe_budgets_only(db_engine, project_id)
    aid = make_approved_appraisal(admin_session, project_id)
    r = admin_session.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/budgets/from-appraisal",
        json={"source_appraisal_id": aid},
    )
    assert r.status_code == 201, r.text
    budget = r.json()
    bid = budget["id"]

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
        for i in range(line_count):
            new_id = uuid.uuid4()
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
    ra = admin_session.post(f"{BASE_URL}/api/v1/budgets/{bid}/activate")
    assert ra.status_code == 200, ra.text
    out = ra.json()
    out["lines"] = sorted(out["lines"], key=lambda x: x.get("display_order", 0))
    return out


def create_transfer(session, budget, *, title="T", amount="2000.00"):
    """Helper: create a 2-line Transfer BCR between budget.lines[0] and [1]."""
    l1, l2 = (ln["id"] for ln in budget["lines"][:2])
    import requests  # noqa: F401  (kept for typing clarity)
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
