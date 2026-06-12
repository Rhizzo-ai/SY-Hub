"""B83 §R5 — Role & Permissions Admin: seed precedence + batch grants +
custom-role lifecycle + audit + lock-out guards.

THE critical block is seed precedence (tests 1-4): operator-revoked grants
recorded in `role_permission_revocations` must survive every
`seed_rbac()` re-run — the additive seed must never re-add them (D1).

Hard guards verified:
  - super_admin fully locked: any batch change targeting it → 403 (D3).
  - Mutations gated `roles.admin` (director holds roles.edit but NOT
    roles.admin → 403) (D2).
  - System roles undeletable + metadata-locked (D6).
  - Custom-role default grants per amended D5: is_sensitive = false AND
    action NOT IN (delete, admin, void).
  - Batch endpoint transactional all-or-nothing across the entire request.
  - One Permission_Change audit row per mutated role (D7).

Naming requirement (Build Pack §R5) — file is named exactly
`test_role_permissions_admin.py`. Do not consolidate. Function names are
binding — do not rename.
"""
from __future__ import annotations

import os
import uuid

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll, plain_login

load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
            or "http://localhost:8001")
DATABASE_URL = os.environ["DATABASE_URL"]
TEST_PASSWORD = "TestUser-Dev-2026!"

EXCLUDED_ACTIONS = ("delete", "admin", "void")


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
        # Warm-run hygiene: clear any leftovers from a previously aborted
        # run so the seed-precedence tests start from seeded truth.
        c.execute(text("""
            DELETE FROM roles
            WHERE is_system_role = false AND (
                code LIKE 'b83\\_test\\_%' OR code = 'quantity_surveyor'
            )
        """))
        c.execute(text("DELETE FROM role_permission_revocations"))
    # Restore any seeded grant a leftover revocation may have suppressed.
    from app.seed_rbac import seed_rbac
    seed_rbac()
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-admin@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-director@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def pm(db_engine):
    return plain_login(BASE_URL, "test-pm@example.test", TEST_PASSWORD)


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _run_seed():
    from app.seed_rbac import seed_rbac
    seed_rbac()


def _role_id(c, role_code: str) -> str:
    return str(c.execute(
        text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
    ).scalar())


def _perm_id(c, perm_code: str) -> str:
    return str(c.execute(
        text("SELECT id FROM permissions WHERE code = :pc"), {"pc": perm_code}
    ).scalar())


def _grant_exists(c, role_id: str, perm_id: str) -> bool:
    return bool(c.execute(text(
        "SELECT 1 FROM role_permissions "
        "WHERE role_id = :r AND permission_id = :p"
    ), {"r": role_id, "p": perm_id}).scalar())


def _revocation_row(c, role_id: str, perm_id: str):
    return c.execute(text(
        "SELECT role_id, permission_id, revoked_by_user_id, revoked_at "
        "FROM role_permission_revocations "
        "WHERE role_id = :r AND permission_id = :p"
    ), {"r": role_id, "p": perm_id}).mappings().first()


def _delete_revocation(c, role_id: str, perm_id: str) -> None:
    c.execute(text(
        "DELETE FROM role_permission_revocations "
        "WHERE role_id = :r AND permission_id = :p"
    ), {"r": role_id, "p": perm_id})


def _user_id(c, email: str) -> str:
    return str(c.execute(
        text("SELECT id FROM users WHERE email = :e"), {"e": email}
    ).scalar())


def _latest_audit(c, resource_id: str, action: str):
    return c.execute(text(
        "SELECT action, resource_type, resource_id, actor_user_id, "
        "       field_changes, metadata_json "
        "FROM audit_log "
        "WHERE resource_id = :rid AND action = :a "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"rid": resource_id, "a": action}).mappings().first()


def _audit_count(c, resource_id: str, action: str) -> int:
    return c.execute(text(
        "SELECT COUNT(*) FROM audit_log "
        "WHERE resource_id = :rid AND action = :a"
    ), {"rid": resource_id, "a": action}).scalar()


