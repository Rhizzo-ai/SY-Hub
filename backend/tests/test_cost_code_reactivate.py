"""B88 Pack 1 §7.3 — Reactivate (un-retire) mirror of /retire.

Verifies:

  * super_admin can retire then reactivate; the round-trip lands the
    code back in Active status.
  * Reactivate clears retired_at, retired_reason, AND
    replaced_by_code_id (so an incoming retire-and-replace pointer
    chain doesn't survive un-retirement).
  * Reactivate on an already-Active code → 409 (idempotency).
  * Retire on an already-Retired code → 409 (existing behaviour, asserted
    here for the round-trip symmetry).
  * Director CAN reactivate (cost_codes.edit is granted via
    ALL-minus-exclusions in Gate 2).
  * Finance CAN reactivate (cost_codes.edit explicit grant in Gate 2).
  * PM CANNOT reactivate (no cost_codes.edit).
  * Audit row gets written for both retire and reactivate transitions.

Naming requirement (Build Pack §7) — file is named exactly
`test_cost_code_reactivate.py`. Do not consolidate.
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
def section_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text("""
            SELECT id FROM cost_code_sections
            WHERE parent_section_id IS NULL AND allows_subgroups = false
            ORDER BY display_order LIMIT 1
        """)).scalar())


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _fresh_cost_code(admin, section_id: str, prefix: str = "ZZR") -> dict:
    import random
    payload = {
        "section_id": section_id,
        "name": "Reactivate probe",
        "default_entity": "SPV",
        "applies_to_parent": False,
        "applies_to_spv": True,
        "applies_to_construction_co": True,
        "vat_treatment": "Standard",
    }
    for seq in range(10, 100):
        payload["code"] = f"{prefix}-{seq:02d}"
        r = admin.post(f"{BASE_URL}/api/cost-codes", json=payload)
        if r.status_code == 201:
            return r.json()
        if r.status_code == 409:
            continue
        raise AssertionError(f"Create failed: {r.status_code} {r.text}")
    raise AssertionError("Could not allocate sequence.")


def _retire(session, code_id: str, reason: str = "probe") -> requests.Response:
    return session.post(
        f"{BASE_URL}/api/cost-codes/{code_id}/retire",
        json={"retired_reason": reason, "replaced_by_code_id": None},
    )


def _reactivate(session, code_id: str) -> requests.Response:
    return session.post(f"{BASE_URL}/api/cost-codes/{code_id}/reactivate")


# --------------------------------------------------------------------------
# Happy path round-trip
# --------------------------------------------------------------------------

def test_admin_can_retire_then_reactivate(admin, section_id, db_engine):
    code = _fresh_cost_code(admin, section_id)
    code_id = code["id"]

    r1 = _retire(admin, code_id, "operator error")
    assert r1.status_code == 200, r1.text
    assert r1.json()["status"] == "Retired"
    assert r1.json()["retired_at"] is not None

    r2 = _reactivate(admin, code_id)
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["status"] == "Active"
    assert body["retired_at"] is None
    assert body["retired_reason"] is None

    # Tidy up.
    admin.delete(f"{BASE_URL}/api/cost-codes/{code_id}")


def test_reactivate_clears_replaced_by_pointer(admin, section_id, db_engine):
    """If a code was retired with replaced_by_code_id set, reactivating
    it must clear the pointer too (otherwise the un-retired code would
    still claim to be 'replaced by' something)."""
    target = _fresh_cost_code(admin, section_id, prefix="ZZT")
    source = _fresh_cost_code(admin, section_id, prefix="ZZS")
    r = admin.post(
        f"{BASE_URL}/api/cost-codes/{source['id']}/retire",
        json={"retired_reason": "moved",
              "replaced_by_code_id": target["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["replaced_by_code_id"] == target["id"]

    r2 = _reactivate(admin, source["id"])
    assert r2.status_code == 200
    assert r2.json()["replaced_by_code_id"] is None

    # DB-level confirmation.
    with db_engine.connect() as c:
        row = c.execute(text(
            "SELECT status, retired_at, retired_reason, replaced_by_code_id "
            "FROM cost_codes WHERE id = :i"
        ), {"i": source["id"]}).first()
    assert row[0] == "Active"
    assert row[1] is None
    assert row[2] is None
    assert row[3] is None

    admin.delete(f"{BASE_URL}/api/cost-codes/{source['id']}")
    admin.delete(f"{BASE_URL}/api/cost-codes/{target['id']}")


# --------------------------------------------------------------------------
# Idempotency / state errors
# --------------------------------------------------------------------------

def test_reactivate_already_active_returns_409(admin, section_id):
    code = _fresh_cost_code(admin, section_id, prefix="ZZA")
    r = _reactivate(admin, code["id"])
    assert r.status_code == 409, r.text
    admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


def test_retire_already_retired_returns_409(admin, section_id):
    code = _fresh_cost_code(admin, section_id, prefix="ZZB")
    r1 = _retire(admin, code["id"])
    assert r1.status_code == 200
    r2 = _retire(admin, code["id"])
    assert r2.status_code == 409, r2.text
    # Reactivate to allow delete (delete-guard runs the same path either way,
    # but tidiness).
    _reactivate(admin, code["id"])
    admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


def test_reactivate_unknown_id_returns_404(admin):
    r = _reactivate(admin, str(uuid.uuid4()))
    assert r.status_code == 404


# --------------------------------------------------------------------------
# RBAC matrix on reactivate
# --------------------------------------------------------------------------

def test_director_can_reactivate(admin, director, section_id):
    """cost_codes.edit is inherited by director via ALL-minus-exclusions
    (cost_codes.delete is the only excluded action, NOT edit)."""
    code = _fresh_cost_code(admin, section_id, prefix="ZZD")
    _retire(admin, code["id"])
    r = _reactivate(director, code["id"])
    assert r.status_code == 200, (
        f"Director must hold cost_codes.edit (inherits from "
        f"ALL-minus-exclusions); reactivate returned {r.status_code}."
    )
    admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


def test_finance_can_reactivate(admin, finance, section_id):
    """Finance was explicitly granted cost_codes.edit in Gate 2."""
    code = _fresh_cost_code(admin, section_id, prefix="ZZF")
    _retire(admin, code["id"])
    r = _reactivate(finance, code["id"])
    assert r.status_code == 200, r.text
    admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


def test_pm_cannot_reactivate(admin, pm, section_id):
    code = _fresh_cost_code(admin, section_id, prefix="ZZG")
    _retire(admin, code["id"])
    r = _reactivate(pm, code["id"])
    assert r.status_code == 403, r.text
    admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


# --------------------------------------------------------------------------
# Audit trail
# --------------------------------------------------------------------------

def test_reactivate_writes_audit_row(admin, section_id, db_engine):
    code = _fresh_cost_code(admin, section_id, prefix="ZZX")
    _retire(admin, code["id"], "audit probe")
    _reactivate(admin, code["id"])
    with db_engine.connect() as c:
        rows = c.execute(text("""
            SELECT action, metadata_json
            FROM audit_log
            WHERE resource_type = 'cost_codes'
              AND resource_id = :i
              AND action = 'Status_Change'
            ORDER BY created_at
        """), {"i": code["id"]}).all()
    actions = [r[0] for r in rows]
    metadatas = [r[1] or {} for r in rows]
    # Must contain at least one retire + one reactivate audit row.
    assert len(actions) >= 2, f"Expected >=2 Status_Change rows, got {actions}"
    kinds = {m.get("kind") for m in metadatas if isinstance(m, dict)}
    assert "retire" in kinds and "reactivate" in kinds, (
        f"Audit metadata.kind missing one of retire/reactivate: {kinds}"
    )
    admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")
