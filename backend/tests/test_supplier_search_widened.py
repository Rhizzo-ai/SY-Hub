"""Chat 41 §R-eyeball-Step2B Part 1 (Prompt 2.7-FE-revision) — widened
`q` filter on GET /api/v1/suppliers.

Behavioural contract: the single search box now matches across
name, trade (joined trades.name), trading_name, contact_name, and
notes — case-insensitive, partial (contains). The existing
supplier_type filter + include_archived flag still AND with the search.

Test users:
  - test-admin@example.test  — super_admin (all perms)
"""
from __future__ import annotations

import os
import uuid

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


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def admin():
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture
def _wipe_between(engine):
    """Drop test-owned supplier rows + their audit before each test so
    the search assertions can pin the result set tightly."""
    yield
    with engine.begin() as c:
        c.execute(text(
            "DELETE FROM supplier_documents WHERE supplier_id IN "
            "(SELECT id FROM suppliers WHERE name LIKE 'SrchQ-%')"
        ))
        c.execute(text(
            "DELETE FROM suppliers WHERE name LIKE 'SrchQ-%'"
        ))
        c.execute(text(
            "DELETE FROM trades WHERE name LIKE 'SrchQ-%'"
        ))


def _names(items):
    return sorted(s["name"] for s in items)


# ---------------------------------------------------------------------------
# Widened search — each field matches independently
# ---------------------------------------------------------------------------

class TestSearchAcrossFields:
    def test_q_matches_on_trade_name(self, admin, _wipe_between):
        # Two contacts share the trade; a third has no trade.
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-A", "trade": "SrchQ-Electrician",
        })
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-B", "trade": "SrchQ-Electrician",
        })
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-C", "trade": "SrchQ-Plumber",
        })
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": "Electrician"},
        )
        assert r.status_code == 200, r.text
        out = r.json()["items"]
        hit_names = {s["name"] for s in out}
        assert "SrchQ-A" in hit_names
        assert "SrchQ-B" in hit_names
        assert "SrchQ-C" not in hit_names

    def test_q_matches_on_trading_name(self, admin, _wipe_between):
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-Hidden",
            "trading_name": "SrchQ-PublicTradingName",
        })
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-Other",
        })
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": "PublicTradingName"},
        )
        assert r.status_code == 200
        names = {s["name"] for s in r.json()["items"]}
        assert "SrchQ-Hidden" in names
        assert "SrchQ-Other" not in names

    def test_q_matches_on_contact_name(self, admin, _wipe_between):
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-OrgAlpha",
            "contact_name": "SrchQ-Yolanda",
        })
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-OrgBeta",
            "contact_name": "SrchQ-Steve",
        })
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": "Yolanda"},
        )
        assert r.status_code == 200
        names = {s["name"] for s in r.json()["items"]}
        assert "SrchQ-OrgAlpha" in names
        assert "SrchQ-OrgBeta" not in names

    def test_q_matches_on_notes(self, admin, _wipe_between):
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-Notable",
            "notes": "Preferred for SrchQ-Brickwork. Site call 0800.",
        })
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-Silent",
        })
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": "Brickwork"},
        )
        assert r.status_code == 200
        names = {s["name"] for s in r.json()["items"]}
        assert "SrchQ-Notable" in names
        assert "SrchQ-Silent" not in names

    def test_q_is_case_insensitive_across_all_fields(self, admin, _wipe_between):
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-Z", "trade": "SrchQ-Roofing",
            "trading_name": "Roofers Anonymous",
            "contact_name": "Pat", "notes": "Roof inspections quarterly.",
        })
        for needle in ("roofing", "ROOFING", "RoOfInG"):
            r = admin.get(
                f"{BASE_URL}/api/v1/suppliers",
                params={"q": needle},
            )
            assert r.status_code == 200, r.text
            names = {s["name"] for s in r.json()["items"]}
            assert "SrchQ-Z" in names, (
                f"case-insensitive search failed for needle={needle!r}"
            )


# ---------------------------------------------------------------------------
# Search composes with the supplier_type filter (AND, not OR)
# ---------------------------------------------------------------------------

class TestSearchComposesWithTypeFilter:
    def test_q_hit_of_wrong_type_is_excluded(self, admin, _wipe_between):
        # Two contacts share the trade name but differ in supplier_type.
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-Sub1",
            "supplier_type": "Contractor",
            "trade": "SrchQ-Carpentry",
        })
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-Sup1",
            "supplier_type": "Supplier",
            "trade": "SrchQ-Carpentry",
        })

        # Without the filter both match.
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": "Carpentry"},
        )
        assert r.status_code == 200
        unfiltered = {s["name"] for s in r.json()["items"]}
        assert {"SrchQ-Sub1", "SrchQ-Sup1"} <= unfiltered

        # With supplier_type=Contractor only the Contractor row matches.
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": "Carpentry", "supplier_type": "Contractor"},
        )
        assert r.status_code == 200
        filtered = {s["name"] for s in r.json()["items"]}
        assert "SrchQ-Sub1" in filtered
        assert "SrchQ-Sup1" not in filtered

    def test_q_still_matches_name_after_widening(self, admin, _wipe_between):
        """Regression — the original name-match behaviour must survive."""
        admin.post(f"{BASE_URL}/api/v1/suppliers", json={
            "name": "SrchQ-AcmeOriginal",
        })
        r = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": "AcmeOriginal"},
        )
        assert r.status_code == 200
        names = {s["name"] for s in r.json()["items"]}
        assert "SrchQ-AcmeOriginal" in names
