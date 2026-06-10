"""B88 Pack 1 §7.1 — Section (group) CRUD + two-tier hierarchy + RBAC.

Covers the permission matrix on every NEW or RE-POINTED section
endpoint plus the hierarchy validation rules:

  * POST /cost-code-sections                 → cost_codes.create
  * PATCH /cost-code-sections/{id}           → cost_codes.edit
    (re-pointed from .admin in Gate 3)
  * DELETE /cost-code-sections/{id}          → cost_codes.delete
  * GET /cost-code-sections?tree=true        → cost_codes.view (nested)

Counter-intuitive grants verified:
  - super_admin has all three; director + finance have create + edit
    only; PM + readonly have none of the writes.
  - DIRECTOR DOES NOT HAVE DELETE — see test_director_cannot_delete_*.

Hierarchy rules verified:
  - allows_subgroups=true is required on the parent for any child.
  - max two tiers (tier-3 subgroup-of-subgroup forbidden).
  - allows_subgroups cannot turn on while raw cost codes are attached.
  - Self-reference forbidden on PATCH parent_section_id.

Naming requirement (Build Pack §7) — file is named exactly
`test_cost_code_sections.py`. Do not consolidate.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll, plain_login

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
    with eng.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-admin@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-director@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-finance@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def pm(db_engine):
    return plain_login(BASE_URL, "test-pm@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return plain_login(BASE_URL, "test-readonly@example.test", TEST_PASSWORD)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _uniq_code(prefix: str = "T") -> str:
    """Two-tier section codes are String(30) with a uniqueness constraint."""
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _create_section_payload(**overrides) -> dict:
    base = {
        "code": _uniq_code(),
        "name": "Test Section",
        "display_order": 9999,
        "is_direct_cost": True,
        "default_p_and_l_category": "COS",
        "parent_section_id": None,
        "allows_subgroups": False,
    }
    base.update(overrides)
    return base


def _cleanup_section(db_engine, section_id: str) -> None:
    with db_engine.begin() as c:
        c.execute(text("DELETE FROM cost_code_sections WHERE id = :i"),
                  {"i": section_id})


# --------------------------------------------------------------------------
# 1. CREATE — permission matrix
# --------------------------------------------------------------------------

def test_admin_can_create_section(admin, db_engine):
    r = admin.post(f"{BASE_URL}/api/cost-code-sections",
                   json=_create_section_payload())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["is_subgroup"] is False
    assert body["allows_subgroups"] is False
    assert body["parent_section_id"] is None
    _cleanup_section(db_engine, body["id"])


def test_director_can_create_section(director, db_engine):
    """Director has cost_codes.create via ALL-minus-exclusions."""
    r = director.post(f"{BASE_URL}/api/cost-code-sections",
                      json=_create_section_payload())
    assert r.status_code == 201, r.text
    _cleanup_section(db_engine, r.json()["id"])


def test_finance_can_create_section(finance, db_engine):
    """Finance was explicitly added to cost_codes.create in Gate 2."""
    r = finance.post(f"{BASE_URL}/api/cost-code-sections",
                     json=_create_section_payload())
    assert r.status_code == 201, r.text
    _cleanup_section(db_engine, r.json()["id"])


def test_pm_cannot_create_section(pm):
    r = pm.post(f"{BASE_URL}/api/cost-code-sections",
                json=_create_section_payload())
    assert r.status_code == 403


def test_readonly_cannot_create_section(readonly):
    r = readonly.post(f"{BASE_URL}/api/cost-code-sections",
                      json=_create_section_payload())
    assert r.status_code == 403


# --------------------------------------------------------------------------
# 2. EDIT — permission matrix
# --------------------------------------------------------------------------

def test_admin_can_edit_section(admin, db_engine):
    r = admin.post(f"{BASE_URL}/api/cost-code-sections",
                   json=_create_section_payload())
    sec_id = r.json()["id"]
    r2 = admin.patch(f"{BASE_URL}/api/cost-code-sections/{sec_id}",
                     json={"name": "Renamed"})
    assert r2.status_code == 200
    assert r2.json()["name"] == "Renamed"
    _cleanup_section(db_engine, sec_id)


def test_director_can_edit_section(admin, director, db_engine):
    """Re-pointed from .admin to .edit — director must still pass."""
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = director.patch(f"{BASE_URL}/api/cost-code-sections/{sec_id}",
                       json={"display_order": 8888})
    assert r.status_code == 200, r.text
    _cleanup_section(db_engine, sec_id)


def test_finance_can_edit_section(admin, finance, db_engine):
    """Finance was added cost_codes.edit in Gate 2."""
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = finance.patch(f"{BASE_URL}/api/cost-code-sections/{sec_id}",
                      json={"name": "Finance renamed"})
    assert r.status_code == 200, r.text
    _cleanup_section(db_engine, sec_id)


def test_pm_cannot_edit_section(admin, pm, db_engine):
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = pm.patch(f"{BASE_URL}/api/cost-code-sections/{sec_id}",
                 json={"name": "Should fail"})
    assert r.status_code == 403
    _cleanup_section(db_engine, sec_id)


# --------------------------------------------------------------------------
# 3. DELETE — permission matrix (THE counter-intuitive one)
# --------------------------------------------------------------------------

def test_admin_can_delete_empty_section(admin):
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = admin.delete(f"{BASE_URL}/api/cost-code-sections/{sec_id}")
    assert r.status_code == 204, r.text


def test_director_cannot_delete_section(admin, director, db_engine):
    """Build Pack §4.2 counter-intuitive grant — director was
    explicitly excluded from cost_codes.delete in Gate 2 even
    though it inherits create + edit via ALL-minus-exclusions."""
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = director.delete(f"{BASE_URL}/api/cost-code-sections/{sec_id}")
    assert r.status_code == 403, (
        f"Expected 403 (director excluded from cost_codes.delete) but "
        f"got {r.status_code}: {r.text}"
    )
    _cleanup_section(db_engine, sec_id)


def test_finance_cannot_delete_section(admin, finance, db_engine):
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = finance.delete(f"{BASE_URL}/api/cost-code-sections/{sec_id}")
    assert r.status_code == 403
    _cleanup_section(db_engine, sec_id)


def test_pm_cannot_delete_section(admin, pm, db_engine):
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = pm.delete(f"{BASE_URL}/api/cost-code-sections/{sec_id}")
    assert r.status_code == 403
    _cleanup_section(db_engine, sec_id)


# --------------------------------------------------------------------------
# 4. Hierarchy rules (the two-tier constraint)
# --------------------------------------------------------------------------

def test_create_subgroup_under_allows_subgroups_parent(admin, db_engine):
    """Happy path: parent with allows_subgroups=true accepts a child."""
    parent_id = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(allows_subgroups=True),
    ).json()["id"]
    child = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(parent_section_id=parent_id),
    )
    assert child.status_code == 201, child.text
    body = child.json()
    assert body["parent_section_id"] == parent_id
    assert body["is_subgroup"] is True
    assert body["allows_subgroups"] is False
    _cleanup_section(db_engine, body["id"])
    _cleanup_section(db_engine, parent_id)


def test_cannot_create_subgroup_under_non_allows_parent(admin, db_engine):
    """Sad path: parent has allows_subgroups=false → 422."""
    parent_id = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(allows_subgroups=False),
    ).json()["id"]
    r = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(parent_section_id=parent_id),
    )
    assert r.status_code == 422
    assert "allows_subgroups" in r.text.lower() or "host subgroups" in r.text.lower()
    _cleanup_section(db_engine, parent_id)


def test_cannot_create_tier3_subgroup(admin, db_engine):
    """Forbidden: subgroup under a subgroup (would create a 3-tier tree)."""
    parent_id = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(allows_subgroups=True),
    ).json()["id"]
    sub_id = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(parent_section_id=parent_id),
    ).json()["id"]
    # Now attempt grand-child under sub.
    r = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(parent_section_id=sub_id),
    )
    assert r.status_code == 422
    assert "two tiers" in r.text.lower() or "subgroup" in r.text.lower()
    _cleanup_section(db_engine, sub_id)
    _cleanup_section(db_engine, parent_id)


def test_subgroup_cannot_itself_allow_subgroups(admin, db_engine):
    """Belt-and-braces: can't create a row that is both child and parent."""
    parent_id = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(allows_subgroups=True),
    ).json()["id"]
    r = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(
            parent_section_id=parent_id, allows_subgroups=True
        ),
    )
    assert r.status_code == 422
    _cleanup_section(db_engine, parent_id)


