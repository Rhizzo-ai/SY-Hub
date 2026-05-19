"""Chat 23 Build Pack A — R3.9b provisional sale-price allocation tests.

Verifies the backend serializer emits `_allocated_sale_price_provisional`
on every budget_line returned by GET /budgets/{id} for users with
`budgets.view_sensitive`, and OMITS the field for users without.

Allocation = `appraisal.gdv_total / len(lines)` rounded to 2dp. The
Build Pack §R3.9b calls this v1 provisional; a Future_Tasks entry
tracks the weighted-allocation upgrade.

R3.9b acceptance cases:
  - admin sees the field on every line; pm (no sensitive perm) does not.
  - greenfield: appraisal with no gdv_total => field omitted for everyone.
  - zero lines => no allocation (n/a, no error).
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

import pytest
import requests
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
NON_SENSITIVE_EMAIL = "test-readonly@example.test"  # has budgets.view, NOT view_sensitive


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
def readonly_user(engine):
    return login_with_auto_enroll(None, BASE_URL, NON_SENSITIVE_EMAIL, PWD)


@pytest.fixture(scope="module")
def budget_with_gdv(engine):
    """Build project → appraisal (gdv_total=1,000,000) → Draft budget
    with 4 lines. Returns the budget_id. Teardown removes the chain."""
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        user_id = c.execute(text(
            "SELECT id FROM users WHERE email=:e"
        ), {"e": ADMIN_EMAIL}).scalar()
        cc_ids = c.execute(text(
            "SELECT id FROM cost_codes ORDER BY code LIMIT 4"
        )).scalars().all()
        if not (entity_id and user_id and len(cc_ids) >= 4):
            pytest.skip("seed not present (need ≥4 cost codes)")
        cc_ids = [str(x) for x in cc_ids]

        project_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO projects (
                id, project_code, name, primary_entity_id, project_type,
                land_ownership_method, status, tenure, current_stage,
                stage_entered_at, site_address, site_postcode,
                implementation_required, created_by_user_id
            ) VALUES (
                :id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                'Active', 'Freehold', 'Lead', NOW(),
                '1 R3.9b Way', 'SY1 4BB', false, :u
            )
        """), {"id": project_id, "code": f"R39B-{project_id[:6]}",
               "name": f"R3.9b {project_id[:6]}",
               "ent": entity_id, "u": user_id})

        appraisal_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number, gdv_total
            ) VALUES (
                :id, :pid, 'R3.9b Base', CURRENT_DATE,
                :uid, :gid, 'Base', true, 'Approved', 1, 1000000
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
                :id, :pid, :ap, 1, 'v1', true, 'Draft', NOW(),
                0, 0, 0, 0, 0, 0, 0, NOW(), :u
            )
        """), {"id": budget_id, "pid": project_id, "ap": appraisal_id,
               "u": user_id})

        for i in range(4):
            c.execute(text("""
                INSERT INTO budget_lines (
                    id, budget_id, cost_code_id, entity_id,
                    line_description, original_budget, approved_changes,
                    current_budget, ftc_method, forecast_to_complete,
                    actuals_to_date, committed_value, invoiced_against_commitment,
                    committed_not_invoiced, forecast_final_cost,
                    variance_value, variance_pct, variance_status,
                    is_locked, requires_attention, display_order
                ) VALUES (
                    :id, :b, :cc, :ent, :desc, 100, 0, 100,
                    'Budget_Remaining', 100, 0, 0, 0, 0, 100, 0, 0, 'Green',
                    false, false, :ord
                )
            """), {
                "id": str(uuid.uuid4()), "b": budget_id,
                "cc": cc_ids[i], "ent": entity_id, "desc": f"Line {i}",
                "ord": i,
            })

    yield {"budget_id": budget_id, "project_id": project_id,
           "appraisal_id": appraisal_id}

    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM budget_line_items
            WHERE budget_line_id IN (
                SELECT id FROM budget_lines WHERE budget_id=:b
            )
        """), {"b": budget_id})
        c.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                  {"b": budget_id})
        c.execute(text("DELETE FROM budgets WHERE id=:b"), {"b": budget_id})
        c.execute(text("DELETE FROM appraisals WHERE id=:a"),
                  {"a": appraisal_id})
        c.execute(text("DELETE FROM projects WHERE id=:p"),
                  {"p": project_id})


class TestProvisionalAllocation:
    def test_admin_sees_field_per_line_equal_split(
        self, admin, budget_with_gdv,
    ):
        r = admin.get(f"{BASE_URL}/api/v1/budgets/{budget_with_gdv['budget_id']}")
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["lines"]) == 4
        for line in body["lines"]:
            # 1,000,000 / 4 lines = 250,000.00 each.
            assert line.get("_allocated_sale_price_provisional") == "250000.00", (
                f"line missing or wrong allocation: {line.get('_allocated_sale_price_provisional')!r}"
            )

    def test_non_sensitive_user_does_not_see_field(
        self, readonly_user, budget_with_gdv,
    ):
        r = readonly_user.get(
            f"{BASE_URL}/api/v1/budgets/{budget_with_gdv['budget_id']}"
        )
        assert r.status_code == 200, r.text
        body = r.json()
        for line in body["lines"]:
            assert "_allocated_sale_price_provisional" not in line, (
                "test-readonly lacks budgets.view_sensitive — field must be omitted"
            )

    def test_appraisal_without_gdv_omits_field(
        self, admin, engine, budget_with_gdv,
    ):
        # Temporarily zero out gdv_total on the source appraisal (the
        # column is NOT NULL so we use 0, which the helper treats the
        # same as NULL — both omit the field).
        with engine.begin() as c:
            c.execute(text(
                "UPDATE appraisals SET gdv_total=0 WHERE id=:a"
            ), {"a": budget_with_gdv["appraisal_id"]})
        try:
            r = admin.get(
                f"{BASE_URL}/api/v1/budgets/{budget_with_gdv['budget_id']}"
            )
            assert r.status_code == 200
            for line in r.json()["lines"]:
                assert "_allocated_sale_price_provisional" not in line, (
                    "GDV=0 -> field must be omitted"
                )
        finally:
            with engine.begin() as c:
                c.execute(text(
                    "UPDATE appraisals SET gdv_total=1000000 WHERE id=:a"
                ), {"a": budget_with_gdv["appraisal_id"]})

    def test_helper_is_idempotent_on_repeat_call(
        self, admin, budget_with_gdv,
    ):
        # Two GETs in a row must produce identical allocations — guards
        # against the helper accidentally mutating SQLAlchemy state.
        r1 = admin.get(
            f"{BASE_URL}/api/v1/budgets/{budget_with_gdv['budget_id']}"
        ).json()
        r2 = admin.get(
            f"{BASE_URL}/api/v1/budgets/{budget_with_gdv['budget_id']}"
        ).json()
        a1 = [line["_allocated_sale_price_provisional"] for line in r1["lines"]]
        a2 = [line["_allocated_sale_price_provisional"] for line in r2["lines"]]
        assert a1 == a2 == ["250000.00"] * 4
