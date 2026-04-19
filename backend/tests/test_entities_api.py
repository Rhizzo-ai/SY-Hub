"""
Backend API tests for SY Homes Entities module (Prompt 1.1 + 1.2 Auth)
Tests: Health, Meta endpoints, Entities CRUD, Validation, Hierarchy, Insurance alerts
Updated for Prompt 1.2: All entity endpoints now require authentication
"""
import os
import pytest
import requests
from datetime import date, timedelta
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://construction-command-5.preview.emergentagent.com"

# Test data prefix for cleanup
TEST_PREFIX = "TEST_"

# Auth credentials
SUPER_ADMIN_EMAIL = "test-admin@example.test"
SUPER_ADMIN_PASSWORD = "TestUser-Dev-2026!"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    """Get authentication token for super_admin"""
    response = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": SUPER_ADMIN_EMAIL,
        "password": SUPER_ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for requests"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def tenant_id(api_client, auth_headers):
    """Get the seeded tenant ID"""
    response = api_client.get(f"{BASE_URL}/api/meta/tenant", headers=auth_headers)
    assert response.status_code == 200
    return response.json()["id"]


@pytest.fixture(scope="module")
def seeded_entities(api_client, auth_headers):
    """Get the 3 seeded entities"""
    response = api_client.get(f"{BASE_URL}/api/entities", params={"page_size": 100}, headers=auth_headers)
    assert response.status_code == 200
    return response.json()["items"]


@pytest.fixture(scope="module")
def parent_entity_id(seeded_entities):
    """Get SY Homes Ltd (Parent) entity ID"""
    for e in seeded_entities:
        if e["name"] == "SY Homes Ltd":
            return e["id"]
    pytest.fail("SY Homes Ltd not found in seeded entities")


class TestHealthEndpoint:
    """Health check endpoint tests"""
    
    def test_health_returns_200(self, api_client):
        response = api_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        # Updated for Prompt 1.2
        assert data["module"] == "users+rbac"
        assert data["phase"] == "1.2"


