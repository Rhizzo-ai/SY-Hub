"""Chat 41 §R5 (Prompt 2.7-BE-rev-A) — trades router + grow-as-you-type tests.

Acceptance gates: trades CRUD per §R4.1, idempotent case-insensitive
create per §R3.1, permission gating per §R5.

Test users (re-uses the same fixture pattern as test_suppliers.py):
  - test-admin@example.test     — super_admin (trades.view + trades.create)
  - test-pm@example.test        — project_manager (mirrors super_admin
                                  for trades — has both)
  - test-readonly@example.test  — read_only (trades.view but NOT
                                  trades.create)
  - test-site@example.test      — site_manager (trades.view but NOT
                                  trades.create)
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
PM_EMAIL = "test-pm@example.test"
RO_EMAIL = "test-readonly@example.test"
SITE_EMAIL = "test-site@example.test"


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


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


@pytest.fixture(scope="module", autouse=True)
def _wipe_module(engine):
    """Clean trade + supplier rows owned by this module's test users."""
    with engine.begin() as c:
        # Suppliers reference trades via trade_id (ON DELETE SET NULL), but
        # clean both to keep listings deterministic.
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
        c.execute(text("""
            DELETE FROM trades
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
    yield
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
        c.execute(text("""
            DELETE FROM trades
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))