def test_cannot_self_reference_parent(admin, db_engine):
    sec_id = admin.post(f"{BASE_URL}/api/cost-code-sections",
                        json=_create_section_payload()).json()["id"]
    r = admin.patch(
        f"{BASE_URL}/api/cost-code-sections/{sec_id}",
        json={"parent_section_id": sec_id},
    )
    assert r.status_code == 422
    _cleanup_section(db_engine, sec_id)


def test_unknown_parent_id_rejected(admin, db_engine):
    bogus = str(uuid.uuid4())
    r = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(parent_section_id=bogus),
    )
    assert r.status_code == 422
    assert "does not reference" in r.text.lower() or "not found" in r.text.lower()


# --------------------------------------------------------------------------
# 5. GET /cost-code-sections?tree=true — nested response
# --------------------------------------------------------------------------

def test_tree_endpoint_returns_nested_subgroups(admin, db_engine):
    parent_id = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(allows_subgroups=True),
    ).json()["id"]
    child_id = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json=_create_section_payload(parent_section_id=parent_id),
    ).json()["id"]

    flat = admin.get(f"{BASE_URL}/api/cost-code-sections").json()
    # Flat view: contains both rows.
    ids = {row["id"] for row in flat}
    assert parent_id in ids and child_id in ids

    tree = admin.get(f"{BASE_URL}/api/cost-code-sections?tree=true").json()
    # Tree view: only tier-1 parents at the top; our child is nested in
    # its parent's subgroups.
    tree_ids = {row["id"] for row in tree}
    assert parent_id in tree_ids
    assert child_id not in tree_ids
    parent_row = next(r for r in tree if r["id"] == parent_id)
    sub_ids = {s["id"] for s in parent_row["subgroups"]}
    assert child_id in sub_ids

    _cleanup_section(db_engine, child_id)
    _cleanup_section(db_engine, parent_id)


