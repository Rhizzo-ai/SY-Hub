"""NEW-CRIT-1 + H1 — Role-assignment privilege-escalation guards.

Security regression suite for the three rules layered into
`app/routers/users.py::assign_role` / `revoke_role`:

  1. Superset on grant   — actor may grant a role only if they personally
                           hold every permission that role grants.
  2. No self-assignment  — actor may never assign a role to their own account.
  3. Superset on revoke  — same superset test, plus a refusal to revoke the
                           last remaining active super_admin in the tenant.

Real Postgres via the running app (NOT mocked), conventions mirrored from
`test_role_permissions_admin.py` (BASE_URL, login helpers, `_role_id`,
direct-DB assertions). Each test asserts the HTTP status AND queries the
`user_roles` / `audit_log` tables — we never trust the response alone.

NOTE on tenant scoping (`get_current_tenant_id`): Phase-1 is single-tenant —
`get_current_tenant_id` always resolves the default "SY Homes" tenant
regardless of the authenticated user. The last-super_admin count in the
handler is therefore evaluated against the default tenant. The tenant-scoping
test (13) still exercises the real endpoint by seeding a super_admin in a
SECOND tenant and proving it does NOT count toward the default tenant's
"another super_admin exists" check.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, func, select, text

from tests.conftest import login_with_auto_enroll, plain_login

load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
            or "http://localhost:8001")
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ.get("TEST_USER_PASSWORD", "TestUser-Dev-2026!")

ADMIN_EMAIL = "test-admin@example.test"
READONLY_EMAIL = "test-readonly@example.test"
EDITOR_EMAIL = "test-esc-editor@example.test"

EDITOR_ROLE_CODE = "esc_test_editor"   # {users.edit, roles.view}
ZERO_ROLE_CODE = "esc_test_zero"       # no permissions


# --------------------------------------------------------------------------
# Low-level DB helpers (SQLAlchemy core + ORM)
# --------------------------------------------------------------------------

def _pw_hash() -> str:
    from app.auth.passwords import hash_password
    return hash_password(PWD)


def _default_tenant_id(c) -> str:
    name = os.environ.get("DEFAULT_TENANT_NAME", "SY Homes")
    return str(c.execute(
        text("SELECT id FROM tenants WHERE name = :n"), {"n": name}
    ).scalar())


def _role_id(c, role_code: str) -> str:
    return str(c.execute(
        text("SELECT id FROM roles WHERE code = :rc"), {"rc": role_code}
    ).scalar())


def _user_id(c, email: str) -> str:
    return str(c.execute(
        text("SELECT id FROM users WHERE email = :e"), {"e": email}
    ).scalar())


def _ur_status(c, ur_id: str):
    return c.execute(
        text("SELECT status FROM user_roles WHERE id = :i"), {"i": ur_id}
    ).scalar()


def _active_ur(c, user_id: str, role_code: str):
    return c.execute(text(
        "SELECT ur.id FROM user_roles ur JOIN roles r ON r.id = ur.role_id "
        "WHERE ur.user_id = :u AND r.code = :rc AND ur.status = 'Active'"
    ), {"u": user_id, "rc": role_code}).scalar()


def _latest_perm_audit(c, resource_id: str):
    return c.execute(text(
        "SELECT metadata_json FROM audit_log "
        "WHERE resource_id = :rid AND action = 'Permission_Change' "
        "ORDER BY created_at DESC LIMIT 1"
    ), {"rid": resource_id}).scalar()


# ---- ORM-based creators (defaults handled by the models) -----------------

def _ensure_custom_role(code: str, name: str, perm_codes: list[str]) -> str:
    """Idempotent: reuse the custom role if it already exists (it is never
    deleted in teardown), else create it with the given permission set."""
    from app.db import SessionLocal
    from app.models.rbac import Role, Permission, role_permissions
    db = SessionLocal()
    try:
        role = db.scalar(select(Role).where(Role.code == code))
        if role is None:
            role = Role(code=code, name=name,
                        description="esc escalation test role",
                        is_system_role=False, priority=999)
            db.add(role)
            db.flush()
            for pc in perm_codes:
                pid = db.scalar(select(Permission.id).where(Permission.code == pc))
                assert pid is not None, f"permission {pc} not seeded"
                db.execute(role_permissions.insert().values(
                    role_id=role.id, permission_id=pid))
        rid = str(role.id)
        db.commit()
        return rid
    finally:
        db.close()


def _mk_user(tenant_id: str, email: str, role_id: str | None = None,
             assigner_id: str | None = None) -> str:
    from app.db import SessionLocal
    from app.models.user import User
    from app.models.rbac import UserRole
    db = SessionLocal()
    try:
        u = User(
            tenant_id=uuid.UUID(tenant_id), email=email, email_verified=True,
            password_hash=_PW_HASH, password_algorithm="argon2id",
            password_changed_at=datetime.now(timezone.utc), password_history=[],
            first_name="Esc", last_name="Test", display_name="Esc Test",
            user_type="Internal", status="Active",
        )
        db.add(u)
        db.flush()
        uid = str(u.id)
        if role_id:
            ur = UserRole(
                user_id=u.id, role_id=uuid.UUID(role_id), entity_scope="All",
                project_scope="All", view_overrides=[],
                assigned_by_user_id=uuid.UUID(assigner_id) if assigner_id else u.id,
                status="Active",
            )
            db.add(ur)
            db.flush()
        db.commit()
        return uid
    finally:
        db.close()


def _seed_assignment(target_id: str, role_code: str, assigner_id: str) -> str:
    """Directly create an Active assignment of `role_code` on `target_id`."""
    from app.db import SessionLocal
    from app.models.rbac import Role, UserRole
    db = SessionLocal()
    try:
        role_id = db.scalar(select(Role.id).where(Role.code == role_code))
        ur = UserRole(
            user_id=uuid.UUID(target_id), role_id=role_id, entity_scope="All",
            project_scope="All", view_overrides=[],
            assigned_by_user_id=uuid.UUID(assigner_id), status="Active",
        )
        db.add(ur)
        db.flush()
        urid = str(ur.id)
        db.commit()
        return urid
    finally:
        db.close()


def _ensure_editor_user(tenant_id: str, editor_role_id: str, admin_id: str) -> str:
    """Idempotent: the editor logs in (so it accrues append-only login_history
    and cannot be deleted). Reuse it across runs — reset its password/MFA and
    ensure it holds an Active esc_test_editor assignment."""
    from app.db import SessionLocal
    from app.models.user import User
    from app.models.rbac import UserRole
    db = SessionLocal()
    try:
        u = db.scalar(select(User).where(User.email == EDITOR_EMAIL))
        if u is None:
            u = User(
                tenant_id=uuid.UUID(tenant_id), email=EDITOR_EMAIL,
                email_verified=True, password_hash=_PW_HASH,
                password_algorithm="argon2id",
                password_changed_at=datetime.now(timezone.utc),
                password_history=[], first_name="Esc", last_name="Editor",
                display_name="Esc Editor", user_type="Internal", status="Active",
            )
            db.add(u)
            db.flush()
        else:
            u.password_hash = _PW_HASH
            u.password_history = []
            u.status = "Active"
            u.failed_login_attempts = 0
            u.locked_until = None
            u.mfa_enabled = False
            u.mfa_secret_encrypted = None
            u.mfa_backup_codes_encrypted = None
        # Ensure an Active assignment of the editor role.
        existing = db.scalar(select(UserRole).where(
            UserRole.user_id == u.id,
            UserRole.role_id == uuid.UUID(editor_role_id),
            UserRole.status == "Active",
        ))
        if existing is None:
            db.add(UserRole(
                user_id=u.id, role_id=uuid.UUID(editor_role_id),
                entity_scope="All", project_scope="All", view_overrides=[],
                assigned_by_user_id=uuid.UUID(admin_id), status="Active",
            ))
        uid = str(u.id)
        db.commit()
        return uid
    finally:
        db.close()


def _new_target(tenant_id: str) -> str:
    return _mk_user(tenant_id, f"test-esc-tgt-{uuid.uuid4().hex[:10]}@example.test")


_PW_HASH = None  # set in the `seed` fixture once the app is importable


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


def _cleanup_targets(eng):
    """Remove all per-test artefacts so the suite leaves zero footprint.

    Deletes: every esc role-assignment, the two custom roles (+ their
    role_permissions), the per-test target / other-tenant users, and any
    synthetic second tenant. The editor USER row itself is intentionally
    retained — it logs in and therefore carries append-only
    user_login_history rows that block deletion (FK SET NULL is denied). It
    is left role-less and reused idempotently on the next run, so it never
    pollutes role/permission counts.
    """
    with eng.begin() as c:
        # 1. Drop every role assignment held by an esc test user (incl. editor).
        c.execute(text(
            "DELETE FROM user_roles WHERE user_id IN "
            "(SELECT id FROM users WHERE email LIKE 'test-esc%@example.test')"))
        # 2. Drop the custom roles (and their permission grants) — restores the
        #    seeded role/permission counts exactly.
        c.execute(text(
            "DELETE FROM role_permissions WHERE role_id IN "
            "(SELECT id FROM roles WHERE code LIKE 'esc_test_%')"))
        c.execute(text("DELETE FROM roles WHERE code LIKE 'esc_test_%'"))
        # 3. Delete the non-login users (targets + other-tenant probes).
        c.execute(text(
            "DELETE FROM users WHERE email LIKE 'test-esc-tgt-%' "
            "OR email LIKE 'test-esc-other-%'"))
        # 4. Synthetic second tenant(s) from the tenant-scoping test.
        c.execute(text(
            "DELETE FROM user_roles WHERE user_id IN (SELECT id FROM users "
            "WHERE tenant_id IN (SELECT id FROM tenants WHERE name LIKE 'ESC Other%'))"))
        c.execute(text(
            "DELETE FROM users WHERE tenant_id IN "
            "(SELECT id FROM tenants WHERE name LIKE 'ESC Other%')"))
        c.execute(text("DELETE FROM tenants WHERE name LIKE 'ESC Other%'"))


@pytest.fixture(scope="module")
def seed(engine):
    global _PW_HASH
    _PW_HASH = _pw_hash()

    # Make the seeded users password-loginable / MFA-clean. test-admin is an
    # MFA-enforced super_admin — reset its MFA so login_with_auto_enroll
    # re-enrolls fresh (and caches the TOTP secret) in this session rather
    # than skipping on a stale prior enrolment.
    with engine.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email IN (:admin, :ro)
        """), {"admin": ADMIN_EMAIL, "ro": READONLY_EMAIL})

    _cleanup_targets(engine)

    with engine.connect() as c:
        tenant_id = _default_tenant_id(c)
        admin_id = _user_id(c, ADMIN_EMAIL)

    editor_role_id = _ensure_custom_role(
        EDITOR_ROLE_CODE, "Esc Test Editor", ["users.edit", "roles.view"])
    zero_role_id = _ensure_custom_role(ZERO_ROLE_CODE, "Esc Test Zero", [])
    editor_id = _ensure_editor_user(tenant_id, editor_role_id, admin_id)

    data = {
        "tenant_id": tenant_id,
        "admin_id": admin_id,
        "editor_id": editor_id,
        "editor_role_id": editor_role_id,
        "zero_role_id": zero_role_id,
    }
    yield data

    _cleanup_targets(engine)


