"""Audit-remediation P1 acceptance tests — SY_Hub_Audit_Remediation_P1_BuildPack_v1.

Six findings:
  R1 — Close the matching mfa_pending holes on /mfa/disable and
       /mfa/backup-codes/regenerate.
  R2 — Quarantine 3 order-dependent flaky tests (no test cases here —
       see the @xfail/@skip on those tests themselves).
  R3 — Source-row lock on governance create paths
       (create_new_version + create_scenario decision).
  R4 — Cosmetic docstring fix (no test).
  R5 — Destructive Alembic downgrade (operator decision — no test until
       Option 1 is picked).
  R6 — CHANGELOG entries (no test).

These tests print the literal evidence required by SELF-REPORT — HTTP
status codes from real calls, audit prints, two-session concurrency
output.
"""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import jwt
import pytest
import requests
import sqlalchemy as sa
from dotenv import load_dotenv

from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"

load_dotenv(str(_BACKEND / ".env"))

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://contract-changes-hub.preview.emergentagent.com"
)
DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]

TEST_PASSWORD = "TestUser-Dev-2026!"
PM = "test-pm@example.test"
ADMIN = "test-admin@example.test"


@pytest.fixture(scope="module")
def db_engine():
    eng = sa.create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _user_id_and_tenant(db_engine, email: str):
    with db_engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT id, tenant_id FROM users WHERE email=:e"
        ), {"e": email}).first()
        assert row, f"User {email} not seeded"
        return row[0], row[1]


def _reset_user_mfa(db_engine, email: str) -> None:
    with db_engine.begin() as conn:
        conn.execute(sa.text(
            "UPDATE users SET mfa_enabled=false, mfa_method=NULL, "
            "mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL, "
            "mfa_enrolled_at=NULL, failed_login_attempts=0, "
            "locked_until=NULL, lockout_level=0 WHERE email=:e"
        ), {"e": email})