def _batch(session, changes: list[dict]):
    return session.post(f"{BASE_URL}/api/roles/permissions-batch",
                        json={"changes": changes})


def _uniq_role_name(prefix: str = "B83 Test Role") -> str:
    return f"{prefix} {uuid.uuid4().hex[:8]}"


def _create_custom_role(admin, name: str | None = None,
                        description: str = "B83 test custom role"):
    r = admin.post(f"{BASE_URL}/api/roles",
                   json={"name": name or _uniq_role_name(),
                         "description": description})
    assert r.status_code == 201, r.text
    return r.json()


def _delete_role_sql(db_engine, role_id: str) -> None:
    with db_engine.begin() as c:
        c.execute(text("DELETE FROM user_roles WHERE role_id = :r"),
                  {"r": role_id})
        c.execute(text("DELETE FROM roles WHERE id = :r AND is_system_role = false"),
                  {"r": role_id})


# ==========================================================================
# Seed precedence (THE critical block) — tests 1-4
# ==========================================================================

def test_revoked_pair_not_readded_by_seed(db_engine):
    """Grant exists for (project_manager, budgets.create); write revocation
    row + delete grant; run seed_rbac(); grant must STILL be absent (D1)."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        pid = _perm_id(c, "budgets.create")
        assert _grant_exists(c, rid, pid), "precondition: seeded grant missing"
        c.execute(text(
            "DELETE FROM role_permissions WHERE role_id=:r AND permission_id=:p"
        ), {"r": rid, "p": pid})
        c.execute(text(
            "INSERT INTO role_permission_revocations (role_id, permission_id) "
            "VALUES (:r, :p)"
        ), {"r": rid, "p": pid})
    try:
        _run_seed()
        with db_engine.begin() as c:
            assert not _grant_exists(c, rid, pid), (
                "seed re-added an operator-revoked grant — D1 violated"
            )
            assert _revocation_row(c, rid, pid) is not None
    finally:
        with db_engine.begin() as c:
            _delete_revocation(c, rid, pid)
        _run_seed()  # restore seeded truth
        with db_engine.begin() as c:
            assert _grant_exists(c, rid, pid)


def test_seed_still_adds_new_unrevoked_grants(db_engine):
    """Delete an unrevoked seeded grant; seed_rbac() must re-add it —
    the seed stays additive for everything not revoked."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        pid = _perm_id(c, "budgets.edit")
        assert _grant_exists(c, rid, pid)
        c.execute(text(
            "DELETE FROM role_permissions WHERE role_id=:r AND permission_id=:p"
        ), {"r": rid, "p": pid})
    _run_seed()
    with db_engine.begin() as c:
        assert _grant_exists(c, rid, pid), "seed failed to re-add unrevoked grant"


def test_seed_never_touches_custom_roles(db_engine):
    """Custom role with a hand-picked grant set; seed_rbac() must leave it
    exactly as-is (ROLE_PERMISSIONS only references system role codes)."""
    role_id = str(uuid.uuid4())
    with db_engine.begin() as c:
        c.execute(text(
            "INSERT INTO roles (id, code, name, description, is_system_role, "
            "priority, created_at, updated_at) VALUES "
            "(:i, 'b83_test_seed_probe', 'B83 Seed Probe', 'probe', false, 40, "
            "now(), now())"
        ), {"i": role_id})
        pid = _perm_id(c, "budgets.view")
        c.execute(text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "VALUES (:r, :p)"
        ), {"r": role_id, "p": pid})
    try:
        _run_seed()
        with db_engine.begin() as c:
            codes = [row[0] for row in c.execute(text(
                "SELECT p.code FROM role_permissions rp "
                "JOIN permissions p ON p.id = rp.permission_id "
                "WHERE rp.role_id = :r"
            ), {"r": role_id})]
            assert codes == ["budgets.view"], (
                f"seed modified a custom role's grants: {codes}"
            )
    finally:
        _delete_role_sql(db_engine, role_id)