# --------------------------------------------------------------------------
# 6. allows_subgroups cannot turn on while raw codes attached
# --------------------------------------------------------------------------

def test_cannot_enable_allows_subgroups_with_attached_codes(
    admin, db_engine,
):
    """If a section already has cost codes attached, you can't flip it to
    allows_subgroups=true — the codes would be "stranded" under a
    parent-that-hosts-subgroups, breaking the §3.2 filing rule."""
    sec = admin.post(f"{BASE_URL}/api/cost-code-sections",
                     json=_create_section_payload()).json()
    sec_id = sec["id"]
    # Attach a cost code to it directly via DB to avoid the API's
    # prefix-sequence uniqueness machinery (and to keep this test focused).
    # QQQ prefix is reserved for this single test so it never collides
    # with the ZZ* probe prefixes used in test_cost_code_delete_guard.py.
    code_id = str(uuid.uuid4())
    with db_engine.begin() as c:
        c.execute(text("""
            INSERT INTO cost_codes (
              id, code, prefix, sequence, section_id, name,
              default_entity, vat_treatment,
              applies_to_parent, applies_to_spv, applies_to_construction_co,
              is_vattable, is_cis_applicable, is_retention_applicable,
              is_capitalisable, status, display_order,
              created_at, updated_at
            ) VALUES (
              :id, 'QQQ-99', 'QQQ', 99, :sid, 'attached probe',
              'SPV', 'Standard',
              false, true, true,
              false, false, false, false, 'Active', 9999,
              now(), now()
            )
            ON CONFLICT (prefix, sequence) DO NOTHING
        """), {"id": code_id, "sid": sec_id})
        # If our INSERT was a no-op (already exists from a prior run),
        # find the existing row and reuse it.
        existing = c.execute(text(
            "SELECT id FROM cost_codes WHERE prefix='QQQ' AND sequence=99"
        )).scalar()
        if existing:
            code_id = str(existing)
            c.execute(text(
                "UPDATE cost_codes SET section_id = :sid WHERE id = :cid"
            ), {"sid": sec_id, "cid": code_id})

    try:
        r = admin.patch(
            f"{BASE_URL}/api/cost-code-sections/{sec_id}",
            json={"allows_subgroups": True},
        )
        assert r.status_code == 409
        assert "allows_subgroups" in r.text.lower() or "cost codes" in r.text.lower()
    finally:
        with db_engine.begin() as c:
            c.execute(text("DELETE FROM cost_codes WHERE id = :i"),
                      {"i": code_id})
        _cleanup_section(db_engine, sec_id)


# --------------------------------------------------------------------------
# 7. Duplicate section code → 409
# --------------------------------------------------------------------------

def test_duplicate_section_code_rejected(admin, db_engine):
    code = _uniq_code()
    a = admin.post(f"{BASE_URL}/api/cost-code-sections",
                   json=_create_section_payload(code=code))
    assert a.status_code == 201
    b = admin.post(f"{BASE_URL}/api/cost-code-sections",
                   json=_create_section_payload(code=code))
    assert b.status_code == 409
    _cleanup_section(db_engine, a.json()["id"])
