"""Audit Remediation Patch #2 — tests for I1 / I2 / I3 / M7.

I1: User invite endpoint writes an audit row.
I2: PII scrub endpoint writes an audit row before scrubbing.
I3: Bank fields are redacted in entity audit diffs.
M7: pyproject.toml exists with pytest config (so bare `pytest` works).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover — Python ≥3.11 in this project
    tomllib = None

load_dotenv("/app/backend/.env")

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
TEST_PASSWORD = "TestUser-Dev-2026!"

ADMIN_EMAIL = "test-admin@example.test"


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
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def admin_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text(
            "SELECT id FROM users WHERE email=:e"
        ), {"e": ADMIN_EMAIL}).scalar())


@pytest.fixture(scope="module")
def primary_entity_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text(
            "SELECT id FROM entities WHERE name='SY Homes Ltd'"
        )).scalar())


def _last_audit_for(engine, *, resource_type, resource_id, action):
    with engine.connect() as c:
        return c.execute(text(
            "SELECT actor_user_id, action, resource_type, resource_id, "
            "       field_changes, metadata_json, entity_id "
            "FROM audit_log "
            "WHERE resource_type=:rt AND resource_id=:rid AND action=:a "
            "ORDER BY created_at DESC LIMIT 1"
        ), {"rt": resource_type, "rid": resource_id, "a": action}).first()


# ==========================================================================
# I1 — User invite writes audit row
# ==========================================================================

def test_user_invite_writes_audit_row(admin, admin_id, primary_entity_id, db_engine):
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "email": f"invitee-{suffix}@example.test",
        "first_name": "Invite",
        "last_name": "Tee",
        "user_type": "Internal",
        "primary_entity_id": primary_entity_id,
    }
    r = admin.post(f"{BASE_URL}/api/users", json=payload)
    assert r.status_code == 201, r.text
    new_id = r.json()["user"]["id"]

    row = _last_audit_for(db_engine, resource_type="users",
                          resource_id=new_id, action="Create")
    assert row is not None, "No audit row written for user invite"
    actor_user_id, action, _rt, _rid, field_changes, metadata, entity_id = row

    assert str(actor_user_id) == admin_id
    assert action == "Create"
    assert str(entity_id) == primary_entity_id

    fc = {f["field"]: f for f in field_changes}
    assert "email" in fc
    assert fc["email"]["old"] is None
    assert fc["email"]["new"] == payload["email"]
    assert fc["user_type"]["new"] == "Internal"
    assert fc["primary_entity_id"]["new"] == primary_entity_id
    assert fc["status"]["new"] == "Pending_Invitation"

    # Sensitive credential fields must NOT appear in field_changes — they
    # are not yet populated at invite time, and even if they were the
    # invite payload should not surface them.
    assert "password_hash" not in fc
    assert "invitation_token_hash" not in fc

    assert metadata.get("action") == "invite"
    assert metadata.get("invited_by") == admin_id


def test_user_invite_audit_row_carries_request_metadata(admin, primary_entity_id, db_engine):
    suffix = uuid.uuid4().hex[:8]
    r = admin.post(f"{BASE_URL}/api/users", json={
        "email": f"invitee-meta-{suffix}@example.test",
        "first_name": "Meta", "last_name": "Tee",
        "user_type": "Internal",
        "primary_entity_id": primary_entity_id,
    })
    assert r.status_code == 201
    new_id = r.json()["user"]["id"]
    with db_engine.connect() as c:
        row = c.execute(text(
            "SELECT ip_address, user_agent FROM audit_log "
            "WHERE resource_id=:rid AND action='Create' AND resource_type='users'"
        ), {"rid": new_id}).first()
    assert row is not None
    # IP / UA should be captured (request param now wired through).
    assert row[0] is not None
    assert row[1] is not None and "python-requests" in row[1].lower()


# ==========================================================================
# I2 — PII scrub writes audit row BEFORE scrubbing
# ==========================================================================

def test_pii_scrub_writes_audit_row_with_scrubbed_markers(
    admin, admin_id, primary_entity_id, db_engine
):
    # Create a fresh user to scrub
    suffix = uuid.uuid4().hex[:8]
    invite = admin.post(f"{BASE_URL}/api/users", json={
        "email": f"scrub-target-{suffix}@example.test",
        "first_name": "Scrub", "last_name": "Target",
        "user_type": "Internal",
        "primary_entity_id": primary_entity_id,
        "phone": "+44 1234 567890",
    })
    assert invite.status_code == 201
    target_id = invite.json()["user"]["id"]
    target_email = invite.json()["user"]["email"]

    r = admin.post(f"{BASE_URL}/api/users/{target_id}/scrub_pii")
    assert r.status_code == 204, r.text

    row = _last_audit_for(db_engine, resource_type="users",
                          resource_id=target_id, action="Delete")
    assert row is not None, "No audit row written for PII scrub"
    actor_user_id, action, _rt, _rid, field_changes, metadata, entity_id = row

    assert str(actor_user_id) == admin_id
    assert action == "Delete"
    assert str(entity_id) == primary_entity_id

    fc = {f["field"]: f for f in field_changes}
    expected_keys = {
        "email", "first_name", "last_name", "display_name",
        "phone", "avatar_url", "job_title",
        "primary_entity_id", "user_type", "status_before",
    }
    assert expected_keys.issubset(fc.keys())

    # Both old and new must be the [SCRUBBED] marker — the actual PII
    # never reaches audit_log.
    for k in expected_keys:
        assert fc[k]["old"] == "[SCRUBBED]", f"{k} old leaked: {fc[k]['old']}"
        assert fc[k]["new"] == "[SCRUBBED]", f"{k} new leaked: {fc[k]['new']}"

    # The literal email should NOT appear anywhere in field_changes payload.
    raw = str(field_changes)
    assert target_email not in raw

    assert metadata.get("action") == "pii_scrub"
    assert metadata.get("gdpr_basis") == "right_to_erasure"
    assert metadata.get("preserves_fk_integrity") is True


def test_pii_scrub_actually_scrubs_the_user_row(admin, primary_entity_id, db_engine):
    suffix = uuid.uuid4().hex[:8]
    invite = admin.post(f"{BASE_URL}/api/users", json={
        "email": f"scrub-effect-{suffix}@example.test",
        "first_name": "Effect", "last_name": "Tee",
        "user_type": "Internal",
        "primary_entity_id": primary_entity_id,
    })
    target_id = invite.json()["user"]["id"]

    admin.post(f"{BASE_URL}/api/users/{target_id}/scrub_pii")

    with db_engine.connect() as c:
        row = c.execute(text(
            "SELECT email, first_name, status, password_hash, "
            "       mfa_secret_encrypted "
            "FROM users WHERE id=:id"
        ), {"id": target_id}).first()
    email, first_name, status, password_hash, mfa_secret = row
    assert "deleted+" in email and "syhomes.invalid" in email
    assert first_name == "[Deleted User"
    assert status == "Archived"
    assert password_hash is None
    assert mfa_secret is None


# ==========================================================================
# I3 — Bank fields redacted in entity audit diffs
# ==========================================================================

@pytest.fixture(scope="module")
def fresh_entity(admin, db_engine):
    """Create a sandbox entity for redaction tests."""
    name = f"AuditPatch2-{uuid.uuid4().hex[:8]}"
    r = admin.post(f"{BASE_URL}/api/entities", json={
        "name": name,
        "legal_name": name + " Limited",
        "entity_type": "SPV",
        "registered_address": "1 Test Street, Shrewsbury, SY1 1AA",
        "default_currency": "GBP",
    })
    assert r.status_code == 201, r.text
    eid = r.json()["id"]
    yield eid
    # Cleanup audit + entity rows so the suite stays deterministic.
    with db_engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type='entities' AND resource_id=:id"
        ), {"id": eid})
        c.execute(text(
            "UPDATE audit_log SET entity_id=NULL WHERE entity_id=:id"
        ), {"id": eid})
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM entities WHERE id=:id"), {"id": eid})


def test_entity_bank_fields_redacted_in_audit_diff(admin, fresh_entity, db_engine):
    # Update the entity with bank details. The schema accepts the
    # full 8-digit bank_account_number; the router masks it at write
    # time so audit_log only ever sees bank_account_number_masked.
    r = admin.put(f"{BASE_URL}/api/entities/{fresh_entity}", json={
        "bank_name": "Barclays Business Banking",
        "bank_account_name": "SY Homes (Patch2 Test) Ltd",
        "bank_account_number": "12344567",
        "legal_name": "SY Homes Patch2 Renamed Ltd",
    })
    assert r.status_code == 200, r.text

    with db_engine.connect() as c:
        field_changes = c.execute(text(
            "SELECT field_changes FROM audit_log "
            "WHERE resource_type='entities' AND resource_id=:id "
            "AND action='Update' ORDER BY created_at DESC LIMIT 1"
        ), {"id": fresh_entity}).scalar()

    assert field_changes is not None
    fc = {f["field"]: f for f in field_changes}

    # Sensitive banking columns must be redacted whenever present.
    for sensitive in ("bank_name", "bank_account_name",
                       "bank_account_number_masked"):
        if sensitive in fc:
            assert fc[sensitive]["old"] == "[REDACTED]"
            assert fc[sensitive]["new"] == "[REDACTED]"

    # The two values explicitly set above MUST appear in the diff.
    assert "bank_name" in fc and "bank_account_name" in fc

    # Literal bank values must NOT appear anywhere in the diff payload.
    raw = str(field_changes)
    assert "Barclays" not in raw
    assert "Patch2 Test" not in raw
    assert "4567" not in raw  # masked or full — neither should leak
    assert "12344567" not in raw

    # Non-sensitive fields in the same diff are NOT redacted.
    assert "legal_name" in fc
    assert fc["legal_name"]["new"] == "SY Homes Patch2 Renamed Ltd"


def test_sensitive_fields_set_includes_banking_and_utr():
    """Lock the redaction set so future PRs can't quietly remove these."""
    from app.services.audit import SENSITIVE_FIELDS

    must_include = {
        "password_hash", "password_history", "password_reset_token_hash",
        "mfa_secret_encrypted", "mfa_backup_codes_encrypted",
        "invitation_token_hash",
        "refresh_token_hash", "previous_refresh_token_hash",
        "bank_name", "bank_account_name", "bank_account_number_masked",
        "utr",
    }
    missing = must_include - SENSITIVE_FIELDS
    assert not missing, f"SENSITIVE_FIELDS missing: {missing}"


# ==========================================================================
# M7 — pyproject.toml configures pytest discovery
# ==========================================================================

@pytest.mark.skipif(tomllib is None, reason="tomllib requires Python 3.11+")
def test_pyproject_pytest_config():
    p = Path(__file__).resolve().parent.parent / "pyproject.toml"
    assert p.exists(), "/app/backend/pyproject.toml missing — bare `pytest` will fail"
    cfg = tomllib.loads(p.read_text())
    pytest_cfg = cfg["tool"]["pytest"]["ini_options"]
    assert "." in pytest_cfg["pythonpath"]
    assert "tests" in pytest_cfg["testpaths"]