def test_revocation_survives_double_seed_run(db_engine):
    """Two consecutive seed_rbac() runs; revoked grant still absent."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        pid = _perm_id(c, "budgets.create")
        c.execute(text(
            "DELETE FROM role_permissions WHERE role_id=:r AND permission_id=:p"
        ), {"r": rid, "p": pid})
        c.execute(text(
            "INSERT INTO role_permission_revocations (role_id, permission_id) "
            "VALUES (:r, :p) ON CONFLICT DO NOTHING"
        ), {"r": rid, "p": pid})
    try:
        _run_seed()
        _run_seed()
        with db_engine.begin() as c:
            assert not _grant_exists(c, rid, pid), (
                "revoked grant returned after double seed run"
            )
    finally:
        with db_engine.begin() as c:
            _delete_revocation(c, rid, pid)
        _run_seed()
        with db_engine.begin() as c:
            assert _grant_exists(c, rid, pid)


# ==========================================================================
# Batch endpoint — tests 5-18
# ==========================================================================

def test_batch_requires_roles_admin(director, db_engine):
    """Director holds roles.edit but NOT roles.admin → 403 (D2)."""
    with db_engine.begin() as c:
        pm_role = _role_id(c, "project_manager")
    r = _batch(director, [{"role_id": pm_role, "add": ["projects.view"],
                           "remove": []}])
    assert r.status_code == 403, r.text
    assert "roles.admin" in r.text


def test_batch_super_admin_target_403(admin, db_engine):
    """Any change targeting super_admin → 403 (D3 lock-out guard)."""
    with db_engine.begin() as c:
        sa_role = _role_id(c, "super_admin")
    r = _batch(admin, [{"role_id": sa_role, "add": [],
                        "remove": ["budgets.view"]}])
    assert r.status_code == 403, r.text
    assert "super_admin grants are locked" in r.text


def test_batch_unknown_role_404(admin):
    bogus = str(uuid.uuid4())
    r = _batch(admin, [{"role_id": bogus, "add": ["projects.view"],
                        "remove": []}])
    assert r.status_code == 404, r.text
    assert bogus in r.text


def test_batch_unknown_permission_code_422_lists_codes(admin, db_engine):
    with db_engine.begin() as c:
        pm_role = _role_id(c, "project_manager")
    r = _batch(admin, [{"role_id": pm_role,
                        "add": ["totally.bogus", "projects.view"],
                        "remove": ["another.bogus"]}])
    assert r.status_code == 422, r.text
    assert "totally.bogus" in r.text
    assert "another.bogus" in r.text


def test_batch_add_and_remove_same_code_422(admin, db_engine):
    with db_engine.begin() as c:
        pm_role = _role_id(c, "project_manager")
    r = _batch(admin, [{"role_id": pm_role,
                        "add": ["projects.view"],
                        "remove": ["projects.view"]}])
    assert r.status_code == 422, r.text


def test_batch_duplicate_role_ids_422(admin, db_engine):
    with db_engine.begin() as c:
        pm_role = _role_id(c, "project_manager")
    r = _batch(admin, [
        {"role_id": pm_role, "add": ["projects.view"], "remove": []},
        {"role_id": pm_role, "add": ["budgets.view"], "remove": []},
    ])
    assert r.status_code == 422, r.text


def test_batch_remove_deletes_grant_and_writes_revocation(admin, db_engine):
    """Remove writes the revocation row stamped with the acting user id."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        pid = _perm_id(c, "budgets.create")
        admin_id = _user_id(c, "test-admin@example.test")
        assert _grant_exists(c, rid, pid)
    try:
        r = _batch(admin, [{"role_id": rid, "add": [],
                            "remove": ["budgets.create"]}])
        assert r.status_code == 200, r.text
        with db_engine.begin() as c:
            assert not _grant_exists(c, rid, pid)
            row = _revocation_row(c, rid, pid)
            assert row is not None
            assert str(row["revoked_by_user_id"]) == admin_id
    finally:
        r = _batch(admin, [{"role_id": rid, "add": ["budgets.create"],
                            "remove": []}])
        assert r.status_code == 200, r.text


