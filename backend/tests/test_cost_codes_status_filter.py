"""B88 Pack 1 — Gate 5 follow-up — `GET /api/cost-codes?status=*` filter.

Regression test for the 500 caught during operator live-eyeball:
`status=All` was passed straight into a SQLAlchemy `WHERE` against the
Postgres `cost_code_status` enum (`Active`/`Retired`), which raised
`InvalidTextRepresentation` and bubbled up as a bare 500.

Backend now defines the contract (router fix in
`backend/app/routers/cost_codes.py::list_cost_codes`):

  * `status=All` / `status=all` (case-insensitive) → no filter
    (returns Active + Retired rows).
  * `status=Active` → Active only.
  * `status=Retired` → Retired only.
  * `status=<anything else>` → 422 with a clear detail message
    (NOT a 500).
  * Omitted → existing behaviour (no filter).
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll

load_dotenv("/app/backend/.env")

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
            or "http://localhost:8001")
DATABASE_URL = os.environ["DATABASE_URL"]
TEST_PASSWORD = "TestUser-Dev-2026!"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(
        None, BASE_URL, "test-admin@example.test", TEST_PASSWORD,
    )


@pytest.fixture(scope="module")
def retired_code(db_engine):
    """Seed exactly one Retired cost code so `status=All` is provably
    > `status=Active`. Idempotent — re-uses an existing Retired row if
    one is already there; cleans up at module teardown.

    Uses a high-sequence sentinel (`ZZQ-99`) under the canonical
    Accounting parent — chosen so it does NOT collide with any
    canonical prefix range and is trivially identifiable for cleanup.
    """
    seeded_id = None
    with db_engine.begin() as c:
        sec_id = c.execute(text(
            "SELECT id FROM cost_code_sections WHERE code='8'"
        )).scalar()
        existing = c.execute(text(
            "SELECT id FROM cost_codes WHERE code='ZZQ-99'"
        )).scalar()
        if existing is None:
            seeded_id = str(uuid.uuid4())
            c.execute(text("""
                INSERT INTO cost_codes (
                  id, code, prefix, sequence, name, section_id,
                  buildertrend_category, default_entity, is_vattable,
                  vat_treatment, status, display_order
                ) VALUES (
                  :id, 'ZZQ-99', 'ZZQ', 99,
                  'Status-filter regression sentinel', :sec,
                  '8 Accounting', 'Parent', true, 'Standard',
                  'Retired', 99
                )
            """), {"id": seeded_id, "sec": sec_id})
        else:
            seeded_id = str(existing)
            # Make sure it's actually Retired.
            c.execute(text(
                "UPDATE cost_codes SET status='Retired' WHERE id = :i"
            ), {"i": seeded_id})

    yield seeded_id

    # Teardown — remove the sentinel row.
    with db_engine.begin() as c:
        c.execute(text("DELETE FROM cost_codes WHERE id = :i"),
                  {"i": seeded_id})


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

class TestCostCodesStatusFilter:

    def test_status_all_returns_active_plus_retired(self, admin, retired_code):
        """status=All must include the seeded Retired row → count is
        strictly greater than the Active-only count."""
        r_all = admin.get(f"{BASE_URL}/api/cost-codes?status=All")
        r_active = admin.get(f"{BASE_URL}/api/cost-codes?status=Active")
        assert r_all.status_code == 200, r_all.text
        assert r_active.status_code == 200, r_active.text
        all_rows = r_all.json()
        active_rows = r_active.json()
        all_codes = {c["code"] for c in all_rows}
        active_codes = {c["code"] for c in active_rows}
        assert "ZZQ-99" in all_codes
        assert "ZZQ-99" not in active_codes
        assert len(all_rows) > len(active_rows)
        # The delta is exactly the Retired set (by status field).
        retired_in_all = [c for c in all_rows if c["status"] == "Retired"]
        assert len(retired_in_all) >= 1
        assert any(c["code"] == "ZZQ-99" for c in retired_in_all)

    def test_status_all_lowercase_is_case_insensitive(self, admin, retired_code):
        """status=all (lowercase) must behave identically to status=All."""
        r_upper = admin.get(f"{BASE_URL}/api/cost-codes?status=All")
        r_lower = admin.get(f"{BASE_URL}/api/cost-codes?status=all")
        assert r_upper.status_code == 200
        assert r_lower.status_code == 200
        upper_codes = sorted(c["code"] for c in r_upper.json())
        lower_codes = sorted(c["code"] for c in r_lower.json())
        assert upper_codes == lower_codes

    def test_status_active_returns_active_only(self, admin, retired_code):
        r = admin.get(f"{BASE_URL}/api/cost-codes?status=Active")
        assert r.status_code == 200
        rows = r.json()
        assert all(c["status"] == "Active" for c in rows)
        assert not any(c["code"] == "ZZQ-99" for c in rows)

    def test_status_retired_returns_retired_only(self, admin, retired_code):
        r = admin.get(f"{BASE_URL}/api/cost-codes?status=Retired")
        assert r.status_code == 200
        rows = r.json()
        assert all(c["status"] == "Retired" for c in rows)
        assert any(c["code"] == "ZZQ-99" for c in rows)

    def test_invalid_status_returns_422_not_500(self, admin, retired_code):
        """Anything not in {All/all, Active, Retired} must 422 with a
        clear detail message — never a 500 (regression for the original
        bug where status=Bogus would hit Postgres and trip
        InvalidTextRepresentation)."""
        for bad in ("Bogus", "active", "retired", "ACTIVE", "deleted", "1"):
            r = admin.get(f"{BASE_URL}/api/cost-codes?status={bad}")
            assert r.status_code == 422, (
                f"status={bad!r} → got {r.status_code}, expected 422; "
                f"body={r.text}"
            )
            body = r.json()
            assert "invalid status filter" in body["detail"], body
            assert repr(bad) in body["detail"], body

    def test_no_status_param_returns_unfiltered(self, admin, retired_code):
        """Omitting the param must NOT regress — keeps the pre-fix
        behaviour (no filter applied)."""
        r_none = admin.get(f"{BASE_URL}/api/cost-codes")
        r_all = admin.get(f"{BASE_URL}/api/cost-codes?status=All")
        assert r_none.status_code == 200
        assert r_all.status_code == 200
        assert (sorted(c["code"] for c in r_none.json())
                == sorted(c["code"] for c in r_all.json()))

    def test_status_filter_composes_with_section_id(self, admin, retired_code,
                                                     db_engine):
        """`status=All` must compose correctly with the section_id
        filter — the route's other params keep working alongside the
        new branch."""
        with db_engine.connect() as c:
            sec_id = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code='8'"
            )).scalar()
        r = admin.get(
            f"{BASE_URL}/api/cost-codes?status=All&section_id={sec_id}"
        )
        assert r.status_code == 200
        rows = r.json()
        codes = sorted(c["code"] for c in rows)
        # Canonical ACC-01..03 + the seeded retired ZZQ-99 (we
        # parked it under section "8" Accounting too).
        assert "ACC-01" in codes
        assert "ACC-02" in codes
        assert "ACC-03" in codes
        assert "ZZQ-99" in codes
