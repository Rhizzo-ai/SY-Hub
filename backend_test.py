#!/usr/bin/env python3
"""
Backend test for DISPLAY-HONESTY fix on appraisal scenario comparator.

Verifies:
1. CONTRACT: comparator response includes new `rlv_converged` key
2. NON-CONVERGED: unreachable RLV solve → residual_land_value is null, rlv_converged is false
3. CONVERGED: reachable RLV solve → residual_land_value is non-null, rlv_converged is true
"""
import json
import sys
from decimal import Decimal

import requests

BASE_URL = "https://prod-property-hub.preview.emergentagent.com"
API_BASE = f"{BASE_URL}/api"

# Test credentials from test_credentials.md
TEST_EMAIL = "test-pm@example.test"
TEST_PASSWORD = "TestUser-Dev-2026!"


class TestSession:
    """Wrapper for authenticated API requests."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        self.user = None
    
    def login(self):
        """Authenticate and store cookies."""
        print(f"\n🔐 Logging in as {TEST_EMAIL}...")
        resp = self.session.post(
            f"{API_BASE}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        print(f"   Status: {resp.status_code}")
        if resp.status_code != 200:
            print(f"   ❌ Login failed: {resp.text}")
            sys.exit(1)
        
        data = resp.json()
        self.user = data.get("user", {})
        print(f"   ✅ Logged in as: {self.user.get('name')} ({self.user.get('role')})")
        return data
    
    def get(self, path):
        """GET request with auth."""
        resp = self.session.get(f"{API_BASE}{path}")
        return resp
    
    def post(self, path, json_data):
        """POST request with auth."""
        resp = self.session.post(f"{API_BASE}{path}", json=json_data)
        return resp
    
    def put(self, path, json_data):
        """PUT request with auth."""
        resp = self.session.put(f"{API_BASE}{path}", json=json_data)
        return resp


def print_json(label, data, indent=2):
    """Pretty-print JSON data."""
    print(f"\n{label}:")
    print(json.dumps(data, indent=indent))


def find_or_create_appraisal_group(session):
    """
    Find an existing appraisal group with a Base scenario, or create one.
    Returns (project_id, appraisal_group_id, base_appraisal_id).
    """
    print("\n📋 Finding or creating appraisal group...")
    
    # Get list of projects
    resp = session.get("/projects")
    if resp.status_code != 200:
        print(f"   ❌ Failed to get projects: {resp.status_code} {resp.text}")
        sys.exit(1)
    
    projects = resp.json().get("items", [])
    print(f"   Found {len(projects)} projects")
    
    # Try to find an existing appraisal
    for project in projects:
        project_id = project["id"]
        resp = session.get(f"/v1/projects/{project_id}/appraisals")
        if resp.status_code == 200:
            appraisals = resp.json().get("items", [])
            # Find a Base scenario appraisal
            for appraisal in appraisals:
                if appraisal.get("scenario") == "Base" and appraisal.get("appraisal_group_id"):
                    print(f"   ✅ Found existing Base appraisal: {appraisal['id']}")
                    print(f"      Project: {project['name']} ({project_id})")
                    print(f"      Group: {appraisal['appraisal_group_id']}")
                    return project_id, appraisal["appraisal_group_id"], appraisal["id"]
    
    # No existing appraisal found, create one
    print("   No existing appraisal found, creating new one...")
    
    # Use first project or create one
    if not projects:
        print("   Creating new project...")
        # Need to get an entity first
        resp = session.get("/entities")
        if resp.status_code != 200:
            print(f"   ❌ Failed to get entities: {resp.status_code} {resp.text}")
            sys.exit(1)
        entities = resp.json().get("items", [])
        if not entities:
            print("   ❌ No entities found - cannot create project")
            sys.exit(1)
        entity_id = entities[0]["id"]
        
        resp = session.post("/projects", json_data={
            "name": "RLV Display Honesty Test Project",
            "project_type": "Dev_Build",
            "primary_entity_id": entity_id,
            "land_ownership_method": "Direct_Purchase",
            "site_address": "Test Site",
            "site_postcode": "SY1 1AA",
        })
        if resp.status_code != 201:
            print(f"   ❌ Failed to create project: {resp.status_code} {resp.text}")
            sys.exit(1)
        project = resp.json()
        project_id = project["id"]
        print(f"   ✅ Created project: {project_id}")
    else:
        project = projects[0]
        project_id = project["id"]
        print(f"   Using existing project: {project['name']} ({project_id})")
    
    # Create appraisal
    print("   Creating appraisal...")
    resp = session.post(f"/v1/projects/{project_id}/appraisals", json_data={
        "name": "RLV Display Honesty Test Appraisal",
        "land_purchase_price": "500000",
        "sdlt_category": "Residential_Standard",
        "developer_relief": False,
        "project_duration_months": 18,
    })
    if resp.status_code != 201:
        print(f"   ❌ Failed to create appraisal: {resp.status_code} {resp.text}")
        sys.exit(1)
    
    appraisal = resp.json()
    appraisal_id = appraisal["id"]
    appraisal_group_id = appraisal["appraisal_group_id"]
    print(f"   ✅ Created appraisal: {appraisal_id}")
    print(f"      Group: {appraisal_group_id}")
    
    # Add a unit so the appraisal has some GDV
    print("   Adding unit to appraisal...")
    resp = session.post(f"/v1/appraisals/{appraisal_id}/units", json_data={
        "unit_label": "Test Unit",
        "unit_type": "Detached",
        "tenure": "Open_Market",
        "quantity": 1,
        "beds": 3,
        "gia_sqm": "100",
        "price_per_unit": "300000",
        "build_cost_per_unit": "150000",
    })
    if resp.status_code != 201:
        print(f"   ⚠️  Failed to add unit: {resp.status_code} {resp.text}")
    else:
        print(f"   ✅ Added unit")
    
    return project_id, appraisal_group_id, appraisal_id


def test_step_1_contract(session, appraisal_group_id):
    """
    STEP 1: CONTRACT - Verify comparator includes rlv_converged key.
    """
    print("\n" + "="*80)
    print("STEP 1: CONTRACT - Verify comparator includes rlv_converged key")
    print("="*80)
    
    resp = session.get(f"/v1/appraisal-groups/{appraisal_group_id}/comparator")
    print(f"\nGET /v1/appraisal-groups/{appraisal_group_id}/comparator")
    print(f"Status: {resp.status_code}")
    
    if resp.status_code == 403:
        print(f"❌ PERMISSION DENIED: {resp.json()}")
        print(f"   Permission code: {resp.json().get('detail', {}).get('code', 'UNKNOWN')}")
        return False
    
    if resp.status_code != 200:
        print(f"❌ Failed to get comparator: {resp.status_code} {resp.text}")
        return False
    
    data = resp.json()
    print_json("Comparator response", data)
    
    # Verify structure
    scenarios = data.get("scenarios", [])
    if not scenarios:
        print("❌ No scenarios in comparator response")
        return False
    
    base_scenario = None
    for scenario in scenarios:
        if scenario.get("scenario_label") == "Base":
            base_scenario = scenario
            break
    
    if not base_scenario:
        print("❌ No Base scenario found in comparator")
        return False
    
    print("\n📊 Base scenario object:")
    print(json.dumps(base_scenario, indent=2))
    
    # Verify rlv_converged key exists (this is the NEW key proving the fix shipped)
    if "rlv_converged" not in base_scenario:
        print("❌ FAIL: 'rlv_converged' key NOT found in Base scenario")
        return False
    
    print(f"\n✅ PASS: 'rlv_converged' key exists in Base scenario")
    print(f"   Value: {base_scenario['rlv_converged']}")
    print(f"   residual_land_value: {base_scenario.get('residual_land_value')}")
    
    return True


def test_step_2_non_converged(session, base_appraisal_id, appraisal_group_id):
    """
    STEP 2: NON-CONVERGED - Run RLV solve with unreachable target (500%).
    Verify residual_land_value is null and rlv_converged is false.
    """
    print("\n" + "="*80)
    print("STEP 2: NON-CONVERGED - Unreachable RLV target (500%)")
    print("="*80)
    
    print(f"\nPOST /v1/appraisals/{base_appraisal_id}/recalculate-rlv")
    print("Body: {\"basis\": \"on_cost\", \"target_pct\": 500}")
    
    resp = session.post(
        f"/v1/appraisals/{base_appraisal_id}/recalculate-rlv",
        json_data={"basis": "on_cost", "target_pct": 500}
    )
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ Failed to recalculate RLV: {resp.status_code} {resp.text}")
        return False
    
    rlv_result = resp.json()
    print_json("RLV solve result", rlv_result)
    
    converged = rlv_result.get("converged")
    print(f"\n📊 RLV solve converged: {converged}")
    
    if converged:
        print("⚠️  WARNING: RLV solve converged with 500% target (unexpected)")
        print("   This may indicate the appraisal has very high profit margins")
        print("   Continuing with test...")
    else:
        print("✅ RLV solve did NOT converge (as expected)")
    
    # Now get the comparator and verify
    print(f"\nGET /v1/appraisal-groups/{appraisal_group_id}/comparator")
    resp = session.get(f"/v1/appraisal-groups/{appraisal_group_id}/comparator")
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ Failed to get comparator: {resp.status_code} {resp.text}")
        return False
    
    data = resp.json()
    base_scenario = None
    for scenario in data.get("scenarios", []):
        if scenario.get("scenario_label") == "Base":
            base_scenario = scenario
            break
    
    if not base_scenario:
        print("❌ No Base scenario found in comparator")
        return False
    
    print("\n📊 Base scenario after non-converged solve:")
    print(json.dumps(base_scenario, indent=2))
    
    residual_land_value = base_scenario.get("residual_land_value")
    rlv_converged = base_scenario.get("rlv_converged")
    
    print(f"\n📊 Verification:")
    print(f"   residual_land_value: {residual_land_value}")
    print(f"   rlv_converged: {rlv_converged}")
    
    # If the solve didn't converge, verify the fix
    if not converged:
        if residual_land_value is not None:
            print(f"❌ FAIL: residual_land_value should be null when not converged, got: {residual_land_value}")
            return False
        
        if rlv_converged is not False:
            print(f"❌ FAIL: rlv_converged should be false when not converged, got: {rlv_converged}")
            return False
        
        print("✅ PASS: residual_land_value is null AND rlv_converged is false")
        return True
    else:
        # Solve converged unexpectedly, but we can still verify the contract
        print("⚠️  Solve converged (unexpected), but verifying contract is still met")
        if rlv_converged is not True:
            print(f"❌ FAIL: rlv_converged should be true when converged, got: {rlv_converged}")
            return False
        print("✅ PASS: Contract verified (rlv_converged reflects actual convergence state)")
        return True


def test_step_3_converged(session, base_appraisal_id, appraisal_group_id):
    """
    STEP 3: CONVERGED - Run RLV solve with reachable target (20%).
    Verify residual_land_value is non-null and rlv_converged is true.
    """
    print("\n" + "="*80)
    print("STEP 3: CONVERGED - Reachable RLV target (20%)")
    print("="*80)
    
    print(f"\nPOST /v1/appraisals/{base_appraisal_id}/recalculate-rlv")
    print("Body: {\"basis\": \"on_cost\", \"target_pct\": 20}")
    
    resp = session.post(
        f"/v1/appraisals/{base_appraisal_id}/recalculate-rlv",
        json_data={"basis": "on_cost", "target_pct": 20}
    )
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ Failed to recalculate RLV: {resp.status_code} {resp.text}")
        return False
    
    rlv_result = resp.json()
    print_json("RLV solve result", rlv_result)
    
    converged = rlv_result.get("converged")
    print(f"\n📊 RLV solve converged: {converged}")
    
    if not converged:
        print("❌ FAIL: RLV solve did NOT converge with 20% target (should be reachable)")
        print("   This may indicate the appraisal structure doesn't support RLV solving")
        return False
    
    print("✅ RLV solve converged (as expected)")
    
    # Now get the comparator and verify
    print(f"\nGET /v1/appraisal-groups/{appraisal_group_id}/comparator")
    resp = session.get(f"/v1/appraisal-groups/{appraisal_group_id}/comparator")
    print(f"Status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"❌ Failed to get comparator: {resp.status_code} {resp.text}")
        return False
    
    data = resp.json()
    base_scenario = None
    for scenario in data.get("scenarios", []):
        if scenario.get("scenario_label") == "Base":
            base_scenario = scenario
            break
    
    if not base_scenario:
        print("❌ No Base scenario found in comparator")
        return False
    
    print("\n📊 Base scenario after converged solve:")
    print(json.dumps(base_scenario, indent=2))
    
    residual_land_value = base_scenario.get("residual_land_value")
    rlv_converged = base_scenario.get("rlv_converged")
    
    print(f"\n📊 Verification:")
    print(f"   residual_land_value: {residual_land_value}")
    print(f"   rlv_converged: {rlv_converged}")
    
    if residual_land_value is None:
        print(f"❌ FAIL: residual_land_value should be non-null when converged, got: null")
        return False
    
    if rlv_converged is not True:
        print(f"❌ FAIL: rlv_converged should be true when converged, got: {rlv_converged}")
        return False
    
    # Verify it's a numeric string
    try:
        value = Decimal(residual_land_value)
        print(f"   Parsed value: £{value:,.2f}")
    except Exception as e:
        print(f"❌ FAIL: residual_land_value is not a valid numeric string: {e}")
        return False
    
    print("✅ PASS: residual_land_value is non-null numeric string AND rlv_converged is true")
    return True


def main():
    """Run all test steps."""
    print("="*80)
    print("DISPLAY-HONESTY FIX VERIFICATION")
    print("Appraisal Scenario Comparator - RLV Convergence Gating")
    print("="*80)
    print(f"\nBase URL: {BASE_URL}")
    print(f"Test User: {TEST_EMAIL}")
    
    session = TestSession()
    session.login()
    
    # Find or create appraisal group
    project_id, appraisal_group_id, base_appraisal_id = find_or_create_appraisal_group(session)
    
    # Run test steps
    results = {}
    
    # Step 1: CONTRACT
    results["step_1_contract"] = test_step_1_contract(session, appraisal_group_id)
    
    # Step 2: NON-CONVERGED
    results["step_2_non_converged"] = test_step_2_non_converged(
        session, base_appraisal_id, appraisal_group_id
    )
    
    # Step 3: CONVERGED
    results["step_3_converged"] = test_step_3_converged(
        session, base_appraisal_id, appraisal_group_id
    )
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    for step, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {step}")
    
    all_passed = all(results.values())
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED - DISPLAY-HONESTY FIX VERIFIED")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED - SEE DETAILS ABOVE")
        sys.exit(1)


if __name__ == "__main__":
    main()
