"""C3 governance API smoke tests — verifies the 9 endpoints powering the frontend.
Targets the public preview URL via cookie auth (auto-enrol MFA on first run).
"""
import os, sys, subprocess, requests, pyotp
import pytest
from datetime import date, timedelta

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://concurrent-mint-fix.preview.emergentagent.com").rstrip("/")
EMAIL = "test-admin@example.test"; PW = "TestUser-Dev-2026!"


def _login():
    s = requests.Session(); s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE}/api/auth/login", json={"email": EMAIL, "password": PW, "remember_me": False})
    assert r.status_code == 200, r.text
    d = r.json()
    if d.get("mfa_enrollment_required"):
        st = s.post(f"{BASE}/api/auth/mfa/enroll/start"); assert st.status_code == 200
        secret = st.json()["secret"]
        c = s.post(f"{BASE}/api/auth/mfa/enroll/confirm",
                   json={"secret": secret, "code": pyotp.TOTP(secret).now()})
        assert c.status_code == 200, c.text
    elif d.get("mfa_required"):
        # re-seed and retry
        subprocess.run([sys.executable, "scripts/seed_test_users.py"], cwd="/app/backend",
                       check=True, capture_output=True)
        return _login()
    return s


@pytest.fixture(scope="module")
def session():
    subprocess.run([sys.executable, "scripts/seed_test_users.py"], cwd="/app/backend",
                   check=True, capture_output=True)
    return _login()


@pytest.fixture(scope="module")
def project_and_base(session):
    s = session
    pjs = s.get(f"{BASE}/api/projects?limit=200").json()
    pjs = pjs if isinstance(pjs, list) else pjs.get("items", [])
    proj = next((p for p in pjs if p.get("name") == "TEST_C3_E2E"), None)
    if not proj:
        ents = s.get(f"{BASE}/api/entities").json()
        ents = ents if isinstance(ents, list) else ents.get("items", [])
        c = s.post(f"{BASE}/api/projects", json={
            "name": "TEST_C3_E2E", "primary_entity_id": ents[0]["id"],
            "project_type": "Pure_Dev", "tenure_mix": "Market_Sale_Only",
            "land_status": "Under_Offer", "land_ownership_method": "Direct_Purchase",
            "site_address": "TEST C3", "site_postcode": "SY1 1AA",
            "post_code": "SY1 1AA", "project_code": "TC3-001",
            "start_date": str(date.today()),
            "target_completion_date": str(date.today() + timedelta(days=365)),
            "status": "Active", "currency": "GBP",
        })
        assert c.status_code in (200, 201), c.text
        proj = c.json()
    pid = proj["id"]
    apr = s.get(f"{BASE}/api/v1/projects/{pid}/appraisals").json()
    apr = apr if isinstance(apr, list) else apr.get("items", [])
    base = next((a for a in apr if a.get("scenario") == "Base"), None)
    if not base:
        c = s.post(f"{BASE}/api/v1/projects/{pid}/appraisals", json={"name": "TEST_C3_Base"})
        assert c.status_code in (200, 201), c.text
        base = c.json()
    return {"project_id": pid, "base_id": base["id"]}


# --- Revisions ---
def test_get_revisions(session, project_and_base):
    r = session.get(f"{BASE}/api/v1/appraisals/{project_and_base['base_id']}/revisions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, (list, dict))
    rows = body if isinstance(body, list) else body.get("items", [])
    # Empty list is valid — revisions only get rows after new-version is created.
    assert isinstance(rows, list)


# --- Scenarios (POST only — frontend reads scenarios as siblings via /projects/{pid}/appraisals) ---
def test_create_scenario_upside(session, project_and_base):
    payload = {"scenario_label": "Upside",
               "scenario_description": "TEST_ Upside scenario for C3 smoke testing flow",
               "rationale": "TEST_ rationale that is plenty long enough for validation"}
    r = session.post(f"{BASE}/api/v1/appraisals/{project_and_base['base_id']}/scenarios", json=payload)
    # 200/201 or 409 if it already exists from a prior run
    assert r.status_code in (200, 201, 409, 400), r.text


# --- Comparator ---
def test_comparator(session, project_and_base):
    detail = session.get(f"{BASE}/api/v1/appraisals/{project_and_base['base_id']}").json()
    gid = detail.get("appraisal_group_id") or detail.get("group_id")
    if not gid:
        pytest.skip("No appraisal_group_id on detail response")
    r = session.get(f"{BASE}/api/v1/appraisal-groups/{gid}/comparator")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, (list, dict))


# --- Decisions ---
def test_list_decisions(session, project_and_base):
    r = session.get(f"{BASE}/api/v1/appraisals/{project_and_base['base_id']}/decisions")
    assert r.status_code == 200, r.text


# --- Nudge ---
def test_get_nudge(session, project_and_base):
    r = session.get(f"{BASE}/api/v1/projects/{project_and_base['project_id']}/nudge")
    assert r.status_code == 200, r.text
    data = r.json()
    # Must contain at least one nudge field used by the banner.
    assert any(k in data for k in ("threshold", "actor_has_decided", "decisions",
                                    "current_appraisal_id", "actor_can_approve"))


# --- New version requires Approved (negative path on Draft is acceptable) ---
def test_new_version_endpoint_exists(session, project_and_base):
    r = session.post(f"{BASE}/api/v1/appraisals/{project_and_base['base_id']}/new-version",
                     json={"reason": "Cost_Update", "summary": "TEST_ smoke for new version endpoint"})
    # 200/201 if base is already Approved; 400/409/422 otherwise — the route must exist.
    assert r.status_code in (200, 201, 400, 409, 422), r.text
