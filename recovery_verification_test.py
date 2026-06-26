#!/usr/bin/env python3
"""
Recovery Verification Test
PostgreSQL was wiped and re-provisioned. This script verifies:
1. GET /api/health returns 200 with JSON (not 502/Cloudflare error)
2. Backend origin is serving JSON (not HTML error page)
3. Authenticated path works end-to-end against Postgres
"""

import requests
import json
import sys

BASE_URL = "https://prod-property-hub.preview.emergentagent.com"

# Test credentials from test_credentials.md
TEST_EMAIL = "test-pm@example.test"
TEST_PASSWORD = "TestUser-Dev-2026!"

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_result(test_name, passed, details):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} - {test_name}")
    print(f"Details: {details}\n")

def test_health_endpoint():
    """Test 1: GET /api/health returns 200 with JSON"""
    print_section("TEST 1: Health Endpoint")
    
    try:
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        
        print(f"HTTP Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"Response snippet (first 500 chars):\n{response.text[:500]}\n")
        
        # Check if it's a 502 or Cloudflare error
        if response.status_code == 502:
            print_result("Health Endpoint", False, "Received 502 Bad Gateway - backend origin not reachable")
            return False
        
        # Check if response is HTML (Cloudflare error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            print_result("Health Endpoint", False, "Received HTML error page (likely Cloudflare error)")
            return False
        
        # Check if response is JSON
        if 'application/json' not in content_type:
            print_result("Health Endpoint", False, f"Expected JSON, got Content-Type: {content_type}")
            return False
        
        # Try to parse JSON
        try:
            data = response.json()
            print(f"Parsed JSON: {json.dumps(data, indent=2)}\n")
        except json.JSONDecodeError:
            print_result("Health Endpoint", False, "Response is not valid JSON")
            return False
        
        # Check for 200 status
        if response.status_code != 200:
            print_result("Health Endpoint", False, f"Expected 200, got {response.status_code}")
            return False
        
        # Check for "status" field in JSON
        if "status" not in data:
            print_result("Health Endpoint", False, "JSON response missing 'status' field")
            return False
        
        print_result("Health Endpoint", True, f"Returns 200 with JSON: {data}")
        return True
        
    except requests.exceptions.RequestException as e:
        print_result("Health Endpoint", False, f"Request failed: {str(e)}")
        return False

def test_authentication():
    """Test 2: POST /api/auth/login with test credentials"""
    print_section("TEST 2: Authentication (Login)")
    
    try:
        session = requests.Session()
        
        login_payload = {
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        }
        
        response = session.post(
            f"{BASE_URL}/api/auth/login",
            json=login_payload,
            timeout=10
        )
        
        print(f"HTTP Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"Response snippet (first 500 chars):\n{response.text[:500]}\n")
        
        # Check if it's a 502 or Cloudflare error
        if response.status_code == 502:
            print_result("Authentication", False, "Received 502 Bad Gateway - backend origin not reachable")
            return None
        
        # Check if response is HTML (Cloudflare error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            print_result("Authentication", False, "Received HTML error page (likely Cloudflare error)")
            return None
        
        # Try to parse JSON
        try:
            data = response.json()
            print(f"Parsed JSON: {json.dumps(data, indent=2)}\n")
        except json.JSONDecodeError:
            print_result("Authentication", False, "Response is not valid JSON")
            return None
        
        # Check for successful login (200)
        if response.status_code != 200:
            print_result("Authentication", False, f"Expected 200, got {response.status_code}. Response: {data}")
            return None
        
        # Check for mfa_enrollment_required (should be false for test-pm)
        if data.get("mfa_enrollment_required"):
            print_result("Authentication", False, "MFA enrollment required (unexpected for test-pm@example.test)")
            return None
        
        # Check cookies are set
        cookies = session.cookies.get_dict()
        print(f"Cookies set: {list(cookies.keys())}\n")
        
        print_result("Authentication", True, f"Login successful. User: {data.get('user', {}).get('email', 'N/A')}")
        return session
        
    except requests.exceptions.RequestException as e:
        print_result("Authentication", False, f"Request failed: {str(e)}")
        return None

def test_database_connectivity(session):
    """Test 3: GET /api/projects to verify DB connectivity"""
    print_section("TEST 3: Database Connectivity (GET /api/projects)")
    
    if session is None:
        print_result("Database Connectivity", False, "Skipped - authentication failed")
        return False
    
    try:
        response = session.get(f"{BASE_URL}/api/projects", timeout=10)
        
        print(f"HTTP Status: {response.status_code}")
        print(f"Content-Type: {response.headers.get('Content-Type', 'N/A')}")
        print(f"Response snippet (first 500 chars):\n{response.text[:500]}\n")
        
        # Check if it's a 502/503 or Cloudflare error
        if response.status_code in [502, 503]:
            print_result("Database Connectivity", False, f"Received {response.status_code} - backend/database not reachable")
            return False
        
        # Check if response is HTML (Cloudflare error page)
        content_type = response.headers.get('Content-Type', '')
        if 'text/html' in content_type:
            print_result("Database Connectivity", False, "Received HTML error page (likely Cloudflare error)")
            return False
        
        # Try to parse JSON
        try:
            data = response.json()
            print(f"Parsed JSON (first 1000 chars): {json.dumps(data, indent=2)[:1000]}\n")
        except json.JSONDecodeError:
            print_result("Database Connectivity", False, "Response is not valid JSON")
            return False
        
        # Check for 200 status
        if response.status_code != 200:
            print_result("Database Connectivity", False, f"Expected 200, got {response.status_code}")
            return False
        
        # Check if response is a list or has data
        if isinstance(data, list):
            project_count = len(data)
        elif isinstance(data, dict) and "items" in data:
            project_count = len(data["items"])
        else:
            project_count = "unknown"
        
        print_result("Database Connectivity", True, f"Returns 200 with JSON. Projects found: {project_count}")
        return True
        
    except requests.exceptions.RequestException as e:
        print_result("Database Connectivity", False, f"Request failed: {str(e)}")
        return False

def main():
    print_section("RECOVERY VERIFICATION TEST")
    print(f"Base URL: {BASE_URL}")
    print(f"Test User: {TEST_EMAIL}")
    print(f"Purpose: Verify PostgreSQL recovery and backend health\n")
    
    results = []
    
    # Test 1: Health endpoint
    health_ok = test_health_endpoint()
    results.append(("Health Endpoint", health_ok))
    
    # Test 2: Authentication
    session = test_authentication()
    auth_ok = session is not None
    results.append(("Authentication", auth_ok))
    
    # Test 3: Database connectivity
    db_ok = test_database_connectivity(session)
    results.append(("Database Connectivity", db_ok))
    
    # Summary
    print_section("SUMMARY")
    all_passed = all(result[1] for result in results)
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {test_name}")
    
    print(f"\n{'='*80}")
    if all_passed:
        print("✅ ALL TESTS PASSED - Backend is healthy and database-backed")
        print("PostgreSQL recovery verification: SUCCESS")
        sys.exit(0)
    else:
        print("❌ SOME TESTS FAILED - Backend recovery incomplete")
        print("PostgreSQL recovery verification: FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
