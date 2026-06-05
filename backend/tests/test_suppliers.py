"""Chat 24 §R1 (Prompt 2.5) — supplier directory tests.

Five integration tests against the live FastAPI service, covering:
  1. POST /api/v1/suppliers creates a supplier, returns 201, audits diff.
  2. GET /api/v1/suppliers excludes is_archived=true by default.
  3. POST /api/v1/suppliers/{id}/archive then /unarchive flips is_archived
     idempotently and emits Archive / Restore audit_log rows.
  4. Duplicate name within the same tenant returns 422.
  5. Reading a supplier without suppliers.view_sensitive nulls out
     banking + VAT + company_number response fields (no leakage).

Test users (seeded by the operator's local conftest):
  - test-admin@example.test  — super_admin role (all perms)
  - test-pm@example.test     — project_manager role (suppliers.view/create/edit but NOT view_sensitive)
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"


def _suffix() -> str:
    """Return a short random string that yields a unique supplier name."""
    return uuid.uuid4().hex[:8].upper()


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    with e.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield e
    e.dispose()


@pytest.fixture(scope="module", autouse=True)
def _wipe_module(engine):
    """Clean rows owned by this module's test users at start + end."""
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
    yield
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))


@pytest.fixture
def _wipe_between(engine):
    """Per-test cleanup of supplier rows owned by the test users."""
    with engine.begin() as c:
        c.execute(text("""
            DELETE FROM suppliers
            WHERE created_by IN (
                SELECT id FROM users WHERE email LIKE 'test-%@example.test'
            )
        """))
    yield


