"""Single-process: seed → login (auto-enrol MFA) → ensure project + appraisal exist for C3 testing.
Outputs JSON: {project_id, base_appraisal_id, version, scenario_appraisal_ids:{}, group_id, cookies:[...]}"""
import os, sys, json, subprocess, requests, pyotp
from datetime import date, timedelta
from urllib.parse import urlparse

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://sy-hub-ops.preview.emergentagent.com").rstrip("/")
EMAIL = "test-admin@example.test"; PW = "TestUser-Dev-2026!"

def fresh_login():
    s = requests.Session(); s.headers.update({"Content-Type":"application/json"})
    r = s.post(f"{BASE}/api/auth/login", json={"email":EMAIL,"password":PW,"remember_me":False})
    r.raise_for_status(); d=r.json()
    if d.get("mfa_enrollment_required"):
        start = s.post(f"{BASE}/api/auth/mfa/enroll/start"); start.raise_for_status()
        secret = start.json()["secret"]
        c = s.post(f"{BASE}/api/auth/mfa/enroll/confirm",
                   json={"secret":secret,"code":pyotp.TOTP(secret).now()})
        c.raise_for_status()
    elif d.get("mfa_required"):
        # already enrolled — but we don't have cached secret. Re-seed and retry.
        subprocess.run([sys.executable,"scripts/seed_test_users.py"], cwd="/app/backend", check=True, capture_output=True)
        return fresh_login()
    return s

def cookies_for_pw(s):
    host = urlparse(BASE).hostname
    return [{"name":c.name,"value":c.value,"domain":c.domain or host,"path":c.path or "/","secure":True,"sameSite":"Lax"} for c in s.cookies if c.name in ("access_token","refresh_token")]

# Always fresh seed + login for deterministic cookies
subprocess.run([sys.executable,"scripts/seed_test_users.py"], cwd="/app/backend", check=True, capture_output=True)
s = fresh_login()

# Find or create project
r = s.get(f"{BASE}/api/projects?limit=200"); r.raise_for_status()
pjs = r.json() if isinstance(r.json(),list) else r.json().get("items",[])
proj = next((p for p in pjs if p.get("name")=="TEST_C3_E2E"), None)

if not proj:
    e = s.get(f"{BASE}/api/entities"); e.raise_for_status()
    ents = e.json() if isinstance(e.json(),list) else e.json().get("items",[])
    eid = ents[0]["id"]
    payload = {"name":"TEST_C3_E2E","primary_entity_id":eid,"project_type":"Pure_Dev",
        "tenure_mix":"Market_Sale_Only","land_status":"Under_Offer","land_ownership_method":"Direct_Purchase",
        "site_address":"TEST C3 Plot","site_postcode":"SY1 1AA","post_code":"SY1 1AA",
        "project_code":"TC3-001","start_date":str(date.today()),
        "target_completion_date":str(date.today()+timedelta(days=365)),
        "status":"Active","currency":"GBP"}
    c = s.post(f"{BASE}/api/projects", json=payload)
    if c.status_code >= 300:
        sys.stderr.write(f"proj create failed: {c.status_code} {c.text}\n"); sys.exit(1)
    proj = c.json()
pid = proj["id"]

# Find or create Base v1 appraisal
r = s.get(f"{BASE}/api/v1/projects/{pid}/appraisals"); r.raise_for_status()
apr_list = r.json() if isinstance(r.json(),list) else r.json().get("items",[])
base = next((a for a in apr_list if a.get("scenario")=="Base"), None)
if not base:
    c = s.post(f"{BASE}/api/v1/projects/{pid}/appraisals", json={"name":"TEST_C3_Base"})
    if c.status_code >= 300:
        sys.stderr.write(f"appr create failed: {c.status_code} {c.text}\n"); sys.exit(1)
    base = c.json()

aid = base["id"]
# Ensure a unit row
detail = s.get(f"{BASE}/api/v1/appraisals/{aid}").json()
if not detail.get("units"):
    s.post(f"{BASE}/api/v1/appraisals/{aid}/units", json={
        "label":"TEST_Unit","tenure":"Market_Sale","unit_type":"House_3B",
        "quantity":3,"gia_sqm":120,"sale_price_per_unit":500000,"build_cost_per_sqm":2083.33})

print(json.dumps({
    "project_id": pid, "base_appraisal_id": aid,
    "version": base.get("version",1), "state": detail.get("state"),
    "is_current": detail.get("is_current"), "scenario": detail.get("scenario"),
    "group_id": detail.get("appraisal_group_id") or detail.get("group_id"),
    "cookies": cookies_for_pw(s),
}))