@pytest.fixture
def _wipe_between(engine):
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
        c.execute(text("""
            DELETE FROM trades
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
    yield


@pytest.fixture(scope="module")
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(engine):
    return login_with_auto_enroll(None, BASE_URL, RO_EMAIL, PWD)


@pytest.fixture(scope="module")
def site(engine):
    return login_with_auto_enroll(None, BASE_URL, SITE_EMAIL, PWD)


# ---------------------------------------------------------------------------
# CRUD basics
# ---------------------------------------------------------------------------

class TestTradesCreate:
    def test_create_trade_returns_201_with_audit(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        name = f"Groundworks-{sx}"
        r = admin.post(f"{BASE_URL}/api/v1/trades", json={"name": name})
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["name"] == name
        assert out["is_archived"] is False
        assert "id" in out and out["id"]

        # Audit row landed.
        with engine.connect() as c:
            rows = c.execute(text("""
                SELECT action FROM audit_log
                 WHERE resource_type='trade' AND resource_id=:rid
            """), {"rid": out["id"]}).all()
        actions = [r[0] for r in rows]
        assert "Create" in actions

    def test_whitespace_is_normalised(
        self, admin, engine, _wipe_between,
    ):
        """Leading/trailing + collapsed internal whitespace."""
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"   Heavy   Plant  -{sx}   "},
        )
        assert r.status_code == 201, r.text
        assert r.json()["name"] == f"Heavy Plant -{sx}"

    def test_empty_name_returns_422(self, admin, engine, _wipe_between):
        # Pydantic min_length=1 rejects empty before the service.
        r = admin.post(f"{BASE_URL}/api/v1/trades", json={"name": ""})
        assert r.status_code == 422, r.text

    def test_whitespace_only_name_returns_422(
        self, admin, engine, _wipe_between,
    ):
        """A purely-whitespace name slips past Pydantic (length 1+) but
        the service normaliser collapses it to '' and raises ValueError.
        """
        r = admin.post(f"{BASE_URL}/api/v1/trades", json={"name": "   "})
        assert r.status_code == 422, r.text


class TestTradesIdempotent:
    def test_case_insensitive_re_create_returns_same_id(
        self, admin, engine, _wipe_between,
    ):
        """Chat 41 §R3.1 — typed name resolves to the existing row
        regardless of case. No duplicate audit row.
        """
        sx = _suffix()
        first = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Electrical-{sx}"},
        )
        assert first.status_code == 201
        tid = first.json()["id"]

        # Re-create with different casing + extra whitespace.
        second = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"  electrical-{sx}  "},
        )
        assert second.status_code == 201
        assert second.json()["id"] == tid

        # Audit log carries exactly one Create row for this resource.
        with engine.connect() as c:
            n = c.execute(text("""
                SELECT count(*) FROM audit_log
                 WHERE resource_type='trade' AND resource_id=:rid
                   AND action='Create'
            """), {"rid": tid}).scalar()
        assert n == 1, f"expected exactly one Create audit row, got {n}"


class TestTradesList:
    def test_list_excludes_archived_by_default(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        a = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Active-{sx}"},
        ).json()
        b = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Archived-{sx}"},
        ).json()
        admin.post(f"{BASE_URL}/api/v1/trades/{b['id']}/archive")

        r = admin.get(f"{BASE_URL}/api/v1/trades", params={"q": sx})
        names = {item["name"] for item in r.json()["items"]}
        assert a["name"] in names
        assert b["name"] not in names

        r2 = admin.get(
            f"{BASE_URL}/api/v1/trades",
            params={"q": sx, "include_archived": "true"},
        )
        names2 = {item["name"] for item in r2.json()["items"]}
        assert a["name"] in names2
        assert b["name"] in names2

    def test_search_is_case_insensitive_substring(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        admin.post(f"{BASE_URL}/api/v1/trades", json={"name": f"Bricklayer-{sx}"})
        admin.post(f"{BASE_URL}/api/v1/trades", json={"name": f"Carpenter-{sx}"})

        r = admin.get(
            f"{BASE_URL}/api/v1/trades",
            params={"q": f"bricklayer-{sx.lower()}"},
        )
        names = {item["name"] for item in r.json()["items"]}
        assert f"Bricklayer-{sx}" in names
        assert f"Carpenter-{sx}" not in names


class TestTradesArchiveLifecycle:
    def test_archive_unarchive_idempotent(self, admin, engine, _wipe_between):
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Cyclic-{sx}"},
        )
        tid = r.json()["id"]

        ra = admin.post(f"{BASE_URL}/api/v1/trades/{tid}/archive")
        assert ra.status_code == 200 and ra.json()["is_archived"] is True

        # second archive is a no-op (no new audit row).
        ra2 = admin.post(f"{BASE_URL}/api/v1/trades/{tid}/archive")
        assert ra2.status_code == 200

        ru = admin.post(f"{BASE_URL}/api/v1/trades/{tid}/unarchive")
        assert ru.status_code == 200 and ru.json()["is_archived"] is False

        with engine.connect() as c:
            actions = [r[0] for r in c.execute(text("""
                SELECT action FROM audit_log
                 WHERE resource_type='trade' AND resource_id=:rid
                 ORDER BY created_at
            """), {"rid": tid}).all()]
        assert actions == ["Create", "Archive", "Restore"], actions


# ---------------------------------------------------------------------------
# Permission gating
# ---------------------------------------------------------------------------

class TestTradesPermissions:
    def test_read_only_can_view_but_not_create(
        self, readonly, engine, _wipe_between,
    ):
        # Can list.
        r = readonly.get(f"{BASE_URL}/api/v1/trades")
        assert r.status_code == 200, r.text

        # Cannot create.
        r2 = readonly.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Forbidden-{_suffix()}"},
        )
        assert r2.status_code == 403, r2.text

    def test_site_manager_can_view_but_not_create(
        self, site, engine, _wipe_between,
    ):
        r = site.get(f"{BASE_URL}/api/v1/trades")
        assert r.status_code == 200, r.text

        r2 = site.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"SiteForbidden-{_suffix()}"},
        )
        assert r2.status_code == 403, r2.text

    def test_pm_can_create(self, pm, engine, _wipe_between):
        r = pm.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"PMTrade-{_suffix()}"},
        )
        assert r.status_code == 201, r.text


# ---------------------------------------------------------------------------
# Archive does NOT cascade to supplier.trade_id (§R3.1 NOTE)
# ---------------------------------------------------------------------------

class TestArchiveDoesNotClearSupplierTradeId:
    def test_supplier_trade_id_survives_trade_archive(
        self, admin, engine, _wipe_between,
    ):
        """Archiving a trade leaves existing supplier.trade_id intact.

        Per §R3.1 NOTE: ON DELETE SET NULL fires only on hard-delete (we
        don't expose that). Archived trades just stop appearing in pick
        lists.
        """
        sx = _suffix()
        # 1) Create a trade.
        rt = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Stay-{sx}"},
        )
        tid = rt.json()["id"]

        # 2) Create a supplier pointing at that trade.
        rs = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"WithTrade-{sx}", "trade_id": tid},
        )
        sid = rs.json()["id"]
        assert rs.json()["trade_id"] == tid

        # 3) Archive the trade.
        admin.post(f"{BASE_URL}/api/v1/trades/{tid}/archive")

        # 4) Supplier still references the (now-archived) trade.
        r = admin.get(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert r.json()["trade_id"] == tid