def test_batch_add_inserts_grant_and_clears_revocation(admin, db_engine):
    """Re-granting heals the override: grant row back, revocation gone."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        pid = _perm_id(c, "budgets.create")
    r = _batch(admin, [{"role_id": rid, "add": [],
                        "remove": ["budgets.create"]}])
    assert r.status_code == 200, r.text
    r = _batch(admin, [{"role_id": rid, "add": ["budgets.create"],
                        "remove": []}])
    assert r.status_code == 200, r.text
    with db_engine.begin() as c:
        assert _grant_exists(c, rid, pid)
        assert _revocation_row(c, rid, pid) is None


def test_batch_remove_ungranted_code_idempotent_writes_revocation(
    admin, db_engine,
):
    """Removing a code the role never held is idempotent (200) and STILL
    writes the revocation row — pre-empts a future seed grant."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        pid = _perm_id(c, "users.admin")
        assert not _grant_exists(c, rid, pid), "precondition: PM lacks users.admin"
    try:
        r = _batch(admin, [{"role_id": rid, "add": [],
                            "remove": ["users.admin"]}])
        assert r.status_code == 200, r.text
        with db_engine.begin() as c:
            assert not _grant_exists(c, rid, pid)
            assert _revocation_row(c, rid, pid) is not None
    finally:
        # Cleanup by SQL — re-adding via the API would GRANT users.admin.
        with db_engine.begin() as c:
            _delete_revocation(c, rid, pid)


def test_batch_add_already_granted_noop_clears_revocation(admin, db_engine):
    """Adding an already-granted code is a no-op apart from the revocation
    cleanup (heals drift where both rows exist)."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        pid = _perm_id(c, "projects.view")
        assert _grant_exists(c, rid, pid)
        c.execute(text(
            "INSERT INTO role_permission_revocations (role_id, permission_id) "
            "VALUES (:r, :p) ON CONFLICT DO NOTHING"
        ), {"r": rid, "p": pid})
    r = _batch(admin, [{"role_id": rid, "add": ["projects.view"],
                        "remove": []}])
    assert r.status_code == 200, r.text
    with db_engine.begin() as c:
        assert _grant_exists(c, rid, pid)
        assert _revocation_row(c, rid, pid) is None


def test_batch_transactional_all_or_nothing(admin, db_engine):
    """Second change contains an unknown code → the first change must NOT
    apply and no audit rows are written. All-or-nothing across the request."""
    with db_engine.begin() as c:
        pm_role = _role_id(c, "project_manager")
        fin_role = _role_id(c, "finance")
        pid = _perm_id(c, "budgets.create")
        audits_before = _audit_count(c, pm_role, "Permission_Change")
        assert _grant_exists(c, pm_role, pid)
    r = _batch(admin, [
        {"role_id": pm_role, "add": [], "remove": ["budgets.create"]},
        {"role_id": fin_role, "add": ["no.such_permission"], "remove": []},
    ])
    assert r.status_code == 422, r.text
    with db_engine.begin() as c:
        assert _grant_exists(c, pm_role, pid), (
            "first change applied despite failed request — not transactional"
        )
        assert _revocation_row(c, pm_role, pid) is None
        assert _audit_count(c, pm_role, "Permission_Change") == audits_before, (
            "audit row written for a rolled-back request"
        )


def test_batch_multi_role_single_request(admin, db_engine):
    with db_engine.begin() as c:
        pm_role = _role_id(c, "project_manager")
        fin_role = _role_id(c, "finance")
        pid = _perm_id(c, "reports.export")
        assert _grant_exists(c, pm_role, pid)
        assert _grant_exists(c, fin_role, pid)
    try:
        r = _batch(admin, [
            {"role_id": pm_role, "add": [], "remove": ["reports.export"]},
            {"role_id": fin_role, "add": [], "remove": ["reports.export"]},
        ])
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["updated"]) == 2
        with db_engine.begin() as c:
            assert not _grant_exists(c, pm_role, pid)
            assert not _grant_exists(c, fin_role, pid)
    finally:
        r = _batch(admin, [
            {"role_id": pm_role, "add": ["reports.export"], "remove": []},
            {"role_id": fin_role, "add": ["reports.export"], "remove": []},
        ])
        assert r.status_code == 200, r.text


def test_batch_audit_row_per_role(admin, db_engine):
    """ONE Permission_Change audit row per mutated role; field_changes
    carry the sorted added/removed code lists (D7)."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
        before = _audit_count(c, rid, "Permission_Change")
    try:
        r = _batch(admin, [{"role_id": rid, "add": [],
                            "remove": ["reports.export"]}])
        assert r.status_code == 200, r.text
        with db_engine.begin() as c:
            assert _audit_count(c, rid, "Permission_Change") == before + 1
            row = _latest_audit(c, rid, "Permission_Change")
            assert row["resource_type"] == "role"
            changes = {fc["field"]: fc["new"] for fc in row["field_changes"]}
            assert changes["permissions_added"] == []
            assert changes["permissions_removed"] == ["reports.export"]
            assert row["metadata_json"]["role_code"] == "project_manager"
            assert row["metadata_json"]["removed_count"] == 1
            assert row["metadata_json"]["source"] == "b83_admin"
    finally:
        r = _batch(admin, [{"role_id": rid, "add": ["reports.export"],
                            "remove": []}])
        assert r.status_code == 200, r.text


