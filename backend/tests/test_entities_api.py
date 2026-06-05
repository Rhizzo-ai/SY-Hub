"""
Backend API tests for SY Homes Entities module (Prompt 1.1 + 1.2 Auth).
Migrated to cookies-only transport (audit remediation C1 — Feb 2026).
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

from tests.conftest import login_with_auto_enroll


BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://sy-hub-ops.preview.emergentagent.com"

TEST_PREFIX = "TEST_"

SUPER_ADMIN_EMAIL = "test-admin@example.test"
SUPER_ADMIN_PASSWORD = "TestUser-Dev-2026!"


@pytest.fixture(scope="module")
def anon_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# Kept for tests that reference `api_client` for anon calls.
@pytest.fixture(scope="module")
def api_client(anon_client):
    return anon_client


@pytest.fixture(scope="module")
def admin():
    """Authenticated super_admin session (auto-enrol MFA if required)."""
    return login_with_auto_enroll(None, BASE_URL, SUPER_ADMIN_EMAIL, SUPER_ADMIN_PASSWORD)


@pytest.fixture(scope="module")
def tenant_id(admin):
    response = admin.get(f"{BASE_URL}/api/meta/tenant")
    assert response.status_code == 200
    return response.json()["id"]


@pytest.fixture(scope="module")
def seeded_entities(admin):
    response = admin.get(f"{BASE_URL}/api/entities", params={"page_size": 100})
    assert response.status_code == 200
    return response.json()["items"]


@pytest.fixture(scope="module")
def parent_entity_id(seeded_entities):
    for e in seeded_entities:
        if e["name"] == "SY Homes Ltd":
            return e["id"]
    pytest.fail("SY Homes Ltd not found in seeded entities")


class TestHealthEndpoint:
    def test_health_returns_200(self, anon_client):
        response = anon_client.get(f"{BASE_URL}/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "users+rbac"
        assert data["phase"] == "1.2"


class TestMetaEndpoints:
    def test_tenant_returns_sy_homes(self, admin):
        response = admin.get(f"{BASE_URL}/api/meta/tenant")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "SY Homes"
        uuid.UUID(data["id"])
        assert "created_at" in data

    def test_enums_returns_all_5_enums(self, admin):
        response = admin.get(f"{BASE_URL}/api/meta/enums")
        assert response.status_code == 200
        data = response.json()
        assert "entity_types" in data
        assert "vat_schemes" in data
        assert "vat_return_periods" in data
        assert "cis_statuses" in data
        assert "entity_statuses" in data
        assert set(data["entity_types"]) == {"Parent", "SPV", "ConstructionCo", "JV_Vehicle", "Other"}
        assert set(data["vat_schemes"]) == {"Standard_Quarterly", "Standard_Monthly", "Cash_Accounting", "Flat_Rate", "Not_Registered"}
        assert set(data["vat_return_periods"]) == {"Jan_Apr_Jul_Oct", "Feb_May_Aug_Nov", "Mar_Jun_Sep_Dec", "Monthly"}
        assert set(data["cis_statuses"]) == {"Contractor", "Subcontractor", "Both", "None"}
        assert set(data["entity_statuses"]) == {"Active", "Dormant", "Struck_off"}


class TestEntitiesListEndpoint:
    def test_list_returns_3_seeded_entities(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 3
        names = {e["name"] for e in data["items"]}
        assert "SY Homes Ltd" in names
        assert "SY Homes (Shrewsbury) Ltd" in names
        assert "SY Homes (Construction) Ltd" in names

    def test_filter_by_entity_type_parent(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"entity_type": "Parent"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "SY Homes Ltd"
        assert data["items"][0]["entity_type"] == "Parent"

    def test_filter_by_entity_type_spv(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"entity_type": "SPV"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["name"] == "SY Homes (Shrewsbury) Ltd"

    def test_search_by_name(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"q": "Shrewsbury"})
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert "Shrewsbury" in data["items"][0]["name"]

    def test_sort_by_name_desc(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"sort": "name", "dir": "desc"})
        assert response.status_code == 200
        data = response.json()
        names = [e["name"] for e in data["items"]]
        assert names == sorted(names, reverse=True)

    def test_sort_by_name_asc(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"sort": "name", "dir": "asc"})
        assert response.status_code == 200
        data = response.json()
        names = [e["name"] for e in data["items"]]
        assert names == sorted(names)

    def test_invalid_entity_type_filter_returns_400(self, admin):
        response = admin.get(f"{BASE_URL}/api/entities", params={"entity_type": "InvalidType"})
        assert response.status_code == 400


class TestEntityDetailEndpoint:
    def test_parent_entity_has_children(self, admin, parent_entity_id):
        response = admin.get(f"{BASE_URL}/api/entities/{parent_entity_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "SY Homes Ltd"
        assert data["entity_type"] == "Parent"
        assert data["parent"] is None
        assert len(data["children"]) == 2
        child_names = {c["name"] for c in data["children"]}
        assert "SY Homes (Shrewsbury) Ltd" in child_names
        assert "SY Homes (Construction) Ltd" in child_names

    def test_child_entity_has_parent(self, admin, seeded_entities, parent_entity_id):
        shrewsbury = next(e for e in seeded_entities if "Shrewsbury" in e["name"])
        response = admin.get(f"{BASE_URL}/api/entities/{shrewsbury['id']}")
        assert response.status_code == 200
        data = response.json()
        assert data["parent"] is not None
        assert data["parent"]["id"] == parent_entity_id
        assert data["parent"]["name"] == "SY Homes Ltd"
        assert data["children"] == []

    def test_nonexistent_entity_returns_404(self, admin):
        fake_id = str(uuid.uuid4())
        response = admin.get(f"{BASE_URL}/api/entities/{fake_id}")
        assert response.status_code == 404


class TestEntityCreateEndpoint:
    def test_create_entity_success(self, admin, parent_entity_id):
        payload = {
            "name": f"{TEST_PREFIX}Chester Ltd",
            "legal_name": f"{TEST_PREFIX}Chester Limited",
            "entity_type": "SPV",
            "parent_entity_id": parent_entity_id,
            "registered_address": "123 Test Street, Chester",
            "default_currency": "GBP",
            "status": "Active",
        }
        response = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == payload["name"]
        assert data["legal_name"] == payload["legal_name"]
        assert data["entity_type"] == "SPV"
        assert data["parent"]["id"] == parent_entity_id
        assert "id" in data
        admin.delete(f"{BASE_URL}/api/entities/{data['id']}")

    def test_create_entity_with_valid_ch_number(self, admin):
        payload = {
            "name": f"{TEST_PREFIX}CH Valid Ltd",
            "legal_name": f"{TEST_PREFIX}CH Valid Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "12345678",
        }
        response = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["companies_house_number"] == "12345678"
        admin.delete(f"{BASE_URL}/api/entities/{data['id']}")

    def test_create_entity_with_sc_ch_number(self, admin):
        payload = {
            "name": f"{TEST_PREFIX}SC Valid Ltd",
            "legal_name": f"{TEST_PREFIX}SC Valid Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "SC123456",
        }
        response = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["companies_house_number"] == "SC123456"
        admin.delete(f"{BASE_URL}/api/entities/{data['id']}")

    def test_create_entity_invalid_ch_number_rejects_422(self, admin):
        payload = {
            "name": f"{TEST_PREFIX}Invalid CH Ltd",
            "legal_name": f"{TEST_PREFIX}Invalid CH Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "ABC",
        }
        response = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert response.status_code == 422

    def test_create_entity_duplicate_ch_number_rejects_409(self, admin):
        payload1 = {
            "name": f"{TEST_PREFIX}Dup CH 1 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup CH 1 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "99999991",
        }
        r1 = admin.post(f"{BASE_URL}/api/entities", json=payload1)
        assert r1.status_code == 201
        id1 = r1.json()["id"]
        payload2 = {
            "name": f"{TEST_PREFIX}Dup CH 2 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup CH 2 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "companies_house_number": "99999991",
        }
        r2 = admin.post(f"{BASE_URL}/api/entities", json=payload2)
        assert r2.status_code == 409
        assert "companies_house_number" in r2.json()["detail"]
        admin.delete(f"{BASE_URL}/api/entities/{id1}")

    def test_create_entity_duplicate_vat_number_rejects_409(self, admin):
        payload1 = {
            "name": f"{TEST_PREFIX}Dup VAT 1 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup VAT 1 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "vat_number": "999999999",
        }
        r1 = admin.post(f"{BASE_URL}/api/entities", json=payload1)
        assert r1.status_code == 201
        id1 = r1.json()["id"]
        payload2 = {
            "name": f"{TEST_PREFIX}Dup VAT 2 Ltd",
            "legal_name": f"{TEST_PREFIX}Dup VAT 2 Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "vat_number": "999999999",
        }
        r2 = admin.post(f"{BASE_URL}/api/entities", json=payload2)
        assert r2.status_code == 409
        assert "vat_number" in r2.json()["detail"]
        admin.delete(f"{BASE_URL}/api/entities/{id1}")

    def test_create_entity_bank_account_masked(self, admin):
        payload = {
            "name": f"{TEST_PREFIX}Bank Test Ltd",
            "legal_name": f"{TEST_PREFIX}Bank Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "bank_account_number": "12345678",
        }
        response = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["bank_account_number_masked"] == "****5678"
        admin.delete(f"{BASE_URL}/api/entities/{data['id']}")


class TestEntityUpdateEndpoint:
    def test_update_entity_success(self, admin):
        payload = {
            "name": f"{TEST_PREFIX}Update Test Ltd",
            "legal_name": f"{TEST_PREFIX}Update Test Limited",
            "entity_type": "SPV",
            "registered_address": "Original Address",
        }
        cr = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        original_updated_at = cr.json()["updated_at"]

        import time
        time.sleep(0.1)
        ur = admin.put(f"{BASE_URL}/api/entities/{entity_id}", json={"name": f"{TEST_PREFIX}Updated Name Ltd"})
        assert ur.status_code == 200
        data = ur.json()
        assert data["name"] == f"{TEST_PREFIX}Updated Name Ltd"
        assert data["updated_at"] != original_updated_at
        admin.delete(f"{BASE_URL}/api/entities/{entity_id}")

    def test_update_entity_self_parent_rejects_400(self, admin):
        payload = {
            "name": f"{TEST_PREFIX}Self Parent Ltd",
            "legal_name": f"{TEST_PREFIX}Self Parent Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
        }
        cr = admin.post(f"{BASE_URL}/api/entities", json=payload)
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        ur = admin.put(f"{BASE_URL}/api/entities/{entity_id}", json={"parent_entity_id": entity_id})
        assert ur.status_code == 400
        assert "own parent" in ur.json()["detail"].lower()
        admin.delete(f"{BASE_URL}/api/entities/{entity_id}")

    def test_update_entity_circular_parent_rejects_400(self, admin):
        ra = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Circular A Ltd",
            "legal_name": f"{TEST_PREFIX}Circular A Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
        })
        assert ra.status_code == 201
        a_id = ra.json()["id"]
        rb = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Circular B Ltd",
            "legal_name": f"{TEST_PREFIX}Circular B Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "parent_entity_id": a_id,
        })
        assert rb.status_code == 201
        b_id = rb.json()["id"]
        ur = admin.put(f"{BASE_URL}/api/entities/{a_id}", json={"parent_entity_id": b_id})
        assert ur.status_code == 400
        assert "circular" in ur.json()["detail"].lower()
        admin.delete(f"{BASE_URL}/api/entities/{b_id}")
        admin.delete(f"{BASE_URL}/api/entities/{a_id}")

    def test_update_entity_invalid_year_end_rejects_422(self, admin):
        cr = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Year End Test Ltd",
            "legal_name": f"{TEST_PREFIX}Year End Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
        })
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        ur = admin.put(f"{BASE_URL}/api/entities/{entity_id}", json={"year_end": "31-03"})
        assert ur.status_code == 422
        admin.delete(f"{BASE_URL}/api/entities/{entity_id}")


class TestEntityDeleteEndpoint:
    def test_delete_entity_with_children_rejects_409(self, admin, parent_entity_id):
        r = admin.delete(f"{BASE_URL}/api/entities/{parent_entity_id}")
        assert r.status_code == 409
        assert "child" in r.json()["detail"].lower()

    def test_delete_leaf_entity_success(self, admin):
        cr = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Delete Test Ltd",
            "legal_name": f"{TEST_PREFIX}Delete Test Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
        })
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        dr = admin.delete(f"{BASE_URL}/api/entities/{entity_id}")
        assert dr.status_code == 204
        gr = admin.get(f"{BASE_URL}/api/entities/{entity_id}")
        assert gr.status_code == 404


class TestStruckOffStatus:
    def test_struck_off_hidden_by_default(self, admin):
        cr = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Struck Off Ltd",
            "legal_name": f"{TEST_PREFIX}Struck Off Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "status": "Struck_off",
        })
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        lr = admin.get(f"{BASE_URL}/api/entities")
        assert lr.status_code == 200
        names = [e["name"] for e in lr.json()["items"]]
        assert f"{TEST_PREFIX}Struck Off Ltd" not in names
        fr = admin.get(f"{BASE_URL}/api/entities", params={"status": "Struck_off"})
        assert fr.status_code == 200
        names = [e["name"] for e in fr.json()["items"]]
        assert f"{TEST_PREFIX}Struck Off Ltd" in names
        admin.delete(f"{BASE_URL}/api/entities/{entity_id}")


class TestInsuranceAlerts:
    def test_insurance_alerts_critical_severity(self, admin):
        future_date = (date.today() + timedelta(days=10)).isoformat()
        cr = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Insurance Alert Ltd",
            "legal_name": f"{TEST_PREFIX}Insurance Alert Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "el_insurance_expires": future_date,
        })
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        ar = admin.get(f"{BASE_URL}/api/meta/insurance-alerts")
        assert ar.status_code == 200
        entity_alerts = [a for a in ar.json() if a["entity_id"] == entity_id]
        assert len(entity_alerts) == 1
        assert entity_alerts[0]["policy"] == "EL"
        assert entity_alerts[0]["severity"] == "critical"
        assert entity_alerts[0]["days_until_expiry"] == 10
        admin.delete(f"{BASE_URL}/api/entities/{entity_id}")

    def test_insurance_alerts_warning_severity(self, admin):
        future_date = (date.today() + timedelta(days=45)).isoformat()
        cr = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Insurance Warning Ltd",
            "legal_name": f"{TEST_PREFIX}Insurance Warning Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "pl_insurance_expires": future_date,
        })
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        ar = admin.get(f"{BASE_URL}/api/meta/insurance-alerts")
        entity_alerts = [a for a in ar.json() if a["entity_id"] == entity_id]
        assert len(entity_alerts) == 1
        assert entity_alerts[0]["policy"] == "PL"
        assert entity_alerts[0]["severity"] == "warning"
        admin.delete(f"{BASE_URL}/api/entities/{entity_id}")

    def test_insurance_alerts_expired_severity(self, admin):
        past_date = (date.today() - timedelta(days=5)).isoformat()
        cr = admin.post(f"{BASE_URL}/api/entities", json={
            "name": f"{TEST_PREFIX}Insurance Expired Ltd",
            "legal_name": f"{TEST_PREFIX}Insurance Expired Limited",
            "entity_type": "SPV",
            "registered_address": "Test Address",
            "pi_insurance_expires": past_date,
        })
        assert cr.status_code == 201
        entity_id = cr.json()["id"]
        ar = admin.get(f"{BASE_URL}/api/meta/insurance-alerts")
        entity_alerts = [a for a in ar.json() if a["entity_id"] == entity_id]
        assert len(entity_alerts) == 1
        assert entity_alerts[0]["policy"] == "PI"
        assert entity_alerts[0]["severity"] == "expired"
        assert entity_alerts[0]["days_until_expiry"] < 0
        admin.delete(f"{BASE_URL}/api/entities/{entity_id}")


class TestCleanup:
    def test_cleanup_test_entities(self, admin):
        r = admin.get(f"{BASE_URL}/api/entities",
                      params={"page_size": 200, "include_struck_off": True})
        if r.status_code == 200:
            for entity in r.json()["items"]:
                if entity["name"].startswith(TEST_PREFIX):
                    admin.delete(f"{BASE_URL}/api/entities/{entity['id']}")
        r2 = admin.get(f"{BASE_URL}/api/entities",
                       params={"page_size": 200, "include_struck_off": True})
        assert r2.status_code == 200
        leftover = [e for e in r2.json()["items"] if e["name"].startswith(TEST_PREFIX)]
        assert leftover == [], f"Cleanup failed: {[e['name'] for e in leftover]}"
