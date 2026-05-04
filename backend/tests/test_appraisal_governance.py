"""Prompt 2.3 Checkpoint 2 — Appraisal governance backend tests.

Covers (per Build Pack §H):
- Migration 0022: tables, enums, triggers, system_config seed
- Decision-log immutability triggers (UPDATE / DELETE raise)
- Scenario parent-validation trigger
- POST /appraisals/{id}/new-version (atomic handover + revision row)
- /reopen final form (Approved + Rejected toggle, no clone)
- Scenarios CRUD + comparator
- Decisions log + validation + append-only
- Nudge state endpoint + threshold matrix
- `recompute_revision_deltas` hook populates delta_* on save
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll, plain_login


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = "TestUser-Dev-2026!"

ADMIN_EMAIL = "test-admin@example.test"
DIRECTOR_EMAIL = "test-director@example.test"
PM_EMAIL = "test-pm@example.test"
FINANCE_EMAIL = "test-finance@example.test"
READONLY_EMAIL = "test-readonly@example.test"

PRIMARY_ENTITY_NAME = "SY Homes (Shrewsbury) Ltd"


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


def _wipe(engine):
    with engine.begin() as c:
        c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        c.execute(text(
            "DELETE FROM audit_log WHERE resource_type IN "
            "('appraisals','appraisal_units','appraisal_cost_lines',"
            " 'appraisal_finance_model','projects','project_team_members')"
        ))
        c.execute(text("UPDATE audit_log SET project_id = NULL "
                       "WHERE project_id IS NOT NULL"))
        c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_finance_model"))
        c.execute(text("DELETE FROM appraisal_cost_lines"))
        c.execute(text("DELETE FROM appraisal_units"))
        c.execute(text("ALTER TABLE appraisal_decision_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_decision_log"))
        c.execute(text("ALTER TABLE appraisal_decision_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM appraisal_revisions"))
        c.execute(text("DELETE FROM appraisal_scenarios"))
        c.execute(text("DELETE FROM appraisals"))
        c.execute(text("DELETE FROM project_team_members"))
        c.execute(text("DELETE FROM user_role_projects"))
        c.execute(text("DELETE FROM projects"))


@pytest.fixture(scope="module", autouse=True)
def _clean(db_engine):
    _wipe(db_engine)
    yield
    _wipe(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm():
    return plain_login(BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly():
    return plain_login(BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module")
def entity_id(db_engine):
    with db_engine.connect() as c:
        pid = c.execute(
            text("SELECT id FROM entities WHERE name = :n"),
            {"n": PRIMARY_ENTITY_NAME},
        ).scalar()
    assert pid
    return str(pid)


@pytest.fixture(scope="class")
def project(admin, entity_id):
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": f"Governance Test Project {uuid.uuid4().hex[:8]}",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "77 Governance St, Shrewsbury",
        "site_postcode": "SY1 2AA",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture(scope="function")
def fresh_project(admin, entity_id):
    """Function-scoped project — use when tests must each start from a
    pristine (project, group) state (e.g. TestScenarios / TestNudge)."""
    r = admin.post(f"{BASE_URL}/api/projects", json={
        "name": f"Gov Fresh {uuid.uuid4().hex[:8]}",
        "project_type": "Dev_Build",
        "primary_entity_id": entity_id,
        "land_ownership_method": "Direct_Purchase",
        "site_address": "77 Fresh Way, Shrewsbury",
        "site_postcode": "SY1 2BB",
        "tenure": "Freehold",
    })
    assert r.status_code == 201, r.text
    return r.json()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _create_appraisal(client, project_id, name="Gov A1"):
    r = client.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/appraisals",
        json={"name": name, "land_purchase_price": "100000"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _approve(client, appraisal_id):
    client.post(f"{BASE_URL}/api/v1/appraisals/{appraisal_id}/submit")
    r = client.post(f"{BASE_URL}/api/v1/appraisals/{appraisal_id}/approve")
    assert r.status_code == 200, r.text
    return r.json()


def _reject(client, appraisal_id, reason="not enough margin"):
    client.post(f"{BASE_URL}/api/v1/appraisals/{appraisal_id}/submit")
    r = client.post(
        f"{BASE_URL}/api/v1/appraisals/{appraisal_id}/reject",
        json={"reason": reason},
    )
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------------------------------------------------------
# H.2 — Migration 0022 schema sanity
# --------------------------------------------------------------------------

class TestMigration0022:
    def test_all_three_tables_exist(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name IN "
                "('appraisal_revisions','appraisal_scenarios','appraisal_decision_log')"
            )).all()
        assert {r[0] for r in rows} == {
            "appraisal_revisions", "appraisal_scenarios", "appraisal_decision_log",
        }

    def test_new_enum_values_present(self, db_engine):
        with db_engine.connect() as c:
            reasons = c.execute(text(
                "SELECT unnest(enum_range(NULL::appraisal_revision_reason_enum))::text"
            )).scalars().all()
            decisions = c.execute(text(
                "SELECT unnest(enum_range(NULL::decision_type_enum))::text"
            )).scalars().all()
        assert set(reasons) == {
            "GDV_Updated", "Costs_Updated", "Planning_Change",
            "Finance_Terms_Change", "Market_Change", "Scope_Change",
            "Error_Correction", "Other",
        }
        assert set(decisions) == {
            "Go", "No_Go", "Defer", "Request_Revision",
            "Conditional_Go", "Correction",
        }

    def test_system_config_nudge_threshold_seeded(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text(
                "SELECT config_value, value_type::text, category::text "
                "FROM system_config "
                "WHERE config_key='appraisal_decisions_required_threshold'"
            )).first()
        assert row is not None
        assert row[0] == "3"
        assert row[1] == "Integer"
        assert row[2] == "Appraisal"


# --------------------------------------------------------------------------
# H.7 — Decision-log immutability triggers (verified at DB layer)
# --------------------------------------------------------------------------

class TestDecisionLogImmutability:
    def test_update_raises(self, db_engine, admin, project):
        """A raw UPDATE on appraisal_decision_log MUST be blocked."""
        a = _create_appraisal(admin, project["id"], name="Immutable update")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Proceed with the scheme as modelled.",
            },
        )
        assert r.status_code == 201, r.text
        decision_id = r.json()["id"]
        with db_engine.begin() as c:
            with pytest.raises(Exception) as exc:
                c.execute(text(
                    "UPDATE appraisal_decision_log SET decision_rationale='tampered' "
                    "WHERE id=:i"
                ), {"i": decision_id})
        assert "append-only" in str(exc.value).lower() or "forbidden" in str(exc.value).lower()

    def test_delete_raises(self, db_engine, admin, project):
        a = _create_appraisal(admin, project["id"], name="Immutable delete")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Defer",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "More analysis required before committing.",
            },
        )
        assert r.status_code == 201
        decision_id = r.json()["id"]
        with db_engine.begin() as c:
            with pytest.raises(Exception) as exc:
                c.execute(text(
                    "DELETE FROM appraisal_decision_log WHERE id=:i"
                ), {"i": decision_id})
        assert "append-only" in str(exc.value).lower() or "forbidden" in str(exc.value).lower()


# --------------------------------------------------------------------------
# H.6 — Scenario parent-validation trigger
# --------------------------------------------------------------------------

class TestScenarioParentTrigger:
    def test_parent_must_be_base(self, db_engine, admin, project):
        """Inserting a scenario with parent pointing at non-Base → raises."""
        base = _create_appraisal(admin, project["id"], name="Trigger base")
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Upside",
                  "scenario_description": "Optimistic sales upside."},
        )
        assert r.status_code == 201, r.text
        up_id = r.json()["appraisal"]["id"]
        # Try to insert a new scenario row whose parent is the Upside (non-Base).
        with db_engine.begin() as c:
            gid = c.execute(text("SELECT appraisal_group_id FROM appraisals "
                                 "WHERE id=:i"), {"i": up_id}).scalar()
            uid = c.execute(text("SELECT id FROM users "
                                 "WHERE email=:e"),
                            {"e": ADMIN_EMAIL}).scalar()
            with pytest.raises(Exception) as exc:
                c.execute(text(
                    "INSERT INTO appraisal_scenarios "
                    "(id, appraisal_group_id, scenario_appraisal_id, "
                    " parent_scenario_appraisal_id, scenario_label, "
                    " scenario_description, created_by_user_id) "
                    "VALUES (gen_random_uuid(), :gid, :sid, :pid, "
                    " 'Downside', 'Pessimistic alt', :uid)"
                ), {"gid": gid, "sid": up_id, "pid": up_id, "uid": uid})
        assert "base" in str(exc.value).lower()


# --------------------------------------------------------------------------
# H.4 — /new-version endpoint
# --------------------------------------------------------------------------

class TestNewVersionEndpoint:
    def test_from_approved_creates_revision(self, admin, db_engine, project):
        a = _create_appraisal(admin, project["id"], name="NewVersion Approved")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={
                "revision_reason": "GDV_Updated",
                "summary_of_changes": "Bump sale prices after market survey.",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        new_app = body["appraisal"]
        rev = body["revision"]
        assert new_app["status"] == "Draft"
        assert new_app["version_number"] == a["version_number"] + 1
        assert new_app["is_current"] is True
        # Old row: Superseded, not current.
        orig = admin.get(f"{BASE_URL}/api/v1/appraisals/{a['id']}").json()
        assert orig["status"] == "Superseded"
        assert orig["is_current"] is False
        # Revision row wired.
        assert rev["from_version"] == a["version_number"]
        assert rev["to_version"] == new_app["version_number"]
        assert rev["appraisal_id_from"] == a["id"]
        assert rev["appraisal_id_to"] == new_app["id"]
        assert rev["revision_reason"] == "GDV_Updated"
        assert len(rev["summary_of_changes"]) >= 10

    def test_from_rejected_creates_revision(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="NewVersion Rejected")
        _reject(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={
                "revision_reason": "Costs_Updated",
                "summary_of_changes": "Refresh build cost inputs and re-model.",
            },
        )
        assert r.status_code == 201, r.text
        new_app = r.json()["appraisal"]
        assert new_app["status"] == "Draft"
        # From Rejected, the source should NOT flip to Superseded (only
        # Approved does; Rejected stays Rejected).
        orig = admin.get(f"{BASE_URL}/api/v1/appraisals/{a['id']}").json()
        assert orig["status"] == "Rejected"
        assert orig["is_current"] is False

    def test_from_draft_blocked(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="NewVersion Draft")
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={
                "revision_reason": "GDV_Updated",
                "summary_of_changes": "Should be blocked for Draft source.",
            },
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "APPRAISAL_NOT_VERSIONABLE"

    def test_summary_too_short_422(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="NewVersion short")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated", "summary_of_changes": "too"},
        )
        assert r.status_code in (400, 422)

    def test_invalid_revision_reason(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="NewVersion bad reason")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "Nonsense",
                  "summary_of_changes": "This reason does not exist in the enum."},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_REVISION_REASON"

    def test_source_not_current_blocked(self, admin, project):
        """Create a chain A→B (both Approved pathway). Then try /new-version
        from A again — should 400 with SOURCE_NOT_CURRENT."""
        a = _create_appraisal(admin, project["id"], name="Chain source")
        _approve(admin, a["id"])
        r1 = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated",
                  "summary_of_changes": "First version bump to extract stale flag."},
        )
        assert r1.status_code == 201
        # a is now Superseded + not current. Even if it were Approved it's
        # not current, so /new-version should refuse. But because the
        # status is now Superseded, the status check fires first with
        # APPRAISAL_NOT_VERSIONABLE (the more informative of the two).
        r2 = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated",
                  "summary_of_changes": "Should be blocked — a is superseded."},
        )
        assert r2.status_code == 409
        assert r2.json()["detail"]["code"] == "APPRAISAL_NOT_VERSIONABLE"

    def test_revisions_lineage_endpoint(self, admin, fresh_project):
        a = _create_appraisal(admin, fresh_project["id"], name="Lineage")
        _approve(admin, a["id"])
        r1 = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated",
                  "summary_of_changes": "Round one of cost revisions."},
        )
        new1 = r1.json()["appraisal"]
        _approve(admin, new1["id"])
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{new1['id']}/new-version",
            json={"revision_reason": "Costs_Updated",
                  "summary_of_changes": "Round two of cost revisions."},
        )
        lineage = admin.get(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/revisions"
        ).json()
        assert len(lineage["appraisals"]) == 3
        assert len(lineage["revisions"]) == 2

    def test_revisions_deltas_populated_on_recompute(self, admin, fresh_project):
        a = _create_appraisal(admin, fresh_project["id"], name="Deltas")
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/units",
            json={"unit_label": "Base Type", "unit_type": "Detached",
                  "tenure": "Open_Market", "quantity": 2,
                  "price_per_unit": "400000",
                  "build_cost_per_unit": "200000"},
        )
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated",
                  "summary_of_changes": "Add a unit and re-run KPIs."},
        )
        new = r.json()["appraisal"]
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{new['id']}/units",
            json={"unit_label": "Extra", "unit_type": "Semi_Detached",
                  "tenure": "Open_Market", "quantity": 1,
                  "price_per_unit": "350000",
                  "build_cost_per_unit": "175000"},
        )
        lineage = admin.get(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/revisions"
        ).json()
        assert len(lineage["revisions"]) == 1
        rev = lineage["revisions"][0]
        assert Decimal(rev["delta_gdv"]) == Decimal("350000.00")

    def test_readonly_forbidden(self, readonly, admin, project):
        a = _create_appraisal(admin, project["id"], name="Readonly blocked")
        _approve(admin, a["id"])
        r = readonly.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated",
                  "summary_of_changes": "Read-only has no appraisals.edit."},
        )
        assert r.status_code == 403


# --------------------------------------------------------------------------
# H.5 — /reopen final form (2.3 C2)
# --------------------------------------------------------------------------

class TestReopenFinalForm:
    def test_reopen_rejected_toggles(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Reopen rejected")
        _reject(admin, a["id"])
        r = admin.post(f"{BASE_URL}/api/v1/appraisals/{a['id']}/reopen")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["status"] == "Reopened"
        assert b["rejection_reason"] is None
        assert b["is_current"] is True
        assert b["version_number"] == a["version_number"]

    def test_reopen_approved_toggles_no_clone(self, admin, project):
        """Approved → Reopened is a toggle, NO clone (2.3 C2 final form)."""
        a = _create_appraisal(admin, project["id"], name="Reopen approved")
        _approve(admin, a["id"])
        r = admin.post(f"{BASE_URL}/api/v1/appraisals/{a['id']}/reopen")
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["id"] == a["id"]
        assert b["status"] == "Reopened"
        assert b["is_current"] is True
        assert b["version_number"] == a["version_number"]

    def test_reopen_draft_blocked(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Reopen draft")
        r = admin.post(f"{BASE_URL}/api/v1/appraisals/{a['id']}/reopen")
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "NOT_REOPENABLE"

    def test_reopen_non_current_blocked(self, admin, project):
        """Chain A→B via /new-version makes A not current. /reopen on A fires
        NOT_REOPENABLE because A is now Superseded."""
        a = _create_appraisal(admin, project["id"], name="Reopen non-current")
        _approve(admin, a["id"])
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated",
                  "summary_of_changes": "Bump to make a non-current."},
        )
        r = admin.post(f"{BASE_URL}/api/v1/appraisals/{a['id']}/reopen")
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "NOT_REOPENABLE"


# --------------------------------------------------------------------------
# H.6 — Scenarios
# --------------------------------------------------------------------------

class TestScenarios:
    def test_create_upside_from_base(self, admin, fresh_project):
        base = _create_appraisal(admin, fresh_project["id"], name="Scenarios base")
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Upside",
                  "scenario_description": "Upside sales scenario modelling."},
        )
        assert r.status_code == 201, r.text
        new = r.json()["appraisal"]
        scen = r.json()["scenario"]
        assert new["scenario"] == "Upside"
        assert new["version_number"] == 1
        assert new["is_current"] is True
        # Base is ALSO still current — different (project, scenario) tuple.
        base_state = admin.get(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}"
        ).json()
        assert base_state["is_current"] is True
        assert base_state["scenario"] == "Base"
        assert scen["scenario_label"] == "Upside"
        assert scen["parent_scenario_appraisal_id"] == base["id"]

    def test_scenario_description_too_short_422(self, admin, fresh_project):
        base = _create_appraisal(admin, fresh_project["id"], name="Desc short")
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Upside", "scenario_description": "x"},
        )
        assert r.status_code in (400, 422)

    def test_cannot_create_base_scenario(self, admin, fresh_project):
        base = _create_appraisal(admin, fresh_project["id"], name="Base forbidden")
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Base",
                  "scenario_description": "Cannot spawn another Base."},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_SCENARIO_LABEL"

    def test_duplicate_scenario_label(self, admin, fresh_project):
        base = _create_appraisal(admin, fresh_project["id"], name="Dup scenarios")
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Downside",
                  "scenario_description": "First downside scenario."},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Downside",
                  "scenario_description": "Second attempt should fail."},
        )
        assert r.status_code == 409
        assert r.json()["detail"]["code"] == "SCENARIO_LABEL_EXISTS"

    def test_scenario_from_non_base_blocked(self, admin, fresh_project):
        """/scenarios on an Upside appraisal should return NOT_BASE_APPRAISAL."""
        base = _create_appraisal(admin, fresh_project["id"], name="Non-base source")
        r0 = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Upside",
                  "scenario_description": "A genuine upside scenario."},
        )
        assert r0.status_code == 201
        upside_id = r0.json()["appraisal"]["id"]
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{upside_id}/scenarios",
            json={"scenario_label": "Sensitivity",
                  "scenario_description": "Sensitivity off an upside — forbidden."},
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "NOT_BASE_APPRAISAL"

    def test_list_group_scenarios_ordered(self, admin, fresh_project):
        base = _create_appraisal(admin, fresh_project["id"], name="List ordered")
        group_id = base["appraisal_group_id"]
        for label, desc in [
            ("Sensitivity", "Sensitivity analysis modelling scenario."),
            ("Upside", "Optimistic upside market modelling."),
            ("Downside", "Pessimistic downside market modelling."),
        ]:
            r = admin.post(
                f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
                json={"scenario_label": label, "scenario_description": desc},
            )
            assert r.status_code == 201, r.text
        lst = admin.get(
            f"{BASE_URL}/api/v1/appraisal-groups/{group_id}/scenarios"
        ).json()
        labels = [s["scenario_label"] for s in lst["scenarios"]]
        assert labels == ["Base", "Upside", "Downside", "Sensitivity"]

    def test_comparator_payload_shape(self, admin, fresh_project):
        base = _create_appraisal(admin, fresh_project["id"], name="Comparator base")
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/units",
            json={"unit_label": "U", "unit_type": "Detached",
                  "tenure": "Open_Market", "quantity": 1,
                  "price_per_unit": "500000",
                  "build_cost_per_unit": "250000"},
        )
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Upside",
                  "scenario_description": "Upside scenario for comparator."},
        )
        cmp = admin.get(
            f"{BASE_URL}/api/v1/appraisal-groups/{base['appraisal_group_id']}/comparator"
        ).json()
        assert cmp["appraisal_group_id"] == base["appraisal_group_id"]
        labels = [s["scenario_label"] for s in cmp["scenarios"]]
        assert labels == ["Base", "Upside"]
        base_row = cmp["scenarios"][0]
        assert base_row["total_units"] == 1
        assert Decimal(base_row["gdv_total"]) == Decimal("500000.00")
        assert "passes_hurdle" in base_row

    def test_readonly_cannot_create(self, readonly, admin, fresh_project):
        base = _create_appraisal(admin, fresh_project["id"], name="RO scen")
        r = readonly.post(
            f"{BASE_URL}/api/v1/appraisals/{base['id']}/scenarios",
            json={"scenario_label": "Upside",
                  "scenario_description": "Blocked for readonly user."},
        )
        assert r.status_code == 403


# --------------------------------------------------------------------------
# H.7 — Decisions
# --------------------------------------------------------------------------

class TestDecisions:
    def test_go_decision_success(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec Go")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Margins clear the hurdle; proceed.",
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["decision_type"] == "Go"
        assert body["appraisal_id"] == a["id"]
        assert body["decision_maker_user_id"]

    def test_conditional_go_requires_conditions(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec CondGo missing")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Conditional_Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Conditional go without conditions.",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "MISSING_CONDITIONS"

    def test_conditional_go_happy_path(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec CondGo ok")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Conditional_Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Proceed subject to planning consent.",
                "conditions": "Planning consent by Q2; build cost re-tendered.",
            },
        )
        assert r.status_code == 201

    def test_conditions_not_allowed_for_go(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec Go+conditions")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Unconditional proceed — margins clear.",
                "conditions": "These shouldn't be here.",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "CONDITIONS_NOT_ALLOWED"

    def test_future_dated_rejected(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec future")
        _approve(admin, a["id"])
        future = (datetime.now(ZoneInfo("Europe/London")).date()
                  + timedelta(days=5)).isoformat()
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Defer",
                "decision_date": future,
                "decision_rationale": "Future decisions should be blocked.",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "FUTURE_DATED_DECISION"

    def test_version_mismatch(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec ver mismatch")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": 99,
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Version should not match current.",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "INVALID_DECISION_VERSION"

    def test_cannot_log_on_non_current(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec stale")
        _approve(admin, a["id"])
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/new-version",
            json={"revision_reason": "GDV_Updated",
                  "summary_of_changes": "Bump to make original stale."},
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Stale version must block decision logging.",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "DECISION_ON_NON_CURRENT_APPRAISAL"

    def test_correction_requires_reference(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec correction no-ref")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Correction",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Correction without reference is invalid.",
            },
        )
        assert r.status_code == 400
        assert r.json()["detail"]["code"] == "MISSING_CORRECTION_REFERENCE"

    def test_correction_happy_path(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec correction ok")
        _approve(admin, a["id"])
        first = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Defer",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Initial defer that will be corrected.",
            },
        )
        assert first.status_code == 201
        first_id = first.json()["id"]
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Correction",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Correcting the previous decision record.",
                "correction_of_decision_id": first_id,
            },
        )
        assert r.status_code == 201, r.text

    def test_decision_maker_user_id_rejected(self, admin, project):
        """Client cannot proxy decisions — extra='forbid' on payload."""
        a = _create_appraisal(admin, project["id"], name="Dec proxy forbidden")
        _approve(admin, a["id"])
        r = admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Client tries to proxy decision maker.",
                "decision_maker_user_id": str(uuid.uuid4()),
            },
        )
        assert r.status_code == 422

    def test_list_decisions_ordering(self, admin, project):
        a = _create_appraisal(admin, project["id"], name="Dec list")
        _approve(admin, a["id"])
        yday = (date.today() - timedelta(days=2)).isoformat()
        today = date.today().isoformat()
        for d, t in [(yday, "Defer"), (today, "Go")]:
            admin.post(
                f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
                json={
                    "appraisal_version": a["version_number"],
                    "decision_type": t,
                    "decision_date": d,
                    "decision_rationale": f"Decision on {d} with type {t}.",
                },
            )
        r = admin.get(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions"
        ).json()
        assert r["count"] == 2
        # Most recent decision_date first.
        assert r["items"][0]["decision_type"] == "Go"
        assert r["items"][1]["decision_type"] == "Defer"

    def test_readonly_forbidden_on_approve_gated(self, readonly, admin, project):
        """Read-only holds neither appraisals.edit nor appraisals.approve.
        /decisions is gated on appraisals.approve per spec."""
        a = _create_appraisal(admin, project["id"], name="Dec perm")
        _approve(admin, a["id"])
        r = readonly.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Readonly must not log decisions.",
            },
        )
        assert r.status_code in (403, 404)


# --------------------------------------------------------------------------
# H.8 — Nudge
# --------------------------------------------------------------------------

class TestNudge:
    def test_no_current_approved_base(self, admin, fresh_project):
        _create_appraisal(admin, fresh_project["id"], name="Nudge no-approved")
        r = admin.get(f"{BASE_URL}/api/v1/projects/{fresh_project['id']}/nudge")
        assert r.status_code == 200
        body = r.json()
        assert body["should_show"] is False
        assert body["current_appraisal_id"] is None
        assert body["distinct_decision_makers"] == 0

    def test_nudge_under_threshold(self, admin, fresh_project):
        a = _create_appraisal(admin, fresh_project["id"], name="Nudge under")
        _approve(admin, a["id"])
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Go",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "One of three deciders is in.",
            },
        )
        r = admin.get(f"{BASE_URL}/api/v1/projects/{fresh_project['id']}/nudge")
        body = r.json()
        assert body["should_show"] is True
        assert body["threshold"] == 3
        assert body["distinct_decision_makers"] == 1
        assert body["actor_has_decided"] is True

    def test_nudge_at_threshold(self, admin, director, fresh_project, db_engine):
        a = _create_appraisal(admin, fresh_project["id"], name="Nudge threshold")
        _approve(admin, a["id"])
        for client, reason in [
            (admin, "Admin votes Go on the Approved Base."),
            (director, "Director also votes Go — margins look good."),
        ]:
            client.post(
                f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
                json={
                    "appraisal_version": a["version_number"],
                    "decision_type": "Go",
                    "decision_date": date.today().isoformat(),
                    "decision_rationale": reason,
                },
            )
        with db_engine.begin() as c:
            fin_uid = c.execute(text(
                "SELECT id FROM users WHERE email=:e"
            ), {"e": FINANCE_EMAIL}).scalar()
            c.execute(text(
                "INSERT INTO appraisal_decision_log "
                "(id, appraisal_id, appraisal_version, decision_type, "
                " decision_maker_user_id, decision_date, decision_rationale, "
                " supporting_documents) "
                "VALUES (gen_random_uuid(), :aid, :ver, 'Go', :uid, :d, "
                " 'Finance agrees with the Go vote — seed row', '[]'::jsonb)"
            ), {"aid": a["id"], "ver": a["version_number"],
                "uid": fin_uid, "d": date.today().isoformat()})
        r = admin.get(f"{BASE_URL}/api/v1/projects/{fresh_project['id']}/nudge")
        body = r.json()
        assert body["distinct_decision_makers"] == 3
        assert body["should_show"] is False

    def test_nudge_excludes_non_core_types(self, admin, fresh_project):
        a = _create_appraisal(admin, fresh_project["id"], name="Nudge excludes")
        _approve(admin, a["id"])
        admin.post(
            f"{BASE_URL}/api/v1/appraisals/{a['id']}/decisions",
            json={
                "appraisal_version": a["version_number"],
                "decision_type": "Request_Revision",
                "decision_date": date.today().isoformat(),
                "decision_rationale": "Request_Revision does not count.",
            },
        )
        r = admin.get(f"{BASE_URL}/api/v1/projects/{fresh_project['id']}/nudge")
        body = r.json()
        assert body["distinct_decision_makers"] == 0
        assert body["actor_has_decided"] is False

    def test_readonly_can_view_nudge(self, readonly, admin, fresh_project):
        _create_appraisal(admin, fresh_project["id"], name="Nudge RO")
        r = readonly.get(
            f"{BASE_URL}/api/v1/projects/{fresh_project['id']}/nudge"
        )
        assert r.status_code == 200