def test_batch_effect_immediate_on_next_request(admin, pm, db_engine):
    """compute_effective_permissions runs per request (no cache): revoking
    budgets.view bites on the PM's very next budgets request."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
    probe = f"{BASE_URL}/api/v1/budgets/{uuid.uuid4()}"
    pre = pm.get(probe)
    assert pre.status_code != 403, (
        f"precondition: PM should hold budgets.view, got {pre.status_code}"
    )
    try:
        r = _batch(admin, [{"role_id": rid, "add": [],
                            "remove": ["budgets.view"]}])
        assert r.status_code == 200, r.text
        denied = pm.get(probe)
        assert denied.status_code == 403, denied.text
        assert "budgets.view" in denied.text
    finally:
        r = _batch(admin, [{"role_id": rid, "add": ["budgets.view"],
                            "remove": []}])
        assert r.status_code == 200, r.text
        restored = pm.get(probe)
        assert restored.status_code != 403


# ==========================================================================
# Role create — tests 19-25
# ==========================================================================

def test_create_role_requires_roles_admin(director):
    r = director.post(f"{BASE_URL}/api/roles",
                      json={"name": _uniq_role_name(),
                            "description": "should fail"})
    assert r.status_code == 403, r.text
    assert "roles.admin" in r.text


def test_create_role_defaults_match_d5_rule(admin, db_engine):
    """Granted set == permissions WHERE is_sensitive = false AND action NOT
    IN ('delete','admin','void') — set equality, both directions."""
    body = _create_custom_role(admin)
    try:
        actual = {p["code"] for p in body["permissions"]}
        with db_engine.begin() as c:
            expected = {row[0] for row in c.execute(text(
                "SELECT code FROM permissions "
                "WHERE is_sensitive = false "
                "  AND action NOT IN ('delete','admin','void')"
            ))}
        assert actual == expected, (
            f"missing={sorted(expected - actual)} "
            f"extra={sorted(actual - expected)}"
        )
    finally:
        _delete_role_sql(db_engine, body["id"])


def test_create_role_slug_generation(admin, db_engine):
    body = None
    try:
        r = admin.post(f"{BASE_URL}/api/roles",
                       json={"name": "Quantity Surveyor!",
                             "description": "QS test role"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["code"] == "quantity_surveyor"
        assert body["name"] == "Quantity Surveyor!"
    finally:
        if body:
            _delete_role_sql(db_engine, body["id"])


def test_create_role_code_collision_409(admin):
    """Name slugging to an existing system role code → 409, no auto-suffix."""
    r = admin.post(f"{BASE_URL}/api/roles",
                   json={"name": "Site Manager",
                         "description": "collides with system role"})
    assert r.status_code == 409, r.text
    assert "different name" in r.text


def test_create_role_defaults_is_system_false_priority_40(admin, db_engine):
    body = _create_custom_role(admin)
    try:
        assert body["is_system_role"] is False
        assert body["priority"] == 40
    finally:
        _delete_role_sql(db_engine, body["id"])


def test_create_role_audit_create_row(admin, db_engine):
    body = _create_custom_role(admin)
    try:
        with db_engine.begin() as c:
            row = _latest_audit(c, body["id"], "Create")
            assert row is not None, "no Create audit row for new role"
            assert row["resource_type"] == "role"
            assert row["metadata_json"]["role_code"] == body["code"]
            assert row["metadata_json"]["default_grants"] == len(body["permissions"])
            assert row["metadata_json"]["source"] == "b83_admin"
            assert row["actor_user_id"] is not None
    finally:
        _delete_role_sql(db_engine, body["id"])


def test_create_role_name_validation_422(admin):
    # Too short after strip.
    r = admin.post(f"{BASE_URL}/api/roles",
                   json={"name": "  ab ", "description": "x"})
    assert r.status_code == 422, r.text
    # Empty description.
    r = admin.post(f"{BASE_URL}/api/roles",
                   json={"name": _uniq_role_name(), "description": "   "})
    assert r.status_code == 422, r.text
    # Slug collapses to empty.
    r = admin.post(f"{BASE_URL}/api/roles",
                   json={"name": "!!! ???", "description": "no slug"})
    assert r.status_code == 422, r.text


# ==========================================================================
# Role delete — tests 26-29
# ==========================================================================

def test_delete_system_role_409(admin, db_engine):
    with db_engine.begin() as c:
        rid = _role_id(c, "site_manager")
    r = admin.delete(f"{BASE_URL}/api/roles/{rid}")
    assert r.status_code == 409, r.text
    assert "System roles cannot be deleted" in r.text


def test_delete_custom_role_with_any_user_roles_409(admin, db_engine):
    """A Revoked-status user_role STILL blocks deletion — the pre-check
    mirrors the DB-level FK ondelete=RESTRICT exactly (ANY row blocks)."""
    body = _create_custom_role(admin)
    role_id = body["id"]
    ur_id = str(uuid.uuid4())
    try:
        with db_engine.begin() as c:
            pm_user = _user_id(c, "test-pm@example.test")
            c.execute(text(
                "INSERT INTO user_roles (id, user_id, role_id, entity_scope, "
                "project_scope, view_overrides, assigned_by_user_id, status, "
                "created_at, updated_at) VALUES "
                "(:i, :u, :r, 'All', 'All', '[]'::jsonb, :u, 'Revoked', "
                "now(), now())"
            ), {"i": ur_id, "u": pm_user, "r": role_id})
        r = admin.delete(f"{BASE_URL}/api/roles/{role_id}")
        assert r.status_code == 409, r.text
        assert "assigned to 1 user(s)" in r.text
        # After removing the assignment the delete succeeds.
        with db_engine.begin() as c:
            c.execute(text("DELETE FROM user_roles WHERE id = :i"),
                      {"i": ur_id})
        r = admin.delete(f"{BASE_URL}/api/roles/{role_id}")
        assert r.status_code == 204, r.text
    finally:
        _delete_role_sql(db_engine, role_id)


def test_delete_custom_role_cascades_grants_and_revocations(admin, db_engine):
    body = _create_custom_role(admin)
    role_id = body["id"]
    # Create a revocation row via the endpoint (remove a default grant).
    r = _batch(admin, [{"role_id": role_id, "add": [],
                        "remove": ["projects.view"]}])
    assert r.status_code == 200, r.text
    with db_engine.begin() as c:
        grants = c.execute(text(
            "SELECT COUNT(*) FROM role_permissions WHERE role_id = :r"
        ), {"r": role_id}).scalar()
        revs = c.execute(text(
            "SELECT COUNT(*) FROM role_permission_revocations WHERE role_id = :r"
        ), {"r": role_id}).scalar()
        assert grants > 0 and revs == 1
    r = admin.delete(f"{BASE_URL}/api/roles/{role_id}")
    assert r.status_code == 204, r.text
    with db_engine.begin() as c:
        grants = c.execute(text(
            "SELECT COUNT(*) FROM role_permissions WHERE role_id = :r"
        ), {"r": role_id}).scalar()
        revs = c.execute(text(
            "SELECT COUNT(*) FROM role_permission_revocations WHERE role_id = :r"
        ), {"r": role_id}).scalar()
        assert grants == 0, "role_permissions rows survived role delete"
        assert revs == 0, "revocation rows survived role delete"


def test_delete_custom_role_audit_row(admin, db_engine):
    body = _create_custom_role(admin)
    role_id = body["id"]
    r = admin.delete(f"{BASE_URL}/api/roles/{role_id}")
    assert r.status_code == 204, r.text
    with db_engine.begin() as c:
        row = _latest_audit(c, role_id, "Delete")
        assert row is not None, "no Delete audit row"
        assert row["resource_type"] == "role"
        assert row["metadata_json"]["role_code"] == body["code"]
        assert row["metadata_json"]["source"] == "b83_admin"


# ==========================================================================
# Role patch + contract regressions — tests 30-34
# ==========================================================================

def test_patch_system_role_409(admin, db_engine):
    with db_engine.begin() as c:
        rid = _role_id(c, "site_manager")
    r = admin.patch(f"{BASE_URL}/api/roles/{rid}",
                    json={"name": "Hacked Site Manager"})
    assert r.status_code == 409, r.text
    assert "System role metadata is locked" in r.text


def test_patch_custom_role_rename_audit_field_diff(admin, db_engine):
    body = _create_custom_role(admin)
    role_id = body["id"]
    try:
        r = admin.patch(f"{BASE_URL}/api/roles/{role_id}",
                        json={"name": "B83 Renamed Role"})
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "B83 Renamed Role"
        assert r.json()["code"] == body["code"], "rename must never re-slug"
        with db_engine.begin() as c:
            row = _latest_audit(c, role_id, "Update")
            assert row is not None, "no Update audit row"
            fields = {fc["field"]: fc for fc in row["field_changes"]}
            assert "name" in fields
            assert fields["name"]["old"] == body["name"]
            assert fields["name"]["new"] == "B83 Renamed Role"
        # At-least-one-field rule: empty patch → 422.
        r = admin.patch(f"{BASE_URL}/api/roles/{role_id}", json={})
        assert r.status_code == 422, r.text
    finally:
        _delete_role_sql(db_engine, role_id)


def test_get_role_detail_contract_regression(admin, db_engine):
    """Existing RoleDetail shape is a published contract — byte-compatible
    keys, nothing added, nothing removed (§R3.6)."""
    with db_engine.begin() as c:
        rid = _role_id(c, "site_manager")
    r = admin.get(f"{BASE_URL}/api/roles/{rid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) == {
        "id", "code", "name", "description", "is_system_role",
        "priority", "permissions", "user_count",
    }
    assert body["permissions"], "system role should hold permissions"
    assert set(body["permissions"][0].keys()) == {
        "id", "code", "resource", "action", "description", "is_sensitive",
    }
    # List endpoint contract too.
    r = admin.get(f"{BASE_URL}/api/roles")
    assert r.status_code == 200
    assert set(r.json()[0].keys()) == {
        "id", "code", "name", "description", "is_system_role",
        "priority", "permission_count", "user_count",
    }


def test_permissions_batch_path_not_shadowed_by_role_id_route(admin, db_engine):
    """POST /roles/permissions-batch must reach the batch handler — not a
    422 from UUID coercion of 'permissions-batch' on a {role_id} route."""
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
    r = _batch(admin, [{"role_id": rid, "add": ["projects.view"],
                        "remove": []}])
    assert r.status_code == 200, (
        f"batch path shadowed or broken: {r.status_code} {r.text}"
    )
    assert "updated" in r.json()


def test_patch_requires_roles_admin(director, db_engine):
    with db_engine.begin() as c:
        rid = _role_id(c, "project_manager")
    r = director.patch(f"{BASE_URL}/api/roles/{rid}",
                       json={"name": "Director Was Here"})
    assert r.status_code == 403, r.text
    assert "roles.admin" in r.text
