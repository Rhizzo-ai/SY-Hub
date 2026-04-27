"""Backend tests for Prompt 1.5 — Projects + Team Members.

Covers project code generation, area conversion, planning expiry auto-calc,
forward-only stage machine + override, team member management, scoping,
delete-block stub, planning expiry sweep thresholds, financials refresh
stub and audit wiring.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, select, text

from tests.conftest import login_with_auto_enroll, plain_login


load_dotenv("/app/backend/.env")

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
TEST_PASSWORD = "TestUser-Dev-2026!"

ADMIN_EMAIL = "test-admin@example.test"
DIRECTOR_EMAIL = "test-director@example.test"
PM_EMAIL = "test-pm@example.test"
FINANCE_EMAIL = "test-finance@example.test"
READONLY_EMAIL = "test-readonly@example.test"
SITE_EMAIL = "test-site@example.test"

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"
OTHER_ENTITY_NAME = "SY Homes Ltd"


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


def _wipe_projects(engine):
    """Cascade-cleans projects, team members, and related audit rows."""
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('projects','project_team_members')"
        ))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        # Null out FK from audit_log before deleting projects
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "UPDATE audit_log SET project_id = NULL "
            "WHERE project_id IS NOT NULL"
        ))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM project_team_members"))
        c.execute(text("DELETE FROM user_role_projects"))
        c.execute(text("DELETE FROM projects"))


@pytest.fixture(scope="module", autouse=True)
def _clean_projects(db_engine):
    _wipe_projects(db_engine)
    yield
    _wipe_projects(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def pm():
    return plain_login(BASE_URL, PM_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def readonly():
    return plain_login(BASE_URL, READONLY_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def site_manager():
    return plain_login(BASE_URL, SITE_EMAIL, TEST_PASSWORD)


@pytest.fixture(scope="module")
def entity_ids(db_engine):
    with db_engine.connect() as c:
        prim = c.execute(
            text("SELECT id FROM entities WHERE name = :n"),
            {"n": PRIMARY_ENTITY_NAME},
        ).scalar()
        other = c.execute(
            text("SELECT id FROM entities WHERE name = :n"),
            {"n": OTHER_ENTITY_NAME},
        ).scalar()
    assert prim and other, "seeded entities missing"
    return {"primary": str(prim), "other": str(other)}


@pytest.fixture(scope="module")
def user_ids(db_engine):
    with db_engine.connect() as c:
        rows = c.execute(text(
            "SELECT email, id FROM users WHERE email LIKE 'test-%@example.test'"
        )).fetchall()
    return {email: str(uid) for email, uid in rows}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _project_payload(entity_id: str, **overrides) -> dict:
    p = {
        "name": "Shrewsbury Phase 1",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "10 Test Lane, Shrewsbury",
        "site_postcode": "SY1 1AA",
        "local_authority": "Shropshire Council",
        "tenure": "Freehold",
    }
    p.update(overrides)
    return p


def _create_project(session, entity_id, **overrides):
    r = session.post(
        f"{BASE_URL}/api/projects",
        json=_project_payload(entity_id, **overrides),
    )
    assert r.status_code == 201, f"create failed: {r.status_code} {r.text}"
    return r.json()


# ==========================================================================
# Section A — Project code generation (override + auto)
# ==========================================================================

class TestProjectCode:
    def test_auto_code_first_project_uses_slug_prefix(self, admin, entity_ids):
        _wipe_projects_for_module()
        p = _create_project(admin, entity_ids["primary"], name="Shrewsbury Phase 1")
        assert p["project_code"] == "SHR-001"

    def test_auto_code_second_project_increments_counter(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Shrewsbury Phase 2")
        assert p["project_code"] == "SHR-002"

    def test_auto_code_different_slug_starts_at_001(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Oswestry Development")
        assert p["project_code"] == "OSW-001"

    def test_auto_code_short_name_is_padded(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="AB")
        assert p["project_code"].startswith("ABX-")

    def test_auto_code_strips_non_alphanum(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="23-High Street Redev")
        assert p["project_code"].startswith("23H-")

    def test_override_valid_format_accepted(self, admin, entity_ids):
        p = _create_project(
            admin, entity_ids["primary"],
            name="Manual Code Project", project_code="MAN-500",
        )
        assert p["project_code"] == "MAN-500"

    def test_override_bad_format_rejected(self, admin, entity_ids):
        r = admin.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(entity_ids["primary"],
                                  name="Bad Code", project_code="bad-code"),
        )
        assert r.status_code == 400
        assert "project_code" in r.text

    def test_override_too_short_sequence_rejected(self, admin, entity_ids):
        r = admin.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(entity_ids["primary"],
                                  name="Bad Code 2", project_code="XYZ-12"),
        )
        assert r.status_code == 400

    def test_override_duplicate_rejected(self, admin, entity_ids):
        r = admin.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(entity_ids["primary"],
                                  name="Duplicate", project_code="MAN-500"),
        )
        assert r.status_code == 409

    def test_project_code_is_immutable_on_update(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Immutable Test")
        r = admin.put(
            f"{BASE_URL}/api/projects/{p['id']}",
            json={"project_code": "XXX-999"},
        )
        assert r.status_code == 400


def _wipe_projects_for_module():
    """Pytest-inline wipe so the first test class can run cleanly."""
    eng = create_engine(DATABASE_URL, future=True)
    _wipe_projects(eng)
    eng.dispose()


# ==========================================================================
# Section B — Area conversion
# ==========================================================================

class TestAreaConversion:
    def test_ha_derives_acres(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="Area Test 1", site_area_ha="1.0000")
        assert Decimal(str(p["site_area_ha"])) == Decimal("1.0000")
        assert Decimal(str(p["site_area_acres"])) == Decimal("2.4711")

    def test_acres_derives_ha(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="Area Test 2", site_area_acres="2.4711")
        assert Decimal(str(p["site_area_ha"])).quantize(Decimal("0.01")) == Decimal("1.00")

    def test_ha_wins_when_both_supplied(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="Area Both",
                            site_area_ha="2.0000",
                            site_area_acres="99.9999")
        assert Decimal(str(p["site_area_ha"])) == Decimal("2.0000")
        assert Decimal(str(p["site_area_acres"])) == Decimal("4.9421")

    def test_null_areas_remain_null(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Area Null")
        assert p["site_area_ha"] is None
        assert p["site_area_acres"] is None

    def test_area_updated_on_put(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Area Update")
        r = admin.put(f"{BASE_URL}/api/projects/{p['id']}",
                      json={"site_area_ha": "5.0000"})
        assert r.status_code == 200
        body = r.json()
        assert Decimal(str(body["site_area_ha"])) == Decimal("5.0000")
        assert Decimal(str(body["site_area_acres"])) == Decimal("12.3553")

    def test_round_trip_ha_acres_ha_is_stable(self, admin, entity_ids):
        ha_in = Decimal("3.2500")
        p = _create_project(admin, entity_ids["primary"],
                            name="Round Trip", site_area_ha=str(ha_in))
        assert Decimal(str(p["site_area_ha"])) == ha_in


# ==========================================================================
# Section C — Planning expiry auto-calc
# ==========================================================================

class TestPlanningExpiry:
    def test_full_permission_three_year_expiry(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="Full Perm",
                            planning_type="Full",
                            planning_approval_date="2025-06-01")
        assert p["planning_expiry_date"] == "2028-06-01"

    def test_outline_permission_three_year_expiry(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="Outline Perm",
                            planning_type="Outline",
                            planning_approval_date="2025-06-01")
        assert p["planning_expiry_date"] == "2028-06-01"

    def test_reserved_matters_two_year_expiry(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="RM Expiry",
                            planning_type="Reserved_Matters",
                            planning_approval_date="2025-06-01")
        assert p["planning_expiry_date"] == "2027-06-01"

    def test_manual_expiry_override_is_preserved(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="Manual Expiry",
                            planning_type="Full",
                            planning_approval_date="2025-06-01",
                            planning_expiry_date="2029-01-15")
        assert p["planning_expiry_date"] == "2029-01-15"

    def test_no_type_no_expiry(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="No Planning Type")
        assert p["planning_expiry_date"] is None

    def test_update_recalculates_expiry_when_approval_changes(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"],
                            name="Recalc Test",
                            planning_type="Full",
                            planning_approval_date="2025-01-01")
        assert p["planning_expiry_date"] == "2028-01-01"
        r = admin.put(
            f"{BASE_URL}/api/projects/{p['id']}",
            json={"planning_approval_date": "2026-03-15"},
        )
        assert r.status_code == 200
        assert r.json()["planning_expiry_date"] == "2029-03-15"

    def test_update_manual_override_flagged_in_audit(self, admin, entity_ids, db_engine):
        p = _create_project(admin, entity_ids["primary"],
                            name="Manual Override Audit",
                            planning_type="Full",
                            planning_approval_date="2025-05-01")
        r = admin.put(
            f"{BASE_URL}/api/projects/{p['id']}",
            json={"planning_expiry_date": "2030-12-31"},
        )
        assert r.status_code == 200
        with db_engine.connect() as c:
            meta = c.execute(text(
                "SELECT metadata_json FROM audit_log "
                "WHERE resource_type='projects' AND resource_id=:pid "
                "AND action='Update' ORDER BY created_at DESC LIMIT 1"
            ), {"pid": p["id"]}).scalar()
        assert meta is not None
        assert meta.get("planning_expiry_manual_override") is True


# ==========================================================================
# Section D — Stage machine (forward-only + override)
# ==========================================================================

class TestStageMachine:
    def test_new_project_starts_at_lead(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Stage Init")
        assert p["current_stage"] == "Lead"
        assert p["status"] == "Active"

    def test_advance_lead_to_appraisal(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Stage Advance 1")
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                       json={"new_stage": "Appraisal"})
        assert r.status_code == 200
        assert r.json()["current_stage"] == "Appraisal"

    def test_cannot_skip_appraisal(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Stage Skip Test")
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                       json={"new_stage": "Planning"})
        assert r.status_code == 409

    def test_cannot_go_backwards(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Stage Backwards")
        admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                   json={"new_stage": "Appraisal"})
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                       json={"new_stage": "Lead"})
        assert r.status_code == 409

    def test_dead_from_any_active_stage_is_allowed(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Stage Dead Any")
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                       json={"new_stage": "Dead", "dead_reason": "Client pulled out"})
        assert r.status_code == 200
        body = r.json()
        assert body["current_stage"] == "Dead"
        assert body["status"] == "Dead"
        assert body["dead_reason"] == "Client pulled out"

    def test_dead_without_reason_fails(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Stage Dead No Reason")
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                       json={"new_stage": "Dead"})
        assert r.status_code == 400

    def test_closed_syncs_status_to_complete(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Stage Closed")
        # Walk all the way through
        for s in ("Appraisal", "Deal_Pipeline", "Planning", "Pre_Con",
                  "Construction", "Sales", "Post_Completion", "Closed"):
            r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                           json={"new_stage": s})
            assert r.status_code == 200, f"stage {s}: {r.text}"
        assert r.json()["current_stage"] == "Closed"
        assert r.json()["status"] == "Complete"

    def test_construction_can_branch_to_sales_or_post_completion(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Branch Test")
        for s in ("Appraisal", "Deal_Pipeline", "Planning", "Pre_Con", "Construction"):
            admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                       json={"new_stage": s})
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                       json={"new_stage": "Post_Completion"})
        assert r.status_code == 200

    def test_stage_advance_stamps_audit(self, admin, entity_ids, db_engine):
        p = _create_project(admin, entity_ids["primary"], name="Stage Audit")
        admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                   json={"new_stage": "Appraisal"})
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT action, metadata_json FROM audit_log "
                "WHERE resource_id=:pid AND action='Stage_Change' "
                "ORDER BY created_at DESC LIMIT 1"
            ), {"pid": p["id"]}).first()
        assert row is not None
        assert row[1]["override"] is False
        assert row[1]["old_stage"] == "Lead"
        assert row[1]["new_stage"] == "Appraisal"


class TestStageOverride:
    def test_director_cannot_override(self, director, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Override Director")
        r = director.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/override",
            json={"new_stage": "Construction",
                  "reason": "Director tried to skip ahead"},
        )
        assert r.status_code == 403

    def test_admin_override_skips_stages(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Override Skip")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/override",
            json={"new_stage": "Construction",
                  "reason": "Direct-to-build emergency approved"},
        )
        assert r.status_code == 200
        assert r.json()["current_stage"] == "Construction"

    def test_override_requires_minimum_reason_length(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Override Short")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/override",
            json={"new_stage": "Planning", "reason": "short"},
        )
        assert r.status_code == 422

    def test_override_reactivates_dead_project(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Override Revive")
        admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                   json={"new_stage": "Dead",
                         "dead_reason": "Mistake"})
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/override",
            json={"new_stage": "Appraisal",
                  "reason": "Resurrecting the project after error"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["current_stage"] == "Appraisal"
        assert body["status"] == "Active"

    def test_override_to_dead_requires_dead_reason(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Override Dead")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/override",
            json={"new_stage": "Dead",
                  "reason": "Testing dead reason requirement"},
        )
        assert r.status_code == 400

    def test_override_same_stage_rejected(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Override Same")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/override",
            json={"new_stage": "Lead",
                  "reason": "Same stage attempt for test"},
        )
        assert r.status_code == 400

    def test_override_stamps_audit_with_reason_and_director_notifications(
        self, admin, entity_ids, db_engine
    ):
        p = _create_project(admin, entity_ids["primary"], name="Override Audit")
        admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/override",
            json={"new_stage": "Construction",
                  "reason": "Emergency override for testing audit trail"},
        )
        with db_engine.connect() as c:
            meta = c.execute(text(
                "SELECT metadata_json FROM audit_log "
                "WHERE resource_id=:pid AND action='Stage_Change' "
                "ORDER BY created_at DESC LIMIT 1"
            ), {"pid": p["id"]}).scalar()
        assert meta["override"] is True
        assert meta["override_reason"].startswith("Emergency override")
        assert meta["actor_role"] == "super_admin"
        assert isinstance(meta["director_notifications"], list)
        assert meta["director_notifications"][0]["type"] == "Stage_Override"


# ==========================================================================
# Section E — Team member management
# ==========================================================================

class TestTeamMembers:
    def test_add_team_member(self, admin, entity_ids, user_ids):
        p = _create_project(admin, entity_ids["primary"], name="Team Add")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Project_Lead",
                  "is_primary": True},
        )
        assert r.status_code == 201
        tm = r.json()
        assert tm["role_on_project"] == "Project_Lead"
        assert tm["is_primary"] is True

    def test_primary_project_lead_syncs_to_project_lead_user_id(
        self, admin, entity_ids, user_ids
    ):
        p = _create_project(admin, entity_ids["primary"], name="Lead Sync")
        admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Project_Lead",
                  "is_primary": True},
        )
        got = admin.get(f"{BASE_URL}/api/projects/{p['id']}").json()
        assert got["project_lead_user_id"] == user_ids[PM_EMAIL]

    def test_cannot_have_two_active_primaries_same_role(
        self, admin, entity_ids, user_ids
    ):
        p = _create_project(admin, entity_ids["primary"], name="Two Primaries")
        r1 = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Project_Lead",
                  "is_primary": True},
        )
        assert r1.status_code == 201
        r2 = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[DIRECTOR_EMAIL],
                  "role_on_project": "Project_Lead",
                  "is_primary": True},
        )
        assert r2.status_code == 409

    def test_can_have_multiple_non_primary_same_role(self, admin, entity_ids, user_ids):
        p = _create_project(admin, entity_ids["primary"], name="Multi Non Primary")
        for email in (PM_EMAIL, DIRECTOR_EMAIL):
            r = admin.post(
                f"{BASE_URL}/api/projects/{p['id']}/team",
                json={"user_id": user_ids[email],
                      "role_on_project": "Consultant",
                      "is_primary": False},
            )
            assert r.status_code == 201

    def test_invalid_role_rejected(self, admin, entity_ids, user_ids):
        p = _create_project(admin, entity_ids["primary"], name="Bad Role")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Not_A_Role",
                  "is_primary": False},
        )
        assert r.status_code == 422

    def test_unknown_user_rejected(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Unknown User")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": str(uuid.uuid4()),
                  "role_on_project": "Consultant"},
        )
        assert r.status_code == 404

    def test_list_team_active_only_by_default(self, admin, entity_ids, user_ids):
        p = _create_project(admin, entity_ids["primary"], name="List Active")
        add = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Site_Manager",
                  "is_primary": True},
        )
        tm_id = add.json()["id"]
        admin.delete(f"{BASE_URL}/api/projects/{p['id']}/team/{tm_id}")
        active = admin.get(f"{BASE_URL}/api/projects/{p['id']}/team").json()
        assert all(t["removed_at"] is None for t in active)
        assert not any(t["id"] == tm_id for t in active)

    def test_list_team_history_includes_removed(self, admin, entity_ids, user_ids):
        p = _create_project(admin, entity_ids["primary"], name="List History")
        add = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Quantity_Surveyor"},
        )
        tm_id = add.json()["id"]
        admin.delete(f"{BASE_URL}/api/projects/{p['id']}/team/{tm_id}")
        history = admin.get(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            params={"history": "true"},
        ).json()
        assert any(t["id"] == tm_id and t["removed_at"] for t in history)

    def test_remove_primary_lead_nulls_project_lead(
        self, admin, entity_ids, user_ids
    ):
        p = _create_project(admin, entity_ids["primary"], name="Remove Lead Null")
        add = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Project_Lead",
                  "is_primary": True},
        )
        tm_id = add.json()["id"]
        admin.delete(f"{BASE_URL}/api/projects/{p['id']}/team/{tm_id}")
        got = admin.get(f"{BASE_URL}/api/projects/{p['id']}").json()
        assert got["project_lead_user_id"] is None

    def test_remove_idempotent(self, admin, entity_ids, user_ids):
        p = _create_project(admin, entity_ids["primary"], name="Remove Idempotent")
        add = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Finance"},
        )
        tm_id = add.json()["id"]
        r1 = admin.delete(f"{BASE_URL}/api/projects/{p['id']}/team/{tm_id}")
        r2 = admin.delete(f"{BASE_URL}/api/projects/{p['id']}/team/{tm_id}")
        assert r1.status_code == 204
        assert r2.status_code == 204

    def test_remove_wrong_project_404(self, admin, entity_ids, user_ids):
        p1 = _create_project(admin, entity_ids["primary"], name="WP1")
        p2 = _create_project(admin, entity_ids["primary"], name="WP2")
        add = admin.post(
            f"{BASE_URL}/api/projects/{p1['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Designer"},
        )
        r = admin.delete(
            f"{BASE_URL}/api/projects/{p2['id']}/team/{add.json()['id']}"
        )
        assert r.status_code == 404

    def test_team_add_records_audit(self, admin, entity_ids, user_ids, db_engine):
        p = _create_project(admin, entity_ids["primary"], name="Team Audit")
        r = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Contracts_Manager",
                  "is_primary": True},
        )
        tm_id = r.json()["id"]
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT action, metadata_json FROM audit_log "
                "WHERE resource_type='project_team_members' "
                "AND resource_id=:tid ORDER BY created_at DESC LIMIT 1"
            ), {"tid": tm_id}).first()
        assert row is not None
        assert row[0] == "Create"
        assert row[1]["role_on_project"] == "Contracts_Manager"

    def test_team_remove_records_audit(self, admin, entity_ids, user_ids, db_engine):
        p = _create_project(admin, entity_ids["primary"], name="Team Remove Audit")
        add = admin.post(
            f"{BASE_URL}/api/projects/{p['id']}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Sales"},
        )
        admin.delete(f"{BASE_URL}/api/projects/{p['id']}/team/{add.json()['id']}")
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT action FROM audit_log "
                "WHERE resource_type='project_team_members' "
                "AND resource_id=:tid AND action='Delete'"
            ), {"tid": add.json()["id"]}).first()
        assert row is not None


# ==========================================================================
# Section F — Scoping / RBAC
# ==========================================================================

class TestScoping:
    def test_unauthenticated_cannot_list(self, entity_ids):
        import requests as R
        r = R.get(f"{BASE_URL}/api/projects")
        assert r.status_code == 401

    def test_readonly_cannot_create(self, readonly, entity_ids):
        r = readonly.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(entity_ids["primary"], name="RO Create"),
        )
        assert r.status_code == 403

    def test_readonly_cannot_delete(self, readonly, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="RO Delete")
        r = readonly.delete(f"{BASE_URL}/api/projects/{p['id']}")
        assert r.status_code == 403

    def test_readonly_cannot_advance_stage(self, readonly, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="RO Stage")
        r = readonly.post(
            f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
            json={"new_stage": "Appraisal"},
        )
        assert r.status_code == 403

    def test_readonly_can_view(self, readonly, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="RO View")
        r = readonly.get(f"{BASE_URL}/api/projects/{p['id']}")
        assert r.status_code == 200

    def test_readonly_does_not_see_financials(self, readonly, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="RO Financials")
        body = readonly.get(f"{BASE_URL}/api/projects/{p['id']}").json()
        assert "margin_actual_pct" not in body
        assert "gdv_actual" not in body

    def test_director_sees_financials(self, director, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Dir Fin")
        body = director.get(f"{BASE_URL}/api/projects/{p['id']}").json()
        assert "margin_actual_pct" in body

    def test_finance_sees_financials(self, finance, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Fin Fin")
        body = finance.get(f"{BASE_URL}/api/projects/{p['id']}").json()
        assert "margin_actual_pct" in body

    def test_site_manager_cannot_create(self, site_manager, entity_ids):
        r = site_manager.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(entity_ids["primary"], name="Site Create"),
        )
        assert r.status_code == 403

    def test_pagination_works(self, admin, entity_ids):
        # Seed a few projects, then request page 1 size 2
        for i in range(3):
            _create_project(admin, entity_ids["primary"],
                            name=f"Pagination Test {i}")
        r = admin.get(
            f"{BASE_URL}/api/projects",
            params={"page": 1, "page_size": 2},
        )
        assert r.status_code == 200
        body = r.json()
        assert len(body["items"]) == 2
        assert body["total"] >= 3

    def test_search_by_name(self, admin, entity_ids):
        _create_project(admin, entity_ids["primary"], name="Search Target Unique")
        r = admin.get(
            f"{BASE_URL}/api/projects",
            params={"q": "Unique"},
        )
        assert r.status_code == 200
        assert any("Search Target Unique" == it["name"] for it in r.json()["items"])

    def test_filter_by_stage(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Filter Stage Test")
        admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                   json={"new_stage": "Appraisal"})
        r = admin.get(
            f"{BASE_URL}/api/projects",
            params={"current_stage": "Appraisal"},
        )
        codes = [it["current_stage"] for it in r.json()["items"]]
        assert all(c == "Appraisal" for c in codes)

    def test_filter_by_entity(self, admin, entity_ids):
        _create_project(admin, entity_ids["primary"], name="Entity A Filter 1")
        _create_project(admin, entity_ids["other"], name="Entity B Filter 1")
        r = admin.get(
            f"{BASE_URL}/api/projects",
            params={"primary_entity_id": entity_ids["other"]},
        )
        assert r.status_code == 200
        assert all(it["primary_entity_id"] == entity_ids["other"]
                   for it in r.json()["items"])


# ==========================================================================
# Section G — Delete blocking + update flow
# ==========================================================================

class TestDeleteBlocking:
    def test_delete_no_dependents_succeeds(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Delete OK")
        r = admin.delete(f"{BASE_URL}/api/projects/{p['id']}")
        assert r.status_code == 204
        r2 = admin.get(f"{BASE_URL}/api/projects/{p['id']}")
        assert r2.status_code == 404

    def test_delete_404(self, admin):
        r = admin.delete(f"{BASE_URL}/api/projects/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_delete_records_audit(self, admin, entity_ids, db_engine):
        p = _create_project(admin, entity_ids["primary"], name="Delete Audit")
        pid = p["id"]
        admin.delete(f"{BASE_URL}/api/projects/{pid}")
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT action FROM audit_log WHERE resource_id=:pid "
                "AND action='Delete'"
            ), {"pid": pid}).first()
        assert row is not None


class TestUpdateFlow:
    def test_update_tracks_audit_diff(self, admin, entity_ids, db_engine):
        p = _create_project(admin, entity_ids["primary"], name="Update Diff")
        r = admin.put(
            f"{BASE_URL}/api/projects/{p['id']}",
            json={"name": "Update Diff Renamed", "units_target": 20},
        )
        assert r.status_code == 200
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT field_changes FROM audit_log "
                "WHERE resource_id=:pid AND action='Update' "
                "ORDER BY created_at DESC LIMIT 1"
            ), {"pid": p["id"]}).scalar()
        fields = {f["field"] for f in row}
        assert "name" in fields
        assert "units_target" in fields

    def test_update_with_no_changes_does_not_write_audit(
        self, admin, entity_ids, db_engine
    ):
        p = _create_project(admin, entity_ids["primary"], name="No Diff")
        with db_engine.connect() as c:
            before = c.execute(text(
                "SELECT count(*) FROM audit_log "
                "WHERE resource_id=:pid AND action='Update'"
            ), {"pid": p["id"]}).scalar()
        admin.put(
            f"{BASE_URL}/api/projects/{p['id']}",
            json={"name": "No Diff"},  # unchanged
        )
        with db_engine.connect() as c:
            after = c.execute(text(
                "SELECT count(*) FROM audit_log "
                "WHERE resource_id=:pid AND action='Update'"
            ), {"pid": p["id"]}).scalar()
        assert before == after


# ==========================================================================
# Section H — Service-level helpers (unit tests)
# ==========================================================================

class TestServiceHelpers:
    def test_validate_code_override_happy(self):
        from app.services.projects import validate_code_override
        assert validate_code_override("ABC-001") is True
        assert validate_code_override("XY1-999") is True
        assert validate_code_override("123-1234") is True

    def test_validate_code_override_rejects(self):
        from app.services.projects import validate_code_override
        assert validate_code_override("abc-001") is False
        assert validate_code_override("AB-001") is False
        assert validate_code_override("ABCD-001") is False
        assert validate_code_override("ABC_001") is False
        assert validate_code_override("") is False

    def test_reconcile_area_both_prefers_ha(self):
        from app.services.projects import reconcile_area
        ha, acres = reconcile_area(Decimal("1"), Decimal("99"))
        assert ha == Decimal("1.0000")
        assert acres == Decimal("2.4711")

    def test_reconcile_area_none_none_returns_none(self):
        from app.services.projects import reconcile_area
        assert reconcile_area(None, None) == (None, None)

    def test_derive_planning_expiry_full(self):
        from app.services.projects import derive_planning_expiry
        assert derive_planning_expiry("Full", date(2025, 1, 1)) == date(2028, 1, 1)

    def test_derive_planning_expiry_reserved_matters(self):
        from app.services.projects import derive_planning_expiry
        assert (derive_planning_expiry("Reserved_Matters", date(2025, 6, 1))
                == date(2027, 6, 1))

    def test_derive_planning_expiry_missing_inputs(self):
        from app.services.projects import derive_planning_expiry
        assert derive_planning_expiry(None, date(2025, 1, 1)) is None
        assert derive_planning_expiry("Full", None) is None

    def test_is_allowed_forward(self):
        from app.services.project_stage import is_allowed_forward
        assert is_allowed_forward("Lead", "Appraisal") is True
        assert is_allowed_forward("Lead", "Planning") is False
        assert is_allowed_forward("Closed", "Lead") is False
        assert is_allowed_forward("Construction", "Dead") is True


# ==========================================================================
# Section I — Planning expiry sweep
# ==========================================================================

class TestPlanningExpirySweep:
    def test_sweep_fires_exact_thresholds(self, admin, entity_ids, db_engine):
        _wipe_projects(db_engine)
        from app.db import SessionLocal
        from app.scheduler import planning_expiry_sweep
        # Create a project expiring exactly 30 days from now
        today = date.today()
        target = today + timedelta(days=30)
        admin.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(
                entity_ids["primary"], name="Sweep 30",
                planning_expiry_date=target.isoformat(),
                implementation_required=True,
            ),
        )
        db = SessionLocal()
        try:
            payloads = planning_expiry_sweep(db, today=today)
        finally:
            db.close()
        assert any(p["days_remaining"] == 30 for p in payloads)

    def test_sweep_skips_non_thresholds(self, admin, entity_ids, db_engine):
        _wipe_projects(db_engine)
        from app.db import SessionLocal
        from app.scheduler import planning_expiry_sweep
        today = date.today()
        target = today + timedelta(days=100)  # not a threshold
        admin.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(
                entity_ids["primary"], name="Sweep 100",
                planning_expiry_date=target.isoformat(),
                implementation_required=True,
            ),
        )
        db = SessionLocal()
        try:
            payloads = planning_expiry_sweep(db, today=today)
        finally:
            db.close()
        assert all(p["project_code"] != _get_code_for("Sweep 100", db_engine)
                   for p in payloads)

    def test_sweep_fires_daily_past_expiry(self, admin, entity_ids, db_engine):
        _wipe_projects(db_engine)
        from app.db import SessionLocal
        from app.scheduler import planning_expiry_sweep
        today = date.today()
        target = today - timedelta(days=5)
        admin.post(
            f"{BASE_URL}/api/projects",
            json=_project_payload(
                entity_ids["primary"], name="Sweep Past",
                planning_expiry_date=target.isoformat(),
                implementation_required=True,
            ),
        )
        db = SessionLocal()
        try:
            payloads = planning_expiry_sweep(db, today=today)
        finally:
            db.close()
        assert any(p["days_remaining"] == -5 for p in payloads)

    def test_sweep_skips_non_active_projects(self, admin, entity_ids, db_engine):
        _wipe_projects(db_engine)
        from app.db import SessionLocal
        from app.scheduler import planning_expiry_sweep
        today = date.today()
        target = today + timedelta(days=30)
        p = _create_project(
            admin, entity_ids["primary"], name="Sweep Dead",
            planning_expiry_date=target.isoformat(),
        )
        admin.post(f"{BASE_URL}/api/projects/{p['id']}/stage/advance",
                   json={"new_stage": "Dead", "dead_reason": "Test"})
        db = SessionLocal()
        try:
            payloads = planning_expiry_sweep(db, today=today)
        finally:
            db.close()
        assert all(pl["project_code"] != p["project_code"] for pl in payloads)

    def test_sweep_skips_started_projects(self, admin, entity_ids, db_engine):
        _wipe_projects(db_engine)
        from app.db import SessionLocal
        from app.scheduler import planning_expiry_sweep
        today = date.today()
        target = today + timedelta(days=30)
        p = _create_project(
            admin, entity_ids["primary"], name="Sweep Started",
            planning_expiry_date=target.isoformat(),
        )
        admin.put(
            f"{BASE_URL}/api/projects/{p['id']}",
            json={"actual_start_date": today.isoformat()},
        )
        db = SessionLocal()
        try:
            payloads = planning_expiry_sweep(db, today=today)
        finally:
            db.close()
        assert all(pl["project_code"] != p["project_code"] for pl in payloads)


def _get_code_for(name: str, engine):
    with engine.connect() as c:
        return c.execute(text(
            "SELECT project_code FROM projects WHERE name=:n"
        ), {"n": name}).scalar()


# ==========================================================================
# Section J — Financials refresh (stub)
# ==========================================================================

class TestFinancialsRefresh:
    def test_refresh_returns_zero_rollups(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Fin Refresh OK")
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/financials/refresh")
        assert r.status_code == 200
        body = r.json()
        assert Decimal(str(body["gdv_actual"])) == 0
        assert Decimal(str(body["margin_actual_pct"])) == 0
        assert body["financials_refreshed_at"] is not None

    def test_refresh_requires_view_sensitive(self, readonly, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Fin Refresh 403")
        r = readonly.post(f"{BASE_URL}/api/projects/{p['id']}/financials/refresh")
        assert r.status_code == 403

    def test_refresh_stamps_financials_refreshed_at(self, admin, entity_ids):
        p = _create_project(admin, entity_ids["primary"], name="Fin Refresh Stamp")
        r = admin.post(f"{BASE_URL}/api/projects/{p['id']}/financials/refresh")
        assert r.status_code == 200
        follow = admin.get(f"{BASE_URL}/api/projects/{p['id']}").json()
        assert follow["financials_refreshed_at"] is not None


# ==========================================================================
# Section K — Audit retroactive FK sanity
# ==========================================================================

class TestRetroFKs:
    def test_user_role_projects_fk_exists(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE constraint_name='fk_user_role_projects_project_id'"
            )).first()
        assert row is not None

    def test_audit_log_project_id_fk_exists(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE constraint_name='fk_audit_log_project_id'"
            )).first()
        assert row is not None

    def test_project_audit_row_set_null_on_delete(self, admin, entity_ids, db_engine):
        p = _create_project(admin, entity_ids["primary"], name="FK Audit Null")
        pid = p["id"]
        admin.delete(f"{BASE_URL}/api/projects/{pid}")
        with db_engine.connect() as c:
            # Audit row still exists but project_id must be NULL now
            row = c.execute(text(
                "SELECT project_id FROM audit_log "
                "WHERE resource_id=:pid AND action='Delete'"
            ), {"pid": pid}).first()
        assert row is not None
        assert row[0] is None


# ==========================================================================
# Section L — Project not-found + view permissions
# ==========================================================================

class TestLookup:
    def test_get_404(self, admin):
        r = admin.get(f"{BASE_URL}/api/projects/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_put_404(self, admin):
        r = admin.put(
            f"{BASE_URL}/api/projects/{uuid.uuid4()}",
            json={"name": "Ghost"},
        )
        assert r.status_code == 404

    def test_team_add_404(self, admin, user_ids):
        r = admin.post(
            f"{BASE_URL}/api/projects/{uuid.uuid4()}/team",
            json={"user_id": user_ids[PM_EMAIL],
                  "role_on_project": "Project_Lead"},
        )
        assert r.status_code == 404

    def test_stage_advance_404(self, admin):
        r = admin.post(
            f"{BASE_URL}/api/projects/{uuid.uuid4()}/stage/advance",
            json={"new_stage": "Appraisal"},
        )
        assert r.status_code == 404
