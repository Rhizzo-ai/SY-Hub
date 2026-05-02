"""Find or create TEST_Appraisal_E2E project with a Draft appraisal v3 (or latest Draft).
Outputs JSON: {"project_id", "appraisal_id", "version"}"""
import os, sys, json, requests, subprocess, pyotp
from datetime import date, timedelta
sys.path.insert(0, "/app/test_reports/helpers")
from auth_helper import seed, login_session, BASE

seed()
s = login_session()

# Find TEST_Appraisal_E2E project
r = s.get(f"{BASE}/api/projects?limit=200"); r.raise_for_status()
projects = r.json() if isinstance(r.json(), list) else r.json().get("items", r.json().get("results", []))
proj = next((p for p in projects if p.get("name") == "TEST_Appraisal_E2E"), None)

if not proj:
    # Need to create — get entity
    e = s.get(f"{BASE}/api/entities"); e.raise_for_status()
    ents = e.json() if isinstance(e.json(), list) else e.json().get("items", [])
    entity_id = ents[0]["id"]
    payload = {
        "name": "TEST_Appraisal_E2E",
        "primary_entity_id": entity_id,
        "project_type": "Pure_Dev",
        "tenure_mix": "Market_Sale_Only",
        "land_status": "Under_Offer",
        "land_ownership_method": "Direct_Purchase",
        "site_address": "TEST Plot, TEST Rd",
        "site_postcode": "SY1 1AA",
        "post_code": "SY1 1AA",
        "project_code": "TEST-APR-E2E",
        "start_date": str(date.today()),
        "target_completion_date": str(date.today() + timedelta(days=365)),
        "status": "Active",
        "currency": "GBP",
    }
    c = s.post(f"{BASE}/api/projects", json=payload)
    c.raise_for_status()
    proj = c.json()
pid = proj["id"]

# List appraisals for this project
r = s.get(f"{BASE}/api/v1/projects/{pid}/appraisals"); r.raise_for_status()
apr_list = r.json() if isinstance(r.json(), list) else r.json().get("items", [])

draft = next((a for a in apr_list if a.get("state") == "Draft"), None)
if not draft:
    # Create new version
    c = s.post(f"{BASE}/api/v1/projects/{pid}/appraisals", json={"name": "TEST_Edit_Regression"})
    c.raise_for_status()
    draft = c.json()

# Ensure it has a unit row so live math works
aid = draft["id"]
units_r = s.get(f"{BASE}/api/v1/appraisals/{aid}")
if units_r.status_code == 200:
    full = units_r.json()
    if not full.get("units"):
        s.post(f"{BASE}/api/v1/appraisals/{aid}/units", json={
            "label": "TEST_Unit", "tenure": "Market_Sale", "unit_type": "House_3B",
            "quantity": 3, "gia_sqm": 120, "sale_price_per_unit": 500000,
            "build_cost_per_sqm": 2083.33
        })

print(json.dumps({"project_id": pid, "appraisal_id": aid, "version": draft.get("version", 1)}))