class TestMetaEndpoints:
    """Meta endpoints: tenant, enums, insurance-alerts"""
    
    def test_tenant_returns_sy_homes(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/meta/tenant", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "SY Homes"
        # Validate UUID format
        uuid.UUID(data["id"])
        assert "created_at" in data
    
    def test_enums_returns_all_5_enums(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/meta/enums", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Check all 5 enums exist
        assert "entity_types" in data
        assert "vat_schemes" in data
        assert "vat_return_periods" in data
        assert "cis_statuses" in data
        assert "entity_statuses" in data
        
        # Validate expected values
        assert set(data["entity_types"]) == {"Parent", "SPV", "ConstructionCo", "JV_Vehicle", "Other"}
        assert set(data["vat_schemes"]) == {"Standard_Quarterly", "Standard_Monthly", "Cash_Accounting", "Flat_Rate", "Not_Registered"}
        assert set(data["vat_return_periods"]) == {"Jan_Apr_Jul_Oct", "Feb_May_Aug_Nov", "Mar_Jun_Sep_Dec", "Monthly"}
        assert set(data["cis_statuses"]) == {"Contractor", "Subcontractor", "Both", "None"}
        assert set(data["entity_statuses"]) == {"Active", "Dormant", "Struck_off"}


class TestEntitiesListEndpoint:
    """GET /api/entities - List and filter tests"""
    
    def test_list_returns_3_seeded_entities(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/entities", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        
        names = {e["name"] for e in data["items"]}
        assert "SY Homes Ltd" in names
        assert "SY Homes (Shrewsbury) Ltd" in names
        assert "SY Homes (Construction) Ltd" in names
    
    def test_filter_by_entity_type_parent(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/entities", params={"entity_type": "Parent"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "SY Homes Ltd"
        assert data["items"][0]["entity_type"] == "Parent"
    
    def test_filter_by_entity_type_spv(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/entities", params={"entity_type": "SPV"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "SY Homes (Shrewsbury) Ltd"
    
    def test_search_by_name(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/entities", params={"q": "Shrewsbury"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Shrewsbury" in data["items"][0]["name"]
    
    def test_sort_by_name_desc(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/entities", params={"sort": "name", "dir": "desc"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        names = [e["name"] for e in data["items"]]
        assert names == sorted(names, reverse=True)
    
    def test_sort_by_name_asc(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/entities", params={"sort": "name", "dir": "asc"}, headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        names = [e["name"] for e in data["items"]]
        assert names == sorted(names)
    
    def test_invalid_entity_type_filter_returns_400(self, api_client, auth_headers):
        response = api_client.get(f"{BASE_URL}/api/entities", params={"entity_type": "InvalidType"}, headers=auth_headers)
        assert response.status_code == 400


class TestEntityDetailEndpoint:
    """GET /api/entities/{id} - Detail view with hierarchy"""
    
    def test_parent_entity_has_children(self, api_client, auth_headers, parent_entity_id):
        response = api_client.get(f"{BASE_URL}/api/entities/{parent_entity_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data["name"] == "SY Homes Ltd"
        assert data["entity_type"] == "Parent"
        assert data["parent"] is None  # Top-level
        assert len(data["children"]) == 2
        
        child_names = {c["name"] for c in data["children"]}
        assert "SY Homes (Shrewsbury) Ltd" in child_names
        assert "SY Homes (Construction) Ltd" in child_names
    
    def test_child_entity_has_parent(self, api_client, auth_headers, seeded_entities, parent_entity_id):
        # Find Shrewsbury entity
        shrewsbury = next(e for e in seeded_entities if "Shrewsbury" in e["name"])
        
        response = api_client.get(f"{BASE_URL}/api/entities/{shrewsbury['id']}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert data["parent"] is not None
        assert data["parent"]["id"] == parent_entity_id
        assert data["parent"]["name"] == "SY Homes Ltd"
        assert data["children"] == []
    
    def test_nonexistent_entity_returns_404(self, api_client, auth_headers):
        fake_id = str(uuid.uuid4())
        response = api_client.get(f"{BASE_URL}/api/entities/{fake_id}", headers=auth_headers)
        assert response.status_code == 404


class TestEntityCreateEndpoint:
    """POST /api/entities - Create entity tests"""
    
    def test_create_entity_success(self, api_client, auth_headers, parent_entity_id):
        payload = {
            "name": f"{TEST_PREFIX}Chester Ltd",
            "legal_name": f"{TEST_PREFIX}Chester Limited",
            "entity_type": "SPV",
            "parent_entity_id": parent_entity_id,
            "registered_address": "123 Test Street, Chester",
            "default_currency": "GBP",
            "status": "Active"
        }
        response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        
        assert data["name"] == payload["name"]
        assert data["legal_name"] == payload["legal_name"]
        assert data["entity_type"] == "SPV"
        assert data["parent"]["id"] == parent_entity_id
        assert "id" in data
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{data['id']}", headers=auth_headers)
    
    def test_create_entity_with_valid_ch_number(self, api_client, auth_headers):
        payload = {
            "name": f"{TEST_PREFIX}CH Valid Ltd",
            "legal_name": f"{TEST_PREFIX}CH Valid Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "12345678"
        }
        response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["companies_house_number"] == "12345678"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{data['id']}", headers=auth_headers)
    
    def test_create_entity_with_sc_ch_number(self, api_client, auth_headers):
        payload = {
            "name": f"{TEST_PREFIX}SC Valid Ltd",
            "legal_name": f"{TEST_PREFIX}SC Valid Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "SC123456"
        }
        response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["companies_house_number"] == "SC123456"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{data['id']}", headers=auth_headers)
    
    def test_create_entity_invalid_ch_number_rejects_422(self, api_client, auth_headers):
        payload = {
            "name": f"{TEST_PREFIX}Invalid CH Ltd",
            "legal_name": f"{TEST_PREFIX}Invalid CH Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "ABC"  # Too short
        }
        response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert response.status_code == 422
    
    def test_create_entity_duplicate_ch_number_rejects_409(self, api_client, auth_headers):
        # Create first entity
        payload1 = {
            "name": f"{TEST_PREFIX}Dup CH 1 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup CH 1 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "99999991"
        }
        response1 = api_client.post(f"{BASE_URL}/api/entities", json=payload1, headers=auth_headers)
        assert response1.status_code == 201
        entity1_id = response1.json()["id"]
        
        # Try to create second with same CH number
        payload2 = {
            "name": f"{TEST_PREFIX}Dup CH 2 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup CH 2 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "99999991"
        }
        response2 = api_client.post(f"{BASE_URL}/api/entities", json=payload2, headers=auth_headers)
        assert response2.status_code == 409
        assert "companies_house_number" in response2.json()["detail"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity1_id}", headers=auth_headers)
    
    def test_create_entity_duplicate_vat_number_rejects_409(self, api_client, auth_headers):
        # Create first entity
        payload1 = {
            "name": f"{TEST_PREFIX}Dup VAT 1 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup VAT 1 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "vat_number": "999999999"
        }
        response1 = api_client.post(f"{BASE_URL}/api/entities", json=payload1, headers=auth_headers)
        assert response1.status_code == 201
        entity1_id = response1.json()["id"]
        
        # Try to create second with same VAT number
        payload2 = {
            "name": f"{TEST_PREFIX}Dup VAT 2 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup VAT 2 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "vat_number": "999999999"
        }
        response2 = api_client.post(f"{BASE_URL}/api/entities", json=payload2, headers=auth_headers)
        assert response2.status_code == 409
        assert "vat_number" in response2.json()["detail"]
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity1_id}", headers=auth_headers)
    
    def test_create_entity_bank_account_masked(self, api_client, auth_headers):
        payload = {
            "name": f"{TEST_PREFIX}Bank Test Ltd",
            "legal_name": f"{TEST_PREFIX}Bank Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "bank_account_number": "12345678"
        }
        response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["bank_account_number_masked"] == "****5678"
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{data['id']}", headers=auth_headers)


class TestEntityUpdateEndpoint:
    """PUT /api/entities/{id} - Update entity tests"""
    
    def test_update_entity_success(self, api_client, auth_headers):
        # Create entity
        payload = {
            "name": f"{TEST_PREFIX}Update Test Ltd",
            "legal_name": f"{TEST_PREFIX}Update Test Limited",
            "entity_type": "SPV",
            "registered_address": "Original Address"
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        original_updated_at = create_response.json()["updated_at"]
        
        # Update entity
        import time
        time.sleep(0.1)  # Ensure timestamp changes
        update_payload = {"name": f"{TEST_PREFIX}Updated Name Ltd"}
        update_response = api_client.put(f"{BASE_URL}/api/entities/{entity_id}", json=update_payload, headers=auth_headers)
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["name"] == f"{TEST_PREFIX}Updated Name Ltd"
        assert data["updated_at"] != original_updated_at
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)
    
    def test_update_entity_self_parent_rejects_400(self, api_client, auth_headers):
        # Create entity
        payload = {
            "name": f"{TEST_PREFIX}Self Parent Ltd",
            "legal_name": f"{TEST_PREFIX}Self Parent Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address"
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Try to set self as parent
        update_response = api_client.put(
            f"{BASE_URL}/api/entities/{entity_id}",
            json={"parent_entity_id": entity_id},
            headers=auth_headers
        )
        assert update_response.status_code == 400
        assert "own parent" in update_response.json()["detail"].lower()
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)
    
    def test_update_entity_circular_parent_rejects_400(self, api_client, auth_headers):
        # Create entity A
        payload_a = {
            "name": f"{TEST_PREFIX}Circular A Ltd",
            "legal_name": f"{TEST_PREFIX}Circular A Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address"
        }
        response_a = api_client.post(f"{BASE_URL}/api/entities", json=payload_a, headers=auth_headers)
        assert response_a.status_code == 201
        entity_a_id = response_a.json()["id"]
        
        # Create entity B with A as parent
        payload_b = {
            "name": f"{TEST_PREFIX}Circular B Ltd",
            "legal_name": f"{TEST_PREFIX}Circular B Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "parent_entity_id": entity_a_id
        }
        response_b = api_client.post(f"{BASE_URL}/api/entities", json=payload_b, headers=auth_headers)
        assert response_b.status_code == 201
        entity_b_id = response_b.json()["id"]
        
        # Try to set B as parent of A (would create cycle)
        update_response = api_client.put(
            f"{BASE_URL}/api/entities/{entity_a_id}",
            json={"parent_entity_id": entity_b_id},
            headers=auth_headers
        )
        assert update_response.status_code == 400
        assert "circular" in update_response.json()["detail"].lower()
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_b_id}", headers=auth_headers)
        api_client.delete(f"{BASE_URL}/api/entities/{entity_a_id}", headers=auth_headers)
    
    def test_update_entity_invalid_year_end_rejects_422(self, api_client, auth_headers):
        # Create entity
        payload = {
            "name": f"{TEST_PREFIX}Year End Test Ltd",
            "legal_name": f"{TEST_PREFIX}Year End Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address"
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Try invalid year_end format
        update_response = api_client.put(
            f"{BASE_URL}/api/entities/{entity_id}",
            json={"year_end": "31-03"},  # Wrong format (should be MM-DD)
            headers=auth_headers
        )
        assert update_response.status_code == 422
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)


class TestEntityDeleteEndpoint:
    """DELETE /api/entities/{id} - Delete entity tests"""
    
    def test_delete_entity_with_children_rejects_409(self, api_client, auth_headers, parent_entity_id):
        # SY Homes Ltd has children, should not be deletable
        response = api_client.delete(f"{BASE_URL}/api/entities/{parent_entity_id}", headers=auth_headers)
        assert response.status_code == 409
        assert "child" in response.json()["detail"].lower()
    
    def test_delete_leaf_entity_success(self, api_client, auth_headers):
        # Create a leaf entity
        payload = {
            "name": f"{TEST_PREFIX}Delete Test Ltd",
            "legal_name": f"{TEST_PREFIX}Delete Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address"
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Delete it
        delete_response = api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)
        assert delete_response.status_code == 204
        
        # Verify it's gone
        get_response = api_client.get(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)
        assert get_response.status_code == 404


class TestStruckOffStatus:
    """Struck_off status filtering tests"""
    
    def test_struck_off_hidden_by_default(self, api_client, auth_headers):
        # Create struck_off entity
        payload = {
            "name": f"{TEST_PREFIX}Struck Off Ltd",
            "legal_name": f"{TEST_PREFIX}Struck Off Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "status": "Struck_off"
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Default list should not include it
        list_response = api_client.get(f"{BASE_URL}/api/entities", headers=auth_headers)
        assert list_response.status_code == 200
        names = [e["name"] for e in list_response.json()["items"]]
        assert f"{TEST_PREFIX}Struck Off Ltd" not in names
        
        # With status filter, should include it
        filter_response = api_client.get(f"{BASE_URL}/api/entities", params={"status": "Struck_off"}, headers=auth_headers)
        assert filter_response.status_code == 200
        names = [e["name"] for e in filter_response.json()["items"]]
        assert f"{TEST_PREFIX}Struck Off Ltd" in names
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)


class TestInsuranceAlerts:
    """Insurance alerts endpoint tests"""
    
    def test_insurance_alerts_critical_severity(self, api_client, auth_headers):
        # Create entity with insurance expiring in 10 days
        future_date = (date.today() + timedelta(days=10)).isoformat()
        payload = {
            "name": f"{TEST_PREFIX}Insurance Alert Ltd",
            "legal_name": f"{TEST_PREFIX}Insurance Alert Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "el_insurance_expires": future_date
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Check insurance alerts
        alerts_response = api_client.get(f"{BASE_URL}/api/meta/insurance-alerts", headers=auth_headers)
        assert alerts_response.status_code == 200
        alerts = alerts_response.json()
        
        # Find our entity's alert
        entity_alerts = [a for a in alerts if a["entity_id"] == entity_id]
        assert len(entity_alerts) == 1
        assert entity_alerts[0]["policy"] == "EL"
        assert entity_alerts[0]["severity"] == "critical"  # 10 days is critical (<= 14)
        assert entity_alerts[0]["days_until_expiry"] == 10
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)
    
    def test_insurance_alerts_warning_severity(self, api_client, auth_headers):
        # Create entity with insurance expiring in 45 days
        future_date = (date.today() + timedelta(days=45)).isoformat()
        payload = {
            "name": f"{TEST_PREFIX}Insurance Warning Ltd",
            "legal_name": f"{TEST_PREFIX}Insurance Warning Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "pl_insurance_expires": future_date
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Check insurance alerts
        alerts_response = api_client.get(f"{BASE_URL}/api/meta/insurance-alerts", headers=auth_headers)
        assert alerts_response.status_code == 200
        alerts = alerts_response.json()
        
        # Find our entity's alert
        entity_alerts = [a for a in alerts if a["entity_id"] == entity_id]
        assert len(entity_alerts) == 1
        assert entity_alerts[0]["policy"] == "PL"
        assert entity_alerts[0]["severity"] == "warning"  # 45 days is warning (15-60)
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)
    
    def test_insurance_alerts_expired_severity(self, api_client, auth_headers):
        # Create entity with expired insurance
        past_date = (date.today() - timedelta(days=5)).isoformat()
        payload = {
            "name": f"{TEST_PREFIX}Insurance Expired Ltd",
            "legal_name": f"{TEST_PREFIX}Insurance Expired Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "pi_insurance_expires": past_date
        }
        create_response = api_client.post(f"{BASE_URL}/api/entities", json=payload, headers=auth_headers)
        assert create_response.status_code == 201
        entity_id = create_response.json()["id"]
        
        # Check insurance alerts
        alerts_response = api_client.get(f"{BASE_URL}/api/meta/insurance-alerts", headers=auth_headers)
        assert alerts_response.status_code == 200
        alerts = alerts_response.json()
        
        # Find our entity's alert
        entity_alerts = [a for a in alerts if a["entity_id"] == entity_id]
        assert len(entity_alerts) == 1
        assert entity_alerts[0]["policy"] == "PI"
        assert entity_alerts[0]["severity"] == "expired"
        assert entity_alerts[0]["days_until_expiry"] < 0
        
        # Cleanup
        api_client.delete(f"{BASE_URL}/api/entities/{entity_id}", headers=auth_headers)


class TestCleanup:
    """Cleanup any remaining test entities"""
    
    def test_cleanup_test_entities(self, api_client, auth_headers):
        # Get all entities
        response = api_client.get(f"{BASE_URL}/api/entities", params={"page_size": 200, "include_struck_off": True}, headers=auth_headers)
        if response.status_code == 200:
            for entity in response.json()["items"]:
                if entity["name"].startswith(TEST_PREFIX):
                    api_client.delete(f"{BASE_URL}/api/entities/{entity['id']}", headers=auth_headers)
        
        # Verify cleanup
        response = api_client.get(f"{BASE_URL}/api/entities", params={"page_size": 200, "include_struck_off": True}, headers=auth_headers)
        assert response.status_code == 200
        test_entities = [e for e in response.json()["items"] if e["name"].startswith(TEST_PREFIX)]
        assert len(test_entities) == 0, f"Cleanup failed, remaining: {[e['name'] for e in test_entities]}"
