"""Tests for the SY Hub bootstrap orchestrator (app.bootstrap).

Covered failure modes (exit-code mapping is the contract):
- 1 precheck            (BOOTSTRAP_ADMIN_EMAIL/PASSWORD missing)
- 2 pg_unreachable      (DATABASE_URL points at a closed port; short timeout)
- 3 lock_unavailable    (another connection already holds the advisory lock)
- 4 alembic             (covered indirectly — alembic raises on bad URL)
- 6 verify              (each invariant exercised in isolation)

Also verifies:
- detect_db_state on an unstamped fresh DB returns "unstamped"
- detect_db_state on the live DB returns the head revision
- _alembic_heads() helper returns the single head from script directory
- end-to-end cold-start against an ephemeral DB returns exit 0
- idempotence: a second run on a green DB is a no-op exit 0

Tests that need a destructive starting state (cold-start, unstamped) use a
session-scoped ephemeral Postgres database (``syhomes_bootstrap_test``)
created via the syhomes role. The live syhomes DB (used by the rest of
the test suite) is never mutated destructively; only monkeypatches and
session-scoped catalogue overrides exercise the failure paths.

Convention: tests do NOT touch /app/backend/.env or restart any service.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app import bootstrap as B


# Resolves to backend/ regardless of mount point — CI runners use a different prefix than the sandbox.
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
PYTHON_BIN = sys.executable

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _live_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set in test env")
    return url


def _admin_url(live_url: str) -> str:
    """Strip the database name and replace with 'postgres' for CREATE/DROP."""
    base, _ = live_url.rsplit("/", 1)
    return f"{base}/postgres"


def _ephemeral_url(live_url: str, dbname: str) -> str:
    base, _ = live_url.rsplit("/", 1)
    return f"{base}/{dbname}"


def _drop_create_db(admin_url: str, dbname: str) -> None:
    eng = create_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            # Disconnect any sessions on the test DB before dropping.
            c.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": dbname},
            )
            c.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
            c.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        eng.dispose()


def _drop_db(admin_url: str, dbname: str) -> None:
    eng = create_engine(admin_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": dbname},
            )
            c.execute(text(f'DROP DATABASE IF EXISTS "{dbname}"'))
    finally:
        eng.dispose()


def _run_bootstrap_subprocess(env_overrides: dict, timeout: int = 60) -> subprocess.CompletedProcess:
    """Invoke python -m app.bootstrap with a custom env. Captures stdout+stderr."""
    env = os.environ.copy()
    for k, v in env_overrides.items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = v
    return subprocess.run(
        [PYTHON_BIN, "-m", "app.bootstrap"],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _make_live_ctx() -> B.BootstrapContext:
    """Construct a BootstrapContext bound to the live DB without running precheck."""
    return B.BootstrapContext(
        database_url=os.environ["DATABASE_URL"],
        pg_timeout_seconds=10,
        bootstrap_admin_email=os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "rhys@syhomes.co.uk"),
        bootstrap_admin_password=os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "x"),
    )


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture(scope="session")
def ephemeral_db() -> Iterator[str]:
    """Create a throwaway 'syhomes_bootstrap_test' DB, yield its URL, drop on teardown."""
    live = _live_database_url()
    admin = _admin_url(live)
    name = "syhomes_bootstrap_test"
    _drop_create_db(admin, name)
    test_url = _ephemeral_url(live, name)
    # pgcrypto is required for gen_random_uuid() defaults in migrations.
    eng = create_engine(test_url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    finally:
        eng.dispose()
    yield test_url
    _drop_db(admin, name)


# ----------------------------------------------------------------------
# Precheck tests (exit 1)
# ----------------------------------------------------------------------


def test_env_precheck_missing_email():
    r = _run_bootstrap_subprocess({"BOOTSTRAP_ADMIN_EMAIL": ""}, timeout=15)
    assert r.returncode == 1, r.stderr
    assert "BOOTSTRAP_ADMIN_EMAIL" in r.stderr
    assert "result=fail" in r.stderr
    assert "cause=env_missing" in r.stderr


def test_env_precheck_missing_password():
    r = _run_bootstrap_subprocess({"BOOTSTRAP_ADMIN_PASSWORD": ""}, timeout=15)
    assert r.returncode == 1, r.stderr
    assert "BOOTSTRAP_ADMIN_PASSWORD" in r.stderr
    assert "cause=env_missing" in r.stderr


# ----------------------------------------------------------------------
# wait_for_postgres timeout (exit 2)
# ----------------------------------------------------------------------


def test_wait_for_postgres_timeout():
    # Port 1 is reserved and reliably refuses TCP — fastest way to force an
    # OperationalError loop.
    bad = "postgresql+psycopg://syhomes:syhomes_dev@127.0.0.1:1/syhomes"
    r = _run_bootstrap_subprocess(
        {"DATABASE_URL": bad, "BOOTSTRAP_PG_TIMEOUT_SECONDS": "2"},
        timeout=20,
    )
    assert r.returncode == 2, r.stderr
    assert "cause=pg_unreachable" in r.stderr


# ----------------------------------------------------------------------
# detect_db_state
# ----------------------------------------------------------------------


def test_detect_db_state_at_head():
    ctx = _make_live_ctx()
    current = B.detect_db_state(ctx)
    head = B._alembic_heads()
    assert current == head
    assert current.startswith("0034_") or current == head


def test_detect_db_state_unstamped(ephemeral_db: str):
    ctx = B.BootstrapContext(
        database_url=ephemeral_db,
        pg_timeout_seconds=10,
        bootstrap_admin_email="x@example.test",
        bootstrap_admin_password="x",
    )
    current = B.detect_db_state(ctx)
    assert current == "unstamped"


def test_alembic_heads_helper_returns_single_head():
    head = B._alembic_heads()
    assert head and "," not in head, f"expected single head, got {head!r}"
    # Head sentinel updated by Chat 22 (CI hardening): 0025_ → 0026_.
    # Migration 0026_ai_capture_costs_perm landed in Chat 20.
    # Bumped again by Chat 23 R1.3: 0026_ → 0027_ when the default-line-
    # items backfill migration landed.
    # Bumped again by Chat 23 R1.4: 0027_ → 0028_ when the
    # user_preferences table migration landed.
    # Bumped again by Chat 24 R1/R2/R3 (Prompt 2.5): 0028_ → 0032_
    # when suppliers / prefixes / purchase_orders / po_approvals landed.
    # Bumped again by Chat 24 R4 (Prompt 2.5): 0032_ → 0033_ when
    # purchase_order_receipts landed.
    # Bumped again by Chat 26 R7.0b (Prompt 2.5 Track 2): 0033_ → 0034_
    # when the audit_action 'SendBack' enum value landed (P0.13 resolution).
    # See chat-15-closing §3 — this sentinel is "part of any migration's
    # bookkeeping" and must be bumped whenever the head moves.
    assert head.startswith("0034_"), f"unexpected head id: {head}"


# ----------------------------------------------------------------------
# verify_invariants — happy path
# ----------------------------------------------------------------------


def test_verify_invariants_happy_path():
    ctx = _make_live_ctx()
    summary = B.verify_invariants(ctx)
    assert summary["alembic"] == B._alembic_heads()
    assert summary["roles"] >= 1
    assert summary["perms"] >= 1
    assert summary["super_admin"] == ctx.bootstrap_admin_email.strip().lower()


# ----------------------------------------------------------------------
# verify_invariants — failure paths (no live DB mutation; monkeypatches only)
# ----------------------------------------------------------------------


def test_verify_invariants_missing_super_admin():
    ctx = _make_live_ctx()
    ctx.bootstrap_admin_email = "definitely-not-a-real-user@nowhere.invalid"
    with pytest.raises(B.BootstrapError) as excinfo:
        B.verify_invariants(ctx)
    assert excinfo.value.cause == "super_admin_user_missing"


def test_verify_invariants_perm_count_mismatch(monkeypatch):
    import app.seed_rbac as rbac
    # Append a fake permission to the in-memory catalogue. The DB has
    # exactly len(original) rows; verify_invariants will see expected =
    # len(monkeypatched) > actual and fail.
    fake_extra = ("__test_only.fake_perm", "module-test fake")
    monkeypatch.setattr(
        rbac, "PERMISSION_CATALOGUE", list(rbac.PERMISSION_CATALOGUE) + [fake_extra]
    )
    ctx = _make_live_ctx()
    with pytest.raises(B.BootstrapError) as excinfo:
        B.verify_invariants(ctx)
    assert excinfo.value.cause == "perm_count_mismatch"


def test_verify_invariants_role_count_mismatch(monkeypatch):
    import app.seed_rbac as rbac
    monkeypatch.setattr(
        rbac,
        "ROLE_CATALOGUE",
        list(rbac.ROLE_CATALOGUE) + [("__test_only_role", "test fake role")],
    )
    ctx = _make_live_ctx()
    with pytest.raises(B.BootstrapError) as excinfo:
        B.verify_invariants(ctx)
    assert excinfo.value.cause == "role_count_mismatch"


def test_verify_invariants_role_perm_unknown_code(monkeypatch):
    import app.seed_rbac as rbac
    spiked = {k: set(v) for k, v in rbac.ROLE_PERMISSIONS.items()}
    spiked.setdefault("super_admin", set()).add("__test_only.no_such_perm")
    monkeypatch.setattr(rbac, "ROLE_PERMISSIONS", spiked)
    ctx = _make_live_ctx()
    with pytest.raises(B.BootstrapError) as excinfo:
        B.verify_invariants(ctx)
    assert excinfo.value.cause == "role_perm_unknown_code"


# ----------------------------------------------------------------------
# Advisory lock (exit 3)
# ----------------------------------------------------------------------


def test_concurrent_bootstrap_lock():
    """Hold the advisory lock from this process, then invoke bootstrap.

    The orchestrator must fail-fast with cause=lock_unavailable and exit 3.
    The lock is released by closing this test's connection in the finally
    block so subsequent tests are not affected.
    """
    url = _live_database_url()
    holder_eng = create_engine(url, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    holder = holder_eng.connect()
    try:
        got = holder.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:k))"),
            {"k": B.LOCK_KEY_TEXT},
        ).scalar()
        assert got is True, "test could not pre-acquire the bootstrap lock"

        r = _run_bootstrap_subprocess({}, timeout=30)
        assert r.returncode == 3, r.stderr
        assert "cause=lock_unavailable" in r.stderr
    finally:
        try:
            holder.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"),
                {"k": B.LOCK_KEY_TEXT},
            )
        finally:
            holder.close()
            holder_eng.dispose()


# ----------------------------------------------------------------------
# Idempotence
# ----------------------------------------------------------------------


def test_idempotent_run_on_green_db():
    """A second `python -m app.bootstrap` against an already-green DB must
    return exit 0 and emit a verify result=ok line. Bootstrap is the
    canonical pod-restart entrypoint; idempotence is the whole point.
    """
    r = _run_bootstrap_subprocess({}, timeout=60)
    assert r.returncode == 0, r.stderr
    assert "step=verify result=ok" in r.stderr
    assert "[bootstrap] OK alembic=" in r.stderr


# ----------------------------------------------------------------------
# End-to-end cold start (exit 0 from a truly empty DB)
# ----------------------------------------------------------------------


def test_end_to_end_cold_start(ephemeral_db: str):
    """Drop and re-create the ephemeral DB, then invoke bootstrap pointed
    at it. Must run alembic + every seed + verify and exit 0 in a single
    pass — this is the §R7.4 cold-start scenario, asserted by pytest.
    """
    # The fixture already created+pgcrypto'd the DB. Force re-create here
    # to guarantee a truly empty starting state for THIS test.
    live = _live_database_url()
    admin = _admin_url(live)
    name = ephemeral_db.rsplit("/", 1)[1]
    _drop_create_db(admin, name)
    eng = create_engine(ephemeral_db, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    finally:
        eng.dispose()

    r = _run_bootstrap_subprocess(
        {"DATABASE_URL": ephemeral_db},
        timeout=120,
    )
    assert r.returncode == 0, (
        f"cold-start bootstrap failed:\nstdout={r.stdout}\nstderr={r.stderr}"
    )
    assert "step=verify result=ok" in r.stderr
    assert "[bootstrap] OK alembic=" in r.stderr


# ----------------------------------------------------------------------
# Snapshot-restore simulation (§R7.5 — added by user direction)
# ----------------------------------------------------------------------


def test_snapshot_restore_simulation(ephemeral_db: str):
    """Simulate a snapshot-restore at an intermediate alembic revision.

    Postgres does NOT support ``ALTER TYPE ... DROP VALUE``, so we
    cannot simulate a pre-0020 enum state by downgrading from head.
    Instead we build the ephemeral DB UP to revision 0019 from cold,
    using the same staged dance the orchestrator does internally:
      - alembic upgrade 0017_audit_remediation_patch_3
      - seed.seed()                  (so 0018's data step finds tenants)
      - seed_rbac (filtered)         (catalogue minus 0020 actions)
      - alembic upgrade 0019_appraisals_core   (stop short of 0020)

    At that point the ``permission_action`` enum genuinely lacks
    ``submit`` and ``view_financials``. Running bootstrap then must
    self-heal forward: alembic 0020/0021/0022, full RBAC reseed,
    verify, exit 0. This is the actual production failure mode the
    orchestrator was designed to fix (snapshot taken mid-Track-2,
    restored later).
    """
    live = _live_database_url()
    admin = _admin_url(live)
    name = ephemeral_db.rsplit("/", 1)[1]
    _drop_create_db(admin, name)

    # pgcrypto is required for gen_random_uuid() defaults in 0011/0019.
    eng = create_engine(ephemeral_db, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    try:
        with eng.connect() as c:
            c.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    finally:
        eng.dispose()

    # Stage 1: bring the ephemeral DB up to revision 0019 by hand, using a
    # subprocess so the seeds bind their SessionLocal to the ephemeral
    # DB cleanly (avoiding test-runtime module-cache races).
    setup_script = f'''
import os
os.environ["DATABASE_URL"] = {ephemeral_db!r}
from alembic import command
from alembic.config import Config
cfg = Config("{B._alembic_ini_path()}")
cfg.set_main_option("sqlalchemy.url", {ephemeral_db!r})
command.upgrade(cfg, "0017_audit_remediation_patch_3")

from app.seed import seed
seed()

import app.seed_rbac as rbac
from app.bootstrap import _enum_values
valid_actions = _enum_values({ephemeral_db!r}, "permission_action")
valid_resources = _enum_values({ephemeral_db!r}, "permission_resource")
original = list(rbac.PERMISSION_CATALOGUE)
rbac.PERMISSION_CATALOGUE = [
    p for p in original
    if p[2] in valid_actions and p[1] in valid_resources
]
try:
    rbac.seed_rbac()
finally:
    rbac.PERMISSION_CATALOGUE = original

command.upgrade(cfg, "0019_appraisals_core")
print("setup ok")
'''
    setup_env = os.environ.copy()
    setup_env["DATABASE_URL"] = ephemeral_db
    setup_env["BOOTSTRAP_ADMIN_EMAIL"] = setup_env.get(
        "BOOTSTRAP_ADMIN_EMAIL", "rhys@syhomes.co.uk"
    )
    setup_env["BOOTSTRAP_ADMIN_PASSWORD"] = setup_env.get(
        "BOOTSTRAP_ADMIN_PASSWORD", "x"
    )
    setup_result = subprocess.run(
        [PYTHON_BIN, "-c", setup_script],
        cwd=BACKEND_DIR,
        env=setup_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert setup_result.returncode == 0, (
        f"setup-to-0019 failed:\nstdout={setup_result.stdout}\nstderr={setup_result.stderr}"
    )

    # Sanity check: enum values are NOT yet present at 0019.
    eng = create_engine(ephemeral_db, poolclass=NullPool)
    try:
        with eng.connect() as c:
            actions = set(
                r[0] for r in c.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_type t "
                        "JOIN pg_enum e ON e.enumtypid = t.oid "
                        "WHERE t.typname = 'permission_action'"
                    )
                ).all()
            )
            assert "submit" not in actions, (
                f"setup failed: 'submit' already in enum at 0019: {actions}"
            )
            assert "view_financials" not in actions, (
                f"setup failed: 'view_financials' already in enum: {actions}"
            )
            current = c.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()
            assert current == "0019_appraisals_core", current
    finally:
        eng.dispose()

    # Stage 2: invoke bootstrap. Must self-heal to head + add enum values.
    r = _run_bootstrap_subprocess({"DATABASE_URL": ephemeral_db}, timeout=120)
    assert r.returncode == 0, (
        f"snapshot-restore re-bootstrap failed:\n"
        f"stdout={r.stdout}\nstderr={r.stderr}"
    )
    assert "[bootstrap] OK alembic=" in r.stderr

    # Stage 3: verify enum values now present + alembic at head.
    eng = create_engine(ephemeral_db, poolclass=NullPool)
    try:
        with eng.connect() as c:
            actions = set(
                r[0] for r in c.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_type t "
                        "JOIN pg_enum e ON e.enumtypid = t.oid "
                        "WHERE t.typname = 'permission_action'"
                    )
                ).all()
            )
            assert "submit" in actions, actions
            assert "view_financials" in actions, actions
            current = c.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()
            assert current == B._alembic_heads(), current
    finally:
        eng.dispose()