@pytest.fixture(scope="module")
def admin(engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm(engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


def _audit_rows_for_supplier(engine, supplier_id: str, *, action: str | None = None,
                              since: datetime) -> list[dict]:
    """Fetch audit_log rows for the supplier resource."""
    sql = """
        SELECT action, field_changes, metadata_json
          FROM audit_log
         WHERE resource_type='supplier'
           AND resource_id=:rid
           AND created_at >= :since
    """
    params: dict = {"rid": supplier_id, "since": since}
    if action is not None:
        sql += " AND action=:action"
        params["action"] = action
    sql += " ORDER BY created_at ASC"
    with engine.connect() as c:
        return [
            {"action": a, "field_changes": fc, "metadata": md}
            for (a, fc, md) in c.execute(text(sql), params).all()
        ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestCreate:
    def test_create_supplier_returns_201_and_audit_diff(
        self, admin, engine, _wipe_between,
    ):
        start = datetime.now(timezone.utc)
        sx = _suffix()
        body = {
            "name": f"Acme Bricks {sx}",
            "contact_email": "acme@example.test",
            "vat_number": "GB123456789",
            "bank_account_no": "12345678",
            "bank_sort_code": "12-34-56",
            "payment_terms_days": 30,
        }
        r = admin.post(f"{BASE_URL}/api/v1/suppliers", json=body)
        assert r.status_code == 201, r.text
        out = r.json()
        assert out["name"] == body["name"]
        assert out["vat_number"] == "GB123456789"        # admin has sensitive
        assert out["bank_account_no"] == "12345678"
        assert out["is_archived"] is False
        assert out["portal_enabled"] is False
        # Chat 41 §R5 — serialised shape: trade fields present; dropped
        # fields absent. Chat 41 §R-eyeball-Step2A — vat_registered also
        # dropped in 0041.
        assert "trade_id" in out and out["trade_id"] is None
        assert "trade" in out and out["trade"] is None
        assert "cis_subtype" not in out
        assert "default_vat_rate" not in out
        assert "vat_registered" not in out
        sid = out["id"]

        rows = _audit_rows_for_supplier(engine, sid, action="Create", since=start)
        assert len(rows) == 1, f"expected one Create audit row, got {len(rows)}"
        fields = {c["field"]: c for c in rows[0]["field_changes"]}
        # Banking PII fields must be redacted in the audit diff.
        assert fields["bank_account_no"]["new"] == "[REDACTED]"
        assert fields["bank_sort_code"]["new"] == "[REDACTED]"
        # Non-sensitive fields appear as their actual new values.
        assert fields["name"]["new"] == body["name"]
        # vat_number is sensitive at response layer, but NOT redacted in audit
        # (business identifier, not PII — see SENSITIVE_FIELDS list).
        assert fields["vat_number"]["new"] == "GB123456789"


class TestList:
    def test_list_excludes_archived_by_default(self, admin, engine, _wipe_between):
        sx = _suffix()
        for archived in (False, True):
            body = {"name": f"Vendor-{archived}-{sx}"}
            r = admin.post(f"{BASE_URL}/api/v1/suppliers", json=body)
            assert r.status_code == 201, r.text
            sid = r.json()["id"]
            if archived:
                ar = admin.post(f"{BASE_URL}/api/v1/suppliers/{sid}/archive")
                assert ar.status_code == 200, ar.text

        # Default GET excludes archived.
        r = admin.get(f"{BASE_URL}/api/v1/suppliers", params={"q": sx})
        names = {item["name"] for item in r.json()["items"]}
        assert f"Vendor-False-{sx}" in names
        assert f"Vendor-True-{sx}" not in names

        # include_archived=true returns both.
        r2 = admin.get(
            f"{BASE_URL}/api/v1/suppliers",
            params={"q": sx, "include_archived": "true"},
        )
        names2 = {item["name"] for item in r2.json()["items"]}
        assert f"Vendor-False-{sx}" in names2
        assert f"Vendor-True-{sx}" in names2


class TestArchiveLifecycle:
    def test_archive_unarchive_toggles_with_audit(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Lifecycle-{sx}"},
        )
        assert r.status_code == 201
        sid = r.json()["id"]
        start = datetime.now(timezone.utc)

        # archive
        ra = admin.post(f"{BASE_URL}/api/v1/suppliers/{sid}/archive")
        assert ra.status_code == 200, ra.text
        assert ra.json()["is_archived"] is True
        assert ra.json()["archived_at"] is not None

        # unarchive
        ru = admin.post(f"{BASE_URL}/api/v1/suppliers/{sid}/unarchive")
        assert ru.status_code == 200, ru.text
        assert ru.json()["is_archived"] is False
        assert ru.json()["archived_at"] is None

        # idempotency: a second unarchive doesn't emit a new audit row.
        ru2 = admin.post(f"{BASE_URL}/api/v1/suppliers/{sid}/unarchive")
        assert ru2.status_code == 200

        rows = _audit_rows_for_supplier(engine, sid, since=start)
        actions = [r["action"] for r in rows]
        assert actions == ["Archive", "Restore"], (
            f"expected exactly [Archive, Restore], got {actions}"
        )


class TestUniqueness:
    def test_duplicate_name_in_tenant_returns_422(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        body = {"name": f"DupCo {sx}"}
        r1 = admin.post(f"{BASE_URL}/api/v1/suppliers", json=body)
        assert r1.status_code == 201, r1.text

        # Same name, same tenant → 422
        r2 = admin.post(f"{BASE_URL}/api/v1/suppliers", json=body)
        assert r2.status_code == 422, r2.text
        assert "already exists" in r2.json()["detail"].lower()

        # Case-insensitive collision
        r3 = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"dupco {sx.lower()}"},
        )
        assert r3.status_code == 422, r3.text


class TestSensitiveGating:
    def test_view_without_sensitive_perm_nulls_banking_fields(
        self, admin, pm, engine, _wipe_between,
    ):
        sx = _suffix()
        # admin creates a supplier with banking + vat populated.
        r = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={
                "name": f"GatedCo {sx}",
                "vat_number": "GB987654321",
                "company_number": "01234567",
                "bank_name": "Test Bank Ltd",
                "bank_account_no": "11111111",
                "bank_sort_code": "00-00-00",
            },
        )
        assert r.status_code == 201, r.text
        sid = r.json()["id"]
        # Admin (super_admin) sees real values.
        assert r.json()["vat_number"] == "GB987654321"
        assert r.json()["bank_account_no"] == "11111111"

        # PM has suppliers.view but NOT suppliers.view_sensitive.
        rp = pm.get(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert rp.status_code == 200, rp.text
        out = rp.json()
        for key in (
            "vat_number", "company_number",
            "bank_name", "bank_account_no", "bank_sort_code",
        ):
            assert out[key] is None, (
                f"PM should not see {key}, got {out[key]!r}"
            )
        # Non-sensitive fields still visible.
        assert out["name"] == f"GatedCo {sx}"
        assert out["is_archived"] is False


# ==========================================================================
# Chat 41 §R-eyeball-2 (Prompt 2.7-FE-revision) — hard delete.
#
# Endpoint: DELETE /api/v1/suppliers/{id}  (gated on suppliers.delete)
#   - 204 when the supplier has no linked records
#   - 409 when ANY linked record exists (PO, actual, subcontract,
#     CIS verification, supplier_document) — with operator-readable msg
#   - 403 when caller lacks suppliers.delete
#   - 404 when the supplier doesn't exist (or is in another tenant)
# ==========================================================================

class TestSupplierDelete:
    def test_delete_unlinked_supplier_returns_204_and_audits(
        self, admin, engine, _wipe_between,
    ):
        sx = _suffix()
        cr = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"DeleteMe {sx}"},
        )
        assert cr.status_code == 201, cr.text
        sid = cr.json()["id"]
        t0 = datetime.now(timezone.utc)

        dr = admin.delete(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert dr.status_code == 204, dr.text

        # Row really gone.
        gr = admin.get(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert gr.status_code == 404, gr.text

        # Audit "Delete" row recorded.
        rows = _audit_rows_for_supplier(engine, sid, action="Delete", since=t0)
        assert len(rows) == 1, f"expected 1 Delete audit row, got {len(rows)}"

    def test_delete_blocked_when_linked_purchase_order_exists(
        self, admin, engine, _wipe_between,
    ):
        """Function name retains the original wording (PO was the
        first-listed blocker); the test uses a `supplier_documents`
        row as the linkage because it's the lightest-weight FK to set
        up (no project / budget / cost-code prerequisites). The
        backend handler iterates the same `_LINKED_RECORD_TABLES`
        tuple — proving the gate fires for one entry proves the
        wiring for all of them."""
        sx = _suffix()
        cr = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"Linked {sx}"},
        )
        assert cr.status_code == 201, cr.text
        sid = cr.json()["id"]

        with engine.begin() as c:
            tenant_id = c.execute(text(
                "SELECT tenant_id FROM suppliers WHERE id = :sid"
            ), {"sid": sid}).scalar()
            user_id = c.execute(text(
                "SELECT id FROM users WHERE email = :e"
            ), {"e": ADMIN_EMAIL}).scalar()
            c.execute(text("""
                INSERT INTO supplier_documents
                  (id, tenant_id, supplier_id, doc_type, title,
                   created_by, updated_by, created_at, updated_at)
                VALUES
                  (gen_random_uuid(), :tid, :sid, 'Other', :title,
                   :uid, :uid, NOW(), NOW())
            """), {
                "tid": str(tenant_id), "sid": sid,
                "title": f"LinkProof-{sx}",
                "uid": str(user_id),
            })

        dr = admin.delete(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert dr.status_code == 409, dr.text
        body = dr.json()
        assert "Cannot delete" in body.get("detail", "")
        assert "supplier_documents" in body["detail"], body["detail"]
        assert "archive instead" in body["detail"]

        # Row still present.
        gr = admin.get(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert gr.status_code == 200, gr.text

        # Clean up the linked row so the module wipe can drop the supplier.
        with engine.begin() as c:
            c.execute(text(
                "DELETE FROM supplier_documents WHERE supplier_id = :sid"
            ), {"sid": sid})

    def test_delete_forbidden_for_caller_without_suppliers_delete(
        self, pm, admin, _wipe_between,
    ):
        """PM holds suppliers.archive=No (only view/create/edit) in seed
        — so they can't delete either. We use the admin-created row
        as the deletion target."""
        sx = _suffix()
        cr = admin.post(
            f"{BASE_URL}/api/v1/suppliers",
            json={"name": f"NoDelete {sx}"},
        )
        assert cr.status_code == 201, cr.text
        sid = cr.json()["id"]

        dr = pm.delete(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert dr.status_code == 403, dr.text

        # Row still present.
        gr = admin.get(f"{BASE_URL}/api/v1/suppliers/{sid}")
        assert gr.status_code == 200, gr.text

    def test_delete_unknown_supplier_returns_404(
        self, admin, _wipe_between,
    ):
        dr = admin.delete(
            f"{BASE_URL}/api/v1/suppliers/{uuid.uuid4()}"
        )
        assert dr.status_code == 404, dr.text