@pytest.fixture(scope="module")
def admin(seed):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def editor(seed):
    return plain_login(BASE_URL, EDITOR_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly(seed):
    return plain_login(BASE_URL, READONLY_EMAIL, PWD)


def _grant(session, target_id: str, role_id: str, **extra):
    body = {"role_id": role_id, "entity_scope": "All", "project_scope": "All"}
    body.update(extra)
    return session.post(f"{BASE_URL}/api/users/{target_id}/roles", json=body)


def _revoke(session, target_id: str, ur_id: str):
    return session.delete(f"{BASE_URL}/api/users/{target_id}/roles/{ur_id}")


# ==========================================================================
# Grant — superset rule
# ==========================================================================

def test_grant_role_blocked_when_actor_missing_a_permission(engine, seed, editor):
    """users.edit + roles.view holder (NOT a superset of director) granting
    director → 403; no assignment created."""
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        director_role = _role_id(c, "director")
    r = _grant(editor, target, director_role)
    assert r.status_code == 403, r.text
    assert "director" in r.json()["detail"]
    with engine.connect() as c:
        assert _active_ur(c, target, "director") is None


def test_grant_role_allowed_when_actor_holds_all_permissions(engine, seed, admin):
    """super_admin (full catalogue ⊇ director) grants director → 201."""
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        director_role = _role_id(c, "director")
    r = _grant(admin, target, director_role)
    assert r.status_code == 201, r.text
    with engine.connect() as c:
        assert _active_ur(c, target, "director") is not None


def test_grant_finance_blocked_for_non_finance_editor(engine, seed, editor):
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        finance_role = _role_id(c, "finance")
    r = _grant(editor, target, finance_role)
    assert r.status_code == 403, r.text
    assert "finance" in r.json()["detail"]
    with engine.connect() as c:
        assert _active_ur(c, target, "finance") is None


def test_grant_super_admin_blocked_for_non_super_admin(engine, seed, editor):
    """Now blocked via the generic superset rule (not the old special-case)."""
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        sa_role = _role_id(c, "super_admin")
    r = _grant(editor, target, sa_role)
    assert r.status_code == 403, r.text
    assert "super_admin" in r.json()["detail"]
    with engine.connect() as c:
        assert _active_ur(c, target, "super_admin") is None


def test_grant_super_admin_allowed_for_super_admin(engine, seed, admin):
    """super_admin grants super_admin to another user → 201. Cleaned up so
    the tenant super_admin count is not inflated for later tests."""
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        sa_role = _role_id(c, "super_admin")
    r = _grant(admin, target, sa_role)
    assert r.status_code == 201, r.text
    with engine.connect() as c:
        ur = _active_ur(c, target, "super_admin")
        assert ur is not None
    # Clean up the extra super_admin grant immediately.
    with engine.begin() as c:
        c.execute(text("DELETE FROM user_roles WHERE id = :i"), {"i": str(ur)})


def test_grant_zero_permission_role_allowed(engine, seed, editor):
    """A role granting zero permissions confers no power to escalate to, so
    any users.edit holder may grant it → 201 (documents empty-set semantics)."""
    target = _new_target(seed["tenant_id"])
    r = _grant(editor, target, seed["zero_role_id"])
    assert r.status_code == 201, r.text
    with engine.connect() as c:
        assert _active_ur(c, target, ZERO_ROLE_CODE) is not None


# ==========================================================================
# Grant — self-assignment
# ==========================================================================

def test_cannot_assign_role_to_self_even_as_super_admin(engine, seed, admin):
    """super_admin assigning ANY role to their own account → 403."""
    with engine.connect() as c:
        ro_role = _role_id(c, "read_only")
    admin_id = seed["admin_id"]
    r = _grant(admin, admin_id, ro_role)
    assert r.status_code == 403, r.text
    assert "own account" in r.json()["detail"]
    with engine.connect() as c:
        assert _active_ur(c, admin_id, "read_only") is None


def test_cannot_assign_role_to_self_non_admin(engine, seed, editor):
    """users.edit holder assigning to self → 403; self-check fires BEFORE the
    superset check (message is the self-assignment one, not the superset one)."""
    with engine.connect() as c:
        director_role = _role_id(c, "director")
    editor_id = seed["editor_id"]
    r = _grant(editor, editor_id, director_role)
    assert r.status_code == 403, r.text
    assert "own account" in r.json()["detail"]
    with engine.connect() as c:
        assert _active_ur(c, editor_id, "director") is None


# ==========================================================================
# Revoke — superset rule
# ==========================================================================

def test_revoke_role_blocked_when_actor_missing_a_permission(engine, seed, editor):
    target = _new_target(seed["tenant_id"])
    ur = _seed_assignment(target, "director", seed["admin_id"])
    r = _revoke(editor, target, ur)
    assert r.status_code == 403, r.text
    with engine.connect() as c:
        assert _ur_status(c, ur) == "Active"  # untouched


def test_revoke_role_allowed_when_actor_holds_all_permissions(engine, seed, admin):
    target = _new_target(seed["tenant_id"])
    ur = _seed_assignment(target, "director", seed["admin_id"])
    r = _revoke(admin, target, ur)
    assert r.status_code == 204, r.text
    with engine.connect() as c:
        assert _ur_status(c, ur) == "Revoked"


# ==========================================================================
# Revoke — last super_admin protection
# ==========================================================================

def _active_super_admin_urs(c, tenant_id: str, exclude_ur: str | None = None):
    rows = c.execute(text(
        "SELECT ur.id FROM user_roles ur "
        "JOIN roles r ON r.id = ur.role_id "
        "JOIN users u ON u.id = ur.user_id "
        "WHERE r.code = 'super_admin' AND ur.status = 'Active' "
        "  AND u.tenant_id = :t"
    ), {"t": tenant_id}).scalars().all()
    return [str(x) for x in rows if str(x) != (exclude_ur or "")]


def test_cannot_revoke_last_super_admin(engine, seed, admin):
    """Reduce the default tenant to exactly one active super_admin (test-admin),
    then attempt to revoke it → 409; the assignment stays Active."""
    tenant_id = seed["tenant_id"]
    with engine.connect() as c:
        admin_id = seed["admin_id"]
        admin_sa_ur = str(_active_ur(c, admin_id, "super_admin"))
        others = _active_super_admin_urs(c, tenant_id, exclude_ur=admin_sa_ur)
    try:
        with engine.begin() as c:
            for oid in others:
                c.execute(text("UPDATE user_roles SET status='Revoked' WHERE id=:i"),
                          {"i": oid})
        r = _revoke(admin, admin_id, admin_sa_ur)
        assert r.status_code == 409, r.text
        assert "last super_admin" in r.json()["detail"]
        with engine.connect() as c:
            assert _ur_status(c, admin_sa_ur) == "Active"
    finally:
        with engine.begin() as c:
            for oid in others:
                c.execute(text(
                    "UPDATE user_roles SET status='Active', revoked_at=NULL, "
                    "revoked_by_user_id=NULL, revoked_reason=NULL WHERE id=:i"),
                    {"i": oid})


def test_can_revoke_super_admin_when_another_exists(engine, seed, admin):
    """With ≥2 active super_admins, revoking one → 204; another remains."""
    tenant_id = seed["tenant_id"]
    target = _new_target(tenant_id)
    ur = _seed_assignment(target, "super_admin", seed["admin_id"])
    r = _revoke(admin, target, ur)
    assert r.status_code == 204, r.text
    with engine.connect() as c:
        assert _ur_status(c, ur) == "Revoked"
        remaining = c.execute(text(
            "SELECT count(*) FROM user_roles ur "
            "JOIN roles r ON r.id = ur.role_id "
            "JOIN users u ON u.id = ur.user_id "
            "WHERE r.code='super_admin' AND ur.status='Active' AND u.tenant_id=:t"
        ), {"t": tenant_id}).scalar()
        assert remaining >= 1


def test_last_super_admin_count_is_tenant_scoped(engine, seed, admin):
    """A super_admin in a DIFFERENT tenant must NOT count toward the default
    tenant's 'another super_admin exists' check. Seed an other-tenant
    super_admin, reduce the default tenant to one active super_admin, then
    attempt to revoke it → still 409 (proves the join is tenant-scoped)."""
    tenant_id = seed["tenant_id"]
    from app.db import SessionLocal
    from app.models.tenant import Tenant
    from app.models.user import User
    from app.models.rbac import Role, UserRole

    # --- Seed a second tenant with one active super_admin ---
    db = SessionLocal()
    try:
        other = Tenant(name=f"ESC Other Tenant {uuid.uuid4().hex[:6]}")
        db.add(other)
        db.flush()
        sa_role_id = db.scalar(select(Role.id).where(Role.code == "super_admin"))
        ou = User(
            tenant_id=other.id,
            email=f"test-esc-other-{uuid.uuid4().hex[:8]}@example.test",
            email_verified=True, password_hash=_PW_HASH,
            password_algorithm="argon2id",
            password_changed_at=datetime.now(timezone.utc), password_history=[],
            first_name="Esc", last_name="Other", display_name="Esc Other",
            user_type="Internal", status="Active",
        )
        db.add(ou)
        db.flush()
        db.add(UserRole(user_id=ou.id, role_id=sa_role_id, entity_scope="All",
                        project_scope="All", view_overrides=[],
                        assigned_by_user_id=ou.id, status="Active"))
        other_tid = str(other.id)
        db.commit()
    finally:
        db.close()

    with engine.connect() as c:
        admin_id = seed["admin_id"]
        admin_sa_ur = str(_active_ur(c, admin_id, "super_admin"))
        others = _active_super_admin_urs(c, tenant_id, exclude_ur=admin_sa_ur)

    try:
        with engine.begin() as c:
            for oid in others:
                c.execute(text("UPDATE user_roles SET status='Revoked' WHERE id=:i"),
                          {"i": oid})
        # Default tenant now has exactly one active super_admin; the
        # other-tenant super_admin must be excluded by the join → 409.
        r = _revoke(admin, admin_id, admin_sa_ur)
        assert r.status_code == 409, r.text
        with engine.connect() as c:
            assert _ur_status(c, admin_sa_ur) == "Active"
    finally:
        with engine.begin() as c:
            for oid in others:
                c.execute(text(
                    "UPDATE user_roles SET status='Active', revoked_at=NULL, "
                    "revoked_by_user_id=NULL, revoked_reason=NULL WHERE id=:i"),
                    {"i": oid})
            c.execute(text(
                "DELETE FROM user_roles WHERE user_id IN "
                "(SELECT id FROM users WHERE tenant_id=:t)"), {"t": other_tid})
            c.execute(text("DELETE FROM users WHERE tenant_id=:t"), {"t": other_tid})
            c.execute(text("DELETE FROM tenants WHERE id=:t"), {"t": other_tid})


# ==========================================================================
# Audit of blocked attempts
# ==========================================================================

def test_blocked_grant_writes_denial_audit(engine, seed, editor):
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        director_role = _role_id(c, "director")
    r = _grant(editor, target, director_role)
    assert r.status_code == 403, r.text
    with engine.connect() as c:
        m = _latest_perm_audit(c, target)
    assert m is not None
    assert m["kind"] == "role_assignment_denied"
    assert m["rule"] == "superset"
    assert m["role_code"] == "director"


def test_blocked_revoke_writes_denial_audit(engine, seed, editor):
    target = _new_target(seed["tenant_id"])
    ur = _seed_assignment(target, "director", seed["admin_id"])
    r = _revoke(editor, target, ur)
    assert r.status_code == 403, r.text
    with engine.connect() as c:
        m = _latest_perm_audit(c, target)
    assert m is not None
    assert m["kind"] == "role_revocation_denied"
    assert m["rule"] == "superset"


def test_successful_grant_still_audits(engine, seed, admin):
    """Regression: the existing success-path audit still fires."""
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        ro_role = _role_id(c, "read_only")
    r = _grant(admin, target, ro_role)
    assert r.status_code == 201, r.text
    with engine.connect() as c:
        m = _latest_perm_audit(c, target)
    assert m is not None
    assert m["kind"] == "role_assignment"


# ==========================================================================
# Regression / guards intact
# ==========================================================================

def test_assign_role_still_requires_users_edit(engine, seed, readonly):
    """A caller lacking users.edit is rejected by the dependency (403),
    unchanged by the new in-handler checks."""
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        ro_role = _role_id(c, "read_only")
    r = _grant(readonly, target, ro_role)
    assert r.status_code == 403, r.text
    assert "users.edit" in r.json()["detail"]
    with engine.connect() as c:
        assert _active_ur(c, target, "read_only") is None


def test_revoke_already_revoked_is_idempotent(engine, seed, admin):
    target = _new_target(seed["tenant_id"])
    ur = _seed_assignment(target, "read_only", seed["admin_id"])
    r1 = _revoke(admin, target, ur)
    assert r1.status_code == 204, r1.text
    # Second revoke of an already-Revoked assignment is a no-op early return.
    r2 = _revoke(admin, target, ur)
    assert r2.status_code == 204, r2.text
    with engine.connect() as c:
        assert _ur_status(c, ur) == "Revoked"


def test_invalid_entity_scope_still_422(engine, seed, admin):
    """The pre-existing 422 validation on entity_scope must still fire — it
    runs ahead of the new security checks, proving placement is correct."""
    target = _new_target(seed["tenant_id"])
    with engine.connect() as c:
        director_role = _role_id(c, "director")
    r = _grant(admin, target, director_role, entity_scope="Bogus")
    assert r.status_code == 422, r.text