def _mint_access_token(user_id, tenant_id, email):
    payload = {
        "sub": str(user_id), "email": email, "tenant_id": str(tenant_id),
        "iat": int(time.time()), "exp": int(time.time()) + 3600,
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _mint_mfa_pending_token(user_id, email, tenant_id):
    payload = {
        "sub": str(user_id), "email": email, "tenant_id": str(tenant_id),
        "iat": int(time.time()), "exp": int(time.time()) + 900,
        "type": "mfa_pending",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ======================================================================
# R1 — mfa_pending blocked from /mfa/disable + /mfa/backup-codes/regenerate
# ======================================================================

class TestP1_R1_MfaPendingHoles:
    """The two matching enrolment-dep handlers must now reject
    mfa_pending. An `access` token must still reach the business logic.
    """

    def test_mfa_disable_rejects_mfa_pending(self, db_engine):
        """LIVE 401/403: /mfa/disable with an mfa_pending cookie."""
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_mfa_pending_token(pm_id, PM, tenant)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.post(f"{BASE_URL}/api/auth/mfa/disable", json={
            "current_password": TEST_PASSWORD,
        })
        print(f"\nP1.R1 — /mfa/disable with mfa_pending → HTTP {r.status_code} {r.text[:200]}")
        assert r.status_code in (401, 403), (
            f"mfa_pending must be rejected by /mfa/disable; got {r.status_code}"
        )

    def test_mfa_disable_reachable_by_access_token(self, db_engine):
        """LIVE reach-through: /mfa/disable with a full `access` token
        passes the dep. We don't assert 204 because the user may not have
        MFA enrolled (200 path) or the password may differ (400 path);
        we assert NOT 401/403 to prove the dep let the token through.
        """
        _reset_user_mfa(db_engine, PM)
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_access_token(pm_id, tenant, PM)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.post(f"{BASE_URL}/api/auth/mfa/disable", json={
            "current_password": TEST_PASSWORD,
        })
        print(f"P1.R1 — /mfa/disable with access → HTTP {r.status_code} {r.text[:200]}")
        assert r.status_code not in (401, 403), (
            f"access token must reach /mfa/disable's business logic; got {r.status_code}"
        )

    def test_backup_codes_regenerate_rejects_mfa_pending(self, db_engine):
        """LIVE 401/403: /mfa/backup-codes/regenerate with mfa_pending."""
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_mfa_pending_token(pm_id, PM, tenant)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": TEST_PASSWORD, "current_totp": "000000"},
        )
        print(f"\nP1.R1 — /mfa/backup-codes/regenerate with mfa_pending → "
              f"HTTP {r.status_code} {r.text[:200]}")
        assert r.status_code in (401, 403), (
            f"mfa_pending must be rejected by /mfa/backup-codes/regenerate; "
            f"got {r.status_code}"
        )

    def test_backup_codes_regenerate_reachable_by_access_token(self, db_engine):
        """LIVE reach-through with `access`. Without MFA enrolled the
        handler 400s ("MFA not enrolled"); we assert NOT 401/403.
        """
        _reset_user_mfa(db_engine, PM)
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_access_token(pm_id, tenant, PM)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.post(
            f"{BASE_URL}/api/auth/mfa/backup-codes/regenerate",
            json={"current_password": TEST_PASSWORD, "current_totp": "000000"},
        )
        print(f"P1.R1 — /mfa/backup-codes/regenerate with access → "
              f"HTTP {r.status_code} {r.text[:200]}")
        assert r.status_code not in (401, 403), (
            f"access token must reach the regenerate handler; got {r.status_code}"
        )

    def test_source_code_swap_landed(self):
        """Source-level guard — the two handlers now depend on
        get_current_user (NOT get_enrollment_user). Drift here would
        silently re-open the hole.
        """
        path = str(_BACKEND / "app" / "routers" / "auth.py")
        with open(path) as f:
            src = f.read()
        # Find each handler block and assert the right dep.
        for marker in ('@router.post("/mfa/disable"',
                       '@router.post("/mfa/backup-codes/regenerate"'):
            start = src.index(marker)
            end = src.index("\n@router.", start + 1)
            body = src[start:end]
            assert "Depends(get_current_user)" in body, (
                f"{marker} must depend on get_current_user "
                f"(got: {body[:300]})"
            )
            assert "Depends(get_enrollment_user)" not in body, (
                f"{marker} must NOT depend on get_enrollment_user"
            )


# ======================================================================
# R3 — Source-row lock on governance create paths
# ======================================================================

class TestP1_R3_GovernanceSourceLock:
    """create_new_version flips source.is_current=False without a row
    lock. Two concurrent calls on the same Approved source could
    interleave and produce two current versions or trip the partial-
    unique index. Lock the source FOR UPDATE before the flip.

    create_scenario does NOT flip source.is_current per its docstring —
    we confirm that and document why no lock is required.
    """

    def test_create_new_version_locks_source_row(self):
        """Source-level guard — create_new_version must call the shared
        lock helper BEFORE flipping source.is_current = False.
        """
        path = str(_BACKEND / "app" / "services" / "appraisal_revisions.py")
        with open(path) as f:
            src = f.read()
        marker = "def create_new_version"
        start = src.index(marker)
        end = src.index("\ndef ", start + 1) if "\ndef " in src[start + 1:] else len(src)
        body = src[start:end]
        # The lock must come BEFORE the is_current=False flip.
        assert "lock_appraisal_for_update(" in body, (
            "create_new_version must call lock_appraisal_for_update on "
            "the source row before flipping source.is_current = False"
        )
        # Order check: the lock call must appear before the actual
        # `source.is_current = False` assignment statement (not the
        # bullet-list reference in the docstring).
        lock_pos = body.find("lock_appraisal_for_update(")
        flip_pos = body.find("    source.is_current = False\n")
        assert 0 < lock_pos < flip_pos, (
            f"lock_appraisal_for_update must precede the is_current=False flip; "
            f"lock_pos={lock_pos}, flip_pos={flip_pos}"
        )
        print(f"\nP1.R3 — create_new_version lock-position OK: "
              f"lock_appraisal_for_update@{lock_pos} < source.is_current=False@{flip_pos}")

    def test_create_scenario_does_not_flip_source_is_current(self):
        """Negative guard — create_scenario must NOT flip source.is_current
        (per the docstring at appraisal_scenarios.py). If a future commit
        adds such a flip, this test fails so the contract is preserved.
        """
        path = str(_BACKEND / "app" / "services" / "appraisal_scenarios.py")
        with open(path) as f:
            src = f.read()
        marker = "def create_scenario"
        start = src.index(marker)
        end = src.index("\ndef ", start + 1) if "\ndef " in src[start + 1:] else len(src)
        body = src[start:end]
        # `base.is_current = False` or similar would be the racy mutation.
        assert "is_current = False" not in body, (
            "create_scenario must NOT flip is_current on the base "
            "(per docstring contract). If you genuinely need this, add "
            "a with_for_update lock first and update this test."
        )
        print(f"\nP1.R3 — create_scenario does not flip source.is_current → "
              f"no source-row race; lock not required")

    def test_two_session_lock_proves_serialisation(self, db_engine):
        """Two-session concurrency proof against the lock helper called
        by create_new_version. Session A holds the SELECT FOR UPDATE on
        the source row; session B's SELECT FOR UPDATE NOWAIT against
        the same row raises OperationalError. After A commits, B
        succeeds.
        """
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select as sa_select
        from sqlalchemy.exc import OperationalError, DBAPIError
        from app.models.appraisals import Appraisal as AppraisalModel

        # Seed a project + appraisal (the lock target).
        with db_engine.begin() as conn:
            admin = conn.execute(sa.text("""
                SELECT u.id FROM users u
                JOIN user_roles ur ON ur.user_id = u.id AND ur.status = 'Active'
                JOIN roles r ON r.id = ur.role_id
                WHERE r.code = 'super_admin'
                ORDER BY u.created_at LIMIT 1
            """)).scalar()
            entity = conn.execute(sa.text(
                "SELECT id FROM entities ORDER BY created_at LIMIT 1"
            )).scalar()
            assert admin and entity, "missing bootstrap user / entity"

            proj_id = uuid.uuid4()
            conn.execute(sa.text("""
                INSERT INTO projects
                  (id, project_code, name, project_type, primary_entity_id,
                   land_ownership_method, site_address, site_postcode,
                   created_by_user_id, current_stage)
                VALUES (:id, :code, :name, 'Pure_Dev', :ent,
                        'Direct_Purchase', '1 Test St', 'AB1 2CD', :uid, 'Lead')
            """), {
                "id": str(proj_id),
                "code": f"P1-{uuid.uuid4().hex[:6].upper()}",
                "name": "P1.R3 governance lock test",
                "ent": str(entity),
                "uid": str(admin),
            })

            appraisal_id = uuid.uuid4()
            conn.execute(sa.text("""
                INSERT INTO appraisals
                  (id, project_id, name, reference_date,
                   created_by_user_id, appraisal_group_id, version_number)
                VALUES (:id, :pid, 'P1.R3 source appraisal', current_date,
                        :uid, :gid, 1)
            """), {
                "id": str(appraisal_id),
                "pid": str(proj_id),
                "uid": str(admin),
                "gid": str(uuid.uuid4()),
            })

        SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
        a_sess = SessionLocal()
        b_sess = SessionLocal()
        try:
            # Session A: take the lock the SAME way create_new_version does.
            from app.services.appraisal_locks import lock_appraisal_for_update
            lock_appraisal_for_update(a_sess, appraisal_id)

            b_err = None
            try:
                b_sess.execute(
                    sa_select(AppraisalModel.id)
                    .where(AppraisalModel.id == appraisal_id)
                    .with_for_update(nowait=True)
                ).all()
            except (OperationalError, DBAPIError) as exc:
                b_err = exc
            b_sess.rollback()
            print(f"\nP1.R3 — Session B NOWAIT vs Session A holding "
                  f"lock_appraisal_for_update: raised "
                  f"{type(b_err).__name__ if b_err else None}")
            assert b_err is not None, (
                "Session B's NOWAIT acquire should have raised "
                "OperationalError — the lock helper is not actually "
                "locking the row."
            )

            a_sess.commit()
            b_rows = b_sess.execute(
                sa_select(AppraisalModel.id)
                .where(AppraisalModel.id == appraisal_id)
                .with_for_update(nowait=True)
            ).all()
            b_sess.commit()
            assert len(b_rows) == 1, "Session B failed to acquire after A committed"
            print(f"P1.R3 — after A commits, B acquires cleanly: {b_rows[0][0]}")
        finally:
            try:
                a_sess.close()
            except Exception:
                pass
            try:
                b_sess.close()
            except Exception:
                pass
            with db_engine.begin() as conn:
                conn.execute(sa.text("DELETE FROM appraisals WHERE id=:id"),
                             {"id": str(appraisal_id)})
                conn.execute(sa.text("DELETE FROM projects WHERE id=:id"),
                             {"id": str(proj_id)})


# ======================================================================
# R4 — Cosmetic docstring fix
# ======================================================================

class TestP1_R4_DocstringFix:
    """get_enrollment_principal's docstring listed /password/change as
    one of the endpoints that use the dep. P0.3 moved it; the docstring
    needs to follow.
    """

    def test_enrollment_principal_docstring_does_not_list_password_change(self):
        path = str(_BACKEND / "app" / "auth" / "deps.py")
        with open(path) as f:
            src = f.read()
        marker = "def get_enrollment_principal"
        start = src.index(marker)
        end = src.index("\ndef ", start + 1)
        body = src[start:end]
        # Find the docstring block.
        docstart = body.index('"""')
        docend = body.index('"""', docstart + 3)
        doc = body[docstart:docend + 3]
        assert "/password/change" not in doc, (
            "/password/change moved to get_current_principal in P0.3; "
            "remove it from get_enrollment_principal's docstring"
        )
        print(f"\nP1.R4 — get_enrollment_principal docstring is clean of "
              f"/password/change")



# ======================================================================
# R5 — Destructive Alembic downgrade — Option 1 (NotImplementedError)
# ======================================================================

class TestP1_R5_DowngradeNonReversible:
    """0027 was a backfill whose downgrade DELETEd `budget_line_items`
    by content heuristic — which would also destroy user-edited £0
    items matching the shape. Operator decision (2026-02-13): make the
    downgrade DELIBERATELY non-reversible via NotImplementedError so
    nobody can accidentally trigger a data-loss downgrade.
    """

    def test_downgrade_raises_not_implemented_error(self):
        """Calling 0027's downgrade() directly must raise
        NotImplementedError. Argument-less call shape mirrors how
        alembic invokes the function.
        """
        import importlib.util
        path = str(_BACKEND / "alembic" / "versions" / "0027_default_line_items_backfill.py")
        spec = importlib.util.spec_from_file_location("mig_0027", path)
        assert spec is not None and spec.loader is not None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        with pytest.raises(NotImplementedError) as exc:
            mod.downgrade()
        msg = str(exc.value)
        print(f"\nP1.R5 — 0027 downgrade() raised NotImplementedError: {msg!r}")
        assert "user-edited" in msg, (
            "NotImplementedError message must call out that user data "
            "would be destroyed"
        )
        assert "Forward-fix" in msg, (
            "message must point operators at the forward-fix path"
        )

    def test_no_destructive_delete_in_0027_downgrade(self):
        """Source-level guard — the prior `DELETE FROM budget_line_items`
        must NOT be present in the downgrade body. Drift here would
        silently re-introduce the trapdoor.
        """
        path = str(_BACKEND / "alembic" / "versions" / "0027_default_line_items_backfill.py")
        with open(path) as f:
            src = f.read()
        marker = "def downgrade"
        start = src.index(marker)
        # The file ends at downgrade (no later defs), so take to EOF.
        body = src[start:]
        assert "DELETE FROM budget_line_items" not in body, (
            "0027 downgrade must NOT contain `DELETE FROM "
            "budget_line_items` (operator decision P1.R5 Option 1)"
        )
        assert "raise NotImplementedError" in body, (
            "0027 downgrade must raise NotImplementedError"
        )
        print(f"\nP1.R5 — 0027 downgrade body verified clean of "
              f"destructive DELETE; raises NotImplementedError")
