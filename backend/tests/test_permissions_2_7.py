"""Chat 32 §R5 (Prompt 2.7) — permission count + role mapping gates.

Acceptance gates 26-27 (gate 28 = full-suite zero-regression — that one
is a wholesale `pytest` invocation, not a single function).
"""
from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


class TestPermissionCount:
    def test_total_permission_count_is_110(self, engine):
        """Gate 26: permission count = prior baseline (102) + 8 = 110
        at 2.7 close. Chat 33 / mig 0036 (Prompt 2.6) adds
        budget_changes.submit + .apply → 112. Function name retains
        '110' per chat-15 §3 literal-drift convention."""
        with engine.connect() as c:
            n = c.execute(text("SELECT count(*) FROM permissions")).scalar()
        assert n == 112, f"expected 112 permissions, got {n}"

    def test_eight_new_perm_codes_present(self, engine):
        """Gate 26 (positive form): the 8 new codes exist in the catalogue."""
        expected = {
            "cis.view", "cis.view_sensitive", "cis.verify",
            "supplier_documents.view", "supplier_documents.view_sensitive",
            "supplier_documents.create", "supplier_documents.edit",
            "supplier_documents.archive",
        }
        with engine.connect() as c:
            present = {
                r[0] for r in c.execute(text(
                    "SELECT code FROM permissions "
                    "WHERE code LIKE 'cis.%' OR code LIKE 'supplier_documents.%'"
                )).all()
            }
        assert expected <= present, f"missing: {expected - present}"


class TestRoleMapping:
    def test_cis_verify_maps_to_suppliers_create_roles(self, engine):
        """Gate 27: cis.verify is mapped to EXACTLY the roles that hold
        suppliers.create (assert against the live map, not a hardcoded
        list)."""
        with engine.connect() as c:
            suppliers_create_roles = {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM roles r
                    JOIN role_permissions rp ON rp.role_id = r.id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE p.code = 'suppliers.create'
                """)).all()
            }
            cis_verify_roles = {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM roles r
                    JOIN role_permissions rp ON rp.role_id = r.id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE p.code = 'cis.verify'
                """)).all()
            }
        assert suppliers_create_roles, (
            "suppliers.create role set unexpectedly empty — seed broken?"
        )
        assert cis_verify_roles == suppliers_create_roles, (
            f"cis.verify ↔ suppliers.create role mismatch.\n"
            f"  suppliers.create: {sorted(suppliers_create_roles)}\n"
            f"  cis.verify:       {sorted(cis_verify_roles)}"
        )

    def test_supplier_documents_perms_map_to_suppliers_create_roles(
        self, engine,
    ):
        """Gate 27 (the supplier_documents.* half): each of the 5
        supplier_documents.* perms is mapped to exactly the same roles
        that hold suppliers.create."""
        with engine.connect() as c:
            suppliers_create_roles = {
                r[0] for r in c.execute(text("""
                    SELECT r.code FROM roles r
                    JOIN role_permissions rp ON rp.role_id = r.id
                    JOIN permissions p ON p.id = rp.permission_id
                    WHERE p.code = 'suppliers.create'
                """)).all()
            }
            for code in (
                "supplier_documents.view",
                "supplier_documents.view_sensitive",
                "supplier_documents.create",
                "supplier_documents.edit",
                "supplier_documents.archive",
            ):
                got = {
                    r[0] for r in c.execute(text("""
                        SELECT r.code FROM roles r
                        JOIN role_permissions rp ON rp.role_id = r.id
                        JOIN permissions p ON p.id = rp.permission_id
                        WHERE p.code = :code
                    """), {"code": code}).all()
                }
                assert got == suppliers_create_roles, (
                    f"{code} ↔ suppliers.create role mismatch.\n"
                    f"  suppliers.create: {sorted(suppliers_create_roles)}\n"
                    f"  {code}:    {sorted(got)}"
                )
