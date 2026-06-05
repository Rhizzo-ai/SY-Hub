"""Chat 41 §R5 (Prompt 2.7-BE-rev-A) — supplier contact-book reshape tests.

Focused on the rev-A integration surface for suppliers:
  - `_resolve_trade` priority + `_UNSET` sentinel (trade_id wins over
    trade-name; explicit null clears; absent key leaves untouched).
  - Serialised shape: no `cis_subtype` / `default_vat_rate` /
    `vat_registered` keys (the last dropped in 0041 per Chat 41 §R-
    eyeball-Step2A); always has `trade`, `trade_id` (joined trade name
    is null-safe).

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


# ---------------------------------------------------------------------------
# Serialised shape
# ---------------------------------------------------------------------------

class TestSerialisedShape:
    def test_supplier_response_has_rev_a_keys_not_dropped(
        self, admin, engine, _wipe_between,
    ):
        """The rev-A shape: trade + trade_id present; cis_subtype +
        default_vat_rate + vat_registered (dropped in 0041) absent.
        """
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Shape-{sx}"},
        )
        assert r.status_code == 201, r.text
        out = r.json()
        # Present
        for k in ("trade", "trade_id"):
            assert k in out, f"expected {k!r} in response, got {sorted(out)}"
        # Absent — Chat 41 §R-eyeball-Step2A drops vat_registered.
        for k in ("cis_subtype", "default_vat_rate", "vat_registered"):
            assert k not in out, f"{k!r} must be dropped from response"
        # Sensible defaults.
        assert out["trade"] is None
        assert out["trade_id"] is None


# ---------------------------------------------------------------------------
# _resolve_trade priority + _UNSET sentinel
# ---------------------------------------------------------------------------

class TestResolveTradePriority:
    def test_create_with_trade_id_resolves_to_existing_row(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        tid = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Plumbing-{sx}"},
        ).json()["id"]

        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"WithTID-{sx}", "trade_id": tid},
        )
        assert r.status_code == 201
        out = r.json()
        assert out["trade_id"] == tid
        assert out["trade"] == f"Plumbing-{sx}"

    def test_create_with_trade_name_grows_as_you_type(
        self, admin, engine, _wipe_between,
    ):
        """Chat 41 §R3.1 — typing a name that doesn't exist creates the
        trade on the fly.
        """
        sx = _suffix()
        trade_name = f"NewTrade-{sx}"
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"WithTName-{sx}", "trade": trade_name},
        )
        assert r.status_code == 201
        out = r.json()
        assert out["trade"] == trade_name
        assert out["trade_id"]  # non-null

        # The trade now exists in /api/v1/trades.
        rt = admin.get(
            f"{BASE_URL}/api/v1/trades",
            params={"q": trade_name},
        )
        names = {item["name"] for item in rt.json()["items"]}
        assert trade_name in names

    def test_create_trade_id_wins_over_trade_name(
        self, admin, engine, _wipe_between,
    ):
        """Both keys present: trade_id wins (per §R3.2 priority order)."""
        sx = _suffix()
        winner = admin.post(
            f"{BASE_URL}/api/v1/trades",
            json={"name": f"Winner-{sx}"},
        ).json()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"Both-{sx}",
                "trade_id": winner["id"],
                "trade": f"Loser-{sx}",
            },
        )
        assert r.status_code == 201
        assert r.json()["trade_id"] == winner["id"]
        assert r.json()["trade"] == winner["name"]

    def test_create_with_bad_trade_id_returns_422(
        self, admin, engine, _wipe_between,
    ):
        """trade_id pointing at a non-existent UUID → 422."""
        sx = _suffix()
        bogus = str(uuid.uuid4())
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"BadTID-{sx}", "trade_id": bogus},
        )
        assert r.status_code == 422, r.text
        assert "not found" in r.json()["detail"].lower()

    def test_patch_explicit_null_clears_trade(
        self, admin, engine, _wipe_between,
    ):
        """`{"trade": null}` is the explicit "clear" signal — service
        sets row.trade_id = NULL.
        """
        sx = _suffix()
        tid = admin.post(
            f"{BASE_URL}/api/v1/trades", json={"name": f"Drop-{sx}"},
        ).json()["id"]
        sid = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Clearable-{sx}", "trade_id": tid},
        ).json()["id"]

        r = admin.patch(
            f"{BASE_URL}/api/v1/suppliers/{sid}",
            json={"trade": None},
        )
        assert r.status_code == 200
        assert r.json()["trade_id"] is None
        assert r.json()["trade"] is None

    def test_patch_absent_key_leaves_trade_untouched(
        self, admin, engine, _wipe_between,
    ):
        """No `trade` / `trade_id` key in body → `_UNSET` → no change."""
        sx = _suffix()
        tid = admin.post(
            f"{BASE_URL}/api/v1/trades", json={"name": f"Hold-{sx}"},
        ).json()["id"]
        sid = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Hold-{sx}", "trade_id": tid},
        ).json()["id"]

        r = admin.patch(
            f"{BASE_URL}/api/v1/suppliers/{sid}",
            json={"trading_name": "TN"},  # no trade key
        )
        assert r.status_code == 200
        assert r.json()["trade_id"] == tid

    def test_patch_swap_to_new_trade_id(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        a = admin.post(
            f"{BASE_URL}/api/v1/trades", json={"name": f"A-{sx}"},
        ).json()
        b = admin.post(
            f"{BASE_URL}/api/v1/trades", json={"name": f"B-{sx}"},
        ).json()
        sid = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Swap-{sx}", "trade_id": a["id"]},
        ).json()["id"]

        r = admin.patch(
            f"{BASE_URL}/api/v1/suppliers/{sid}",
            json={"trade_id": b["id"]},
        )
        assert r.status_code == 200
        assert r.json()["trade_id"] == b["id"]
        assert r.json()["trade"] == b["name"]
