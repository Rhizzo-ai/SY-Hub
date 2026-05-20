"""Chat 24 §R1 (Prompt 2.5) — project_number_prefixes tests.

Four integration tests covering the prefix CRUD + auto-seed behaviour:
  1. Creating a new project via the API auto-seeds two null-middle
     is_default=true rows (one per entity_type).
  2. POSTing a prefix with invalid middle_shape returns 422.
  3. POSTing a second is_default=true demotes the first via the
     trg_pnp_single_default trigger.
  4. POSTing a prefix duplicating (project, entity_type, middle) returns 422.

These tests live in a single module because each needs a freshly-created
test project (cheaper than per-test project create).
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


def _get_primary_entity_id(engine, admin_email: str) -> str:
    """Find an entity in the admin's tenant to attach test projects to.

    Uses the first non-archived entity for the admin's tenant. The
    operator's seed_test_users.py guarantees at least one exists.
    """
    with engine.connect() as c:
        eid = c.execute(text("""
            SELECT e.id FROM entities e
            JOIN users u ON u.tenant_id = e.tenant_id
            WHERE u.email = :em
            ORDER BY e.created_at ASC LIMIT 1
        """), {"em": admin_email}).scalar()
    assert eid is not None, "test seed needs at least one entity in admin's tenant"
    return str(eid)


def _create_project(admin, entity_id: str) -> str:
    """Create a project via the API and return its id."""
    suffix = uuid.uuid4().hex[:8].upper()
    body = {
        "name": f"Chat24-R1 Project {suffix}",
        "project_type": "Pure_Dev",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "1 Test Lane, Test City",
        "site_postcode": "AB12 3CD",
        "tenure": "Freehold",
        "land_type": "Greenfield",
        "planning_type": "Full",
        "planning_status": "Pre_App",
        "implementation_required": True,
    }
    r = admin.post(f"{BASE_URL}/api/projects", json=body)
    assert r.status_code == 201, f"project create failed: {r.status_code} {r.text}"
    return r.json()["id"]


@pytest.fixture
def project_id(admin, engine):
    """One fresh project per test; cleaned up at teardown."""
    eid = _get_primary_entity_id(engine, ADMIN_EMAIL)
    pid = _create_project(admin, eid)
    yield pid
    with engine.begin() as c:
        # Prefix rows cascade via FK; tear down the project itself.
        c.execute(text(
            "DELETE FROM projects WHERE id = :pid"
        ), {"pid": pid})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestAutoSeed:
    def test_project_create_auto_seeds_null_middle_default_per_entity_type(
        self, admin, project_id, engine,
    ):
        """Creating a project must auto-seed two prefix rows (po + bill)."""
        r = admin.get(
            f"{BASE_URL}/api/v1/projects/{project_id}/number-prefixes"
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # Two rows total: one per entity_type, null middle, is_default=true.
        assert len(items) == 2, f"expected 2 seeded rows, got {items!r}"
        by_type = {it["entity_type"]: it for it in items}
        assert set(by_type) == {"po", "bill"}
        for et, item in by_type.items():
            assert item["middle_prefix"] is None, (
                f"{et}: middle_prefix should be NULL, got {item['middle_prefix']!r}"
            )
            assert item["is_default"] is True, (
                f"{et}: is_default should be true, got {item['is_default']!r}"
            )
            assert item["next_sequence"] == 1
            # Preview shape: "PO-0001" or "BILL-0001".
            expected = ("PO-0001" if et == "po" else "BILL-0001")
            assert item["preview_format"] == expected, (
                f"{et}: preview shape mismatch — got {item['preview_format']!r}"
            )


class TestShape:
    def test_create_prefix_with_invalid_middle_shape_returns_422(
        self, admin, project_id,
    ):
        bad_values = [
            "-AB",       # leading dash
            "AB-",       # trailing dash
            "abc",       # would be uppercased but service normalises; still ok
                         # — replace with a length-12 string to actually fail.
        ]
        # Replace 'abc' (which is valid after upper-case) with length-9 case.
        bad_values[2] = "TOOLONGXX"
        for bad in bad_values:
            r = admin.post(
                f"{BASE_URL}/api/v1/projects/{project_id}/number-prefixes",
                json={"entity_type": "po", "middle_prefix": bad},
            )
            assert r.status_code == 422, (
                f"middle={bad!r} should be rejected, got {r.status_code} {r.text}"
            )


class TestSingleDefault:
    def test_setting_is_default_demotes_others_via_trigger(
        self, admin, project_id, engine,
    ):
        # The auto-seeded null-middle row for po is currently is_default=true.
        # Create a second prefix with is_default=true → trigger should
        # demote the original.
        r = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/number-prefixes",
            json={
                "entity_type": "po",
                "middle_prefix": "HAD",
                "description": "Hadley site stream",
                "is_default": True,
            },
        )
        assert r.status_code == 201, r.text

        # Re-fetch and assert exactly one is_default=true row per entity_type.
        rg = admin.get(
            f"{BASE_URL}/api/v1/projects/{project_id}/number-prefixes",
            params={"entity_type": "po"},
        )
        items = rg.json()["items"]
        defaults = [it for it in items if it["is_default"]]
        assert len(defaults) == 1, (
            f"expected exactly one is_default=true, got {defaults}"
        )
        assert defaults[0]["middle_prefix"] == "HAD"
        # The originally-default null-middle row must now be is_default=false.
        nulls = [it for it in items if it["middle_prefix"] is None]
        assert len(nulls) == 1
        assert nulls[0]["is_default"] is False


class TestUniqueness:
    def test_duplicate_middle_in_namespace_returns_422(
        self, admin, project_id,
    ):
        # First creation — succeeds.
        body = {
            "entity_type": "po", "middle_prefix": "X1",
            "description": "First stream",
        }
        r1 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/number-prefixes",
            json=body,
        )
        assert r1.status_code == 201, r1.text

        # Duplicate — 422.
        r2 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/number-prefixes",
            json=body,
        )
        assert r2.status_code == 422, r2.text
        assert "already exists" in r2.json()["detail"].lower()

        # Same middle_prefix but DIFFERENT entity_type → succeeds (separate namespace).
        r3 = admin.post(
            f"{BASE_URL}/api/v1/projects/{project_id}/number-prefixes",
            json={"entity_type": "bill", "middle_prefix": "X1"},
        )
        assert r3.status_code == 201, r3.text
