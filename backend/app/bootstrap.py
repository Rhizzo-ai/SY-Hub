"""SY Hub bootstrap orchestrator.

Single source of truth for cold-start sequencing. Runs as ``python -m app.bootstrap``
from /app/backend with .env sourced. Holds a Postgres advisory lock for the
duration to prevent concurrent bootstraps. Fails loud and exits non-zero on any
error.

Sequence
--------
0. Env-var precheck (BOOTSTRAP_ADMIN_EMAIL, BOOTSTRAP_ADMIN_PASSWORD)
1. Wait for Postgres (BOOTSTRAP_PG_TIMEOUT_SECONDS, default 60, max 300)
2. Acquire advisory lock (key=hashtext('sy_hub_bootstrap'))
3. Detect DB state (logs current alembic revision; pure observability)
4. alembic upgrade head
5. seed.seed() — tenant + entities
6. seed_rbac.seed_rbac() — permissions + roles + role_perms + super_admin
7. seed_test_users — runs scripts/seed_test_users.py if present (skipped silently otherwise)
8. Verify invariants
9. Release advisory lock + summary log

When this fails — troubleshooting
---------------------------------
- "BOOTSTRAP_ADMIN_EMAIL not set" / "BOOTSTRAP_ADMIN_PASSWORD not set"
    -> Set both in /app/backend/.env. See seed_rbac._seed_bootstrap_admin
       for why these are required.
- "Could not connect to Postgres after Ns"
    -> Check Postgres is running:  sudo supervisorctl status postgres
       Verify DATABASE_URL in .env. If Postgres is genuinely slow on this
       sandbox, raise BOOTSTRAP_PG_TIMEOUT_SECONDS.
- "Could not acquire advisory lock"
    -> Another bootstrap is in progress, or a previous run died holding the
       lock. Wait a moment and retry, or inspect:
         psql "$DATABASE_URL" -c "SELECT pid, locktype, objid FROM pg_locks
                                   WHERE locktype='advisory';"
- "alembic upgrade failed"
    -> Read the alembic stderr captured in the log line. Likely a migration
       error. Inspect:  alembic current   and   alembic heads.
- "Verify failed: cause=alembic_drift"
    -> alembic current != head. Re-run bootstrap; if it persists, a migration
       is genuinely broken and must be fixed by hand.
- "Verify failed: cause=perm_count_mismatch"
    -> permissions row count != len(PERMISSION_CATALOGUE). Most often a
       permission_action enum value is missing because alembic isn't really
       at head, or PERMISSION_CATALOGUE was changed without re-seeding.
- "Verify failed: cause=role_count_mismatch"
    -> roles row count != len(ROLE_CATALOGUE). seed_rbac partially failed,
       or a role was deleted manually.
- "Verify failed: cause=super_admin_user_missing"
    -> No User row exists for BOOTSTRAP_ADMIN_EMAIL. seed_rbac was skipped
       or BOOTSTRAP_ADMIN_EMAIL was changed without re-seeding.
- "Verify failed: cause=super_admin_role_not_active"
    -> The bootstrap admin user has no Active user_role pointing at the
       super_admin role. The user was manually deactivated, or the
       BOOTSTRAP_ADMIN_EMAIL was changed without re-bootstrapping.
       Re-run bootstrap, or restore via SQL.
- "Verify failed: cause=role_perm_unknown_code"
    -> A code in seed_rbac.ROLE_PERMISSIONS does not resolve to any row in
       the permissions table. Typo in the catalogue, or a permission was
       removed without updating role mappings. Fix the source, re-run.

Exit codes
----------
- 0   ok
- 1   precheck failure (env vars missing)
- 2   postgres unreachable within timeout
- 3   advisory lock unavailable
- 4   alembic upgrade failed
- 5   seed failed (tenant, RBAC, or test-users)
- 6   verify failed
- 7   unexpected error

Sandbox provisioning notes (first-time setup on a fresh Emergent fork)
----------------------------------------------------------------------
The bootstrap orchestrator assumes Postgres is already installed and running.
The first session to set up a fresh sandbox must do this once, by hand:

    # 1. Install PostgreSQL 16 from PGDG (Debian 12 / bookworm).
    sudo install -d /usr/share/postgresql-common/pgdg
    sudo curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \\
         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] \\
          https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \\
         | sudo tee /etc/apt/sources.list.d/pgdg.list
    sudo apt-get update
    sudo apt-get install -y postgresql-16 postgresql-contrib-16 postgresql-client-16

    # 2. Provision the syhomes role + DB matching DATABASE_URL in .env.
    sudo -u postgres psql <<SQL
    CREATE ROLE syhomes WITH LOGIN PASSWORD 'syhomes_dev' CREATEDB;
    CREATE DATABASE syhomes OWNER syhomes;
    \\c syhomes
    CREATE EXTENSION IF NOT EXISTS pgcrypto;
    SQL

    # 3. Wire Postgres into supervisor so it survives pod restart.
    cat > /etc/supervisor/conf.d/supervisord_postgres.conf <<EOF
    [program:postgres]
    command=/usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql/16/main \\
            -c config_file=/etc/postgresql/16/main/postgresql.conf \\
            -c hba_file=/etc/postgresql/16/main/pg_hba.conf \\
            -c ident_file=/etc/postgresql/16/main/pg_ident.conf
    user=postgres
    autostart=true
    autorestart=true
    priority=50
    stopsignal=INT
    stopwaitsecs=30
    stdout_logfile=/var/log/supervisor/postgres.out.log
    stderr_logfile=/var/log/supervisor/postgres.err.log
    EOF
    sudo supervisorctl reread && sudo supervisorctl update

    # 4. From here on, every restart is owned by python -m app.bootstrap.

Quirks observed:
- bookworm's default Postgres is 15; PGDG 16 is preferred for forward-compat.
- pg_hba.conf ships with `host all all 127.0.0.1/32 scram-sha-256`, so the
  syhomes role authenticates over TCP without further pg_hba edits.
- pgcrypto is required for the `gen_random_uuid()` server-default used by
  migrations 0011/0012/0015/0019/0022; CREATE EXTENSION must run before
  alembic upgrade.
- Frontend/backend supervisor blocks already exist on the Emergent template;
  only the postgres block needs to be added.
"""
from __future__ import annotations

import logging
import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Optional
from urllib.parse import urlsplit

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool


# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------

EXIT_OK = 0
EXIT_PRECHECK = 1
EXIT_PG_UNREACHABLE = 2
EXIT_LOCK_UNAVAILABLE = 3
EXIT_ALEMBIC = 4
EXIT_SEED = 5
EXIT_VERIFY = 6
EXIT_UNEXPECTED = 7

LOCK_KEY_TEXT = "sy_hub_bootstrap"

DEFAULT_PG_TIMEOUT_SECONDS = 60
MAX_PG_TIMEOUT_SECONDS = 300

# ----------------------------------------------------------------------
# Logging — every line prefixed [bootstrap] for grep-ability.
# ----------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"


def _setup_logger() -> logging.Logger:
    """Install a dedicated handler on the bootstrap logger.

    alembic's env.py calls ``logging.config.fileConfig(alembic.ini)`` which
    by default disables every pre-existing logger (its
    ``disable_existing_loggers=True`` default). After that call, our INFO
    lines silently vanish.

    Two defences applied here:
    - Own handler + ``propagate=False`` so root-logger reconfiguration
      doesn't strip our destination.
    - ``_revive()`` is called at the top of every step function to undo the
      ``disabled = True`` that fileConfig may have set on us.
    """
    lg = logging.getLogger("app.bootstrap")
    lg.setLevel(logging.INFO)
    lg.propagate = False
    # Replace handlers so re-import inside subprocess tests doesn't double-log.
    for h in list(lg.handlers):
        lg.removeHandler(h)
    h = logging.StreamHandler(sys.stderr)
    h.setLevel(logging.INFO)
    h.setFormatter(logging.Formatter(_LOG_FORMAT))
    lg.addHandler(h)
    return lg


def _revive_logger() -> None:
    """Undo logging.config.fileConfig(disable_existing_loggers=True)."""
    log.disabled = False
    if not log.handlers:
        h = logging.StreamHandler(sys.stderr)
        h.setLevel(logging.INFO)
        h.setFormatter(logging.Formatter(_LOG_FORMAT))
        log.addHandler(h)
    log.setLevel(logging.INFO)


log = _setup_logger()


def _kv(step: str, **fields) -> str:
    """Format a structured-ish k=v log line, prefixed [bootstrap]."""
    parts = [f"step={step}"]
    for k, v in fields.items():
        if v is None:
            continue
        sval = str(v)
        if " " in sval or "=" in sval:
            sval = f'"{sval}"'
        parts.append(f"{k}={sval}")
    return "[bootstrap] " + " ".join(parts)


# ----------------------------------------------------------------------
# Context — passed through the pipeline; no module-global mutation.
# ----------------------------------------------------------------------


@dataclass
class BootstrapContext:
    database_url: str
    pg_timeout_seconds: int
    bootstrap_admin_email: str
    bootstrap_admin_password: str
    timings: dict = field(default_factory=dict)
    lock_engine: Optional[Engine] = None
    lock_conn: object = None  # sqlalchemy Connection
    started_at: float = field(default_factory=time.monotonic)


# ----------------------------------------------------------------------
# Custom exception with a cause key for greppable failure logs.
# ----------------------------------------------------------------------


class BootstrapError(RuntimeError):
    def __init__(self, cause: str, message: str):
        super().__init__(message)
        self.cause = cause
        self.message = message


# ----------------------------------------------------------------------
# Step 0 — env-var precheck
# ----------------------------------------------------------------------


def env_precheck() -> BootstrapContext:
    t0 = time.monotonic()
    email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "").strip()
    password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "")
    db_url = os.environ.get("DATABASE_URL", "").strip()
    timeout_raw = os.environ.get(
        "BOOTSTRAP_PG_TIMEOUT_SECONDS", str(DEFAULT_PG_TIMEOUT_SECONDS)
    )

    missing = []
    if not email:
        missing.append("BOOTSTRAP_ADMIN_EMAIL")
    if not password:
        missing.append("BOOTSTRAP_ADMIN_PASSWORD")
    if not db_url:
        missing.append("DATABASE_URL")
    if missing:
        elapsed = time.monotonic() - t0
        log.error(
            _kv(
                "precheck",
                result="fail",
                cause="env_missing",
                missing=",".join(missing),
                elapsed=f"{elapsed:.2f}s",
            )
        )
        raise BootstrapError(
            "env_missing",
            f"{', '.join(missing)} not set in /app/backend/.env",
        )

    try:
        timeout = int(timeout_raw)
    except ValueError:
        elapsed = time.monotonic() - t0
        log.error(
            _kv(
                "precheck",
                result="fail",
                cause="env_invalid",
                var="BOOTSTRAP_PG_TIMEOUT_SECONDS",
                value=timeout_raw,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        raise BootstrapError(
            "env_invalid",
            f"BOOTSTRAP_PG_TIMEOUT_SECONDS must be an integer, got {timeout_raw!r}",
        )
    if timeout < 1 or timeout > MAX_PG_TIMEOUT_SECONDS:
        elapsed = time.monotonic() - t0
        log.error(
            _kv(
                "precheck",
                result="fail",
                cause="env_invalid",
                var="BOOTSTRAP_PG_TIMEOUT_SECONDS",
                value=timeout_raw,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        raise BootstrapError(
            "env_invalid",
            f"BOOTSTRAP_PG_TIMEOUT_SECONDS out of range [1, {MAX_PG_TIMEOUT_SECONDS}]: {timeout}",
        )

    elapsed = time.monotonic() - t0
    ctx = BootstrapContext(
        database_url=db_url,
        pg_timeout_seconds=timeout,
        bootstrap_admin_email=email,
        bootstrap_admin_password=password,
    )
    ctx.timings["precheck"] = elapsed
    log.info(
        _kv(
            "precheck",
            result="ok",
            timeout=f"{timeout}s",
            elapsed=f"{elapsed:.2f}s",
        )
    )
    return ctx


# ----------------------------------------------------------------------
# Step 1 — wait for Postgres
# ----------------------------------------------------------------------


def wait_for_postgres(ctx: BootstrapContext) -> None:
    t0 = time.monotonic()
    deadline = t0 + ctx.pg_timeout_seconds
    last_err: Optional[Exception] = None
    last_progress_log = t0
    attempt = 0

    # Use a NullPool engine so each connect() opens a fresh socket; we never
    # want a stale pooled connection here.
    eng = create_engine(ctx.database_url, poolclass=NullPool, future=True)
    try:
        while time.monotonic() < deadline:
            attempt += 1
            try:
                with eng.connect() as c:
                    c.execute(text("SELECT 1"))
                elapsed = time.monotonic() - t0
                ctx.timings["wait_for_postgres"] = elapsed
                log.info(
                    _kv(
                        "wait_for_postgres",
                        result="ok",
                        attempts=attempt,
                        elapsed=f"{elapsed:.2f}s",
                    )
                )
                return
            except (OperationalError, OSError, socket.error) as e:
                last_err = e
                now = time.monotonic()
                if now - last_progress_log >= 5:
                    log.info(
                        _kv(
                            "wait_for_postgres",
                            result="waiting",
                            attempts=attempt,
                            elapsed=f"{now - t0:.1f}s",
                            timeout=f"{ctx.pg_timeout_seconds}s",
                        )
                    )
                    last_progress_log = now
                time.sleep(1.0)
    finally:
        eng.dispose()

    elapsed = time.monotonic() - t0
    ctx.timings["wait_for_postgres"] = elapsed
    log.error(
        _kv(
            "wait_for_postgres",
            result="fail",
            cause="pg_unreachable",
            attempts=attempt,
            elapsed=f"{elapsed:.2f}s",
            last_error=type(last_err).__name__ if last_err else "unknown",
        )
    )
    raise BootstrapError(
        "pg_unreachable",
        f"Could not connect to Postgres after {ctx.pg_timeout_seconds}s "
        f"({attempt} attempts; last error: {last_err})",
    )


# ----------------------------------------------------------------------
# Step 2 — advisory lock (held until Step 9)
# ----------------------------------------------------------------------


def acquire_advisory_lock(ctx: BootstrapContext) -> None:
    """Acquire a session-scoped Postgres advisory lock.

    Uses a NullPool engine + dedicated connection so the lock can NOT leak
    back into a shared pool — the same physical connection that takes the
    lock is the one that releases it (or the connection close releases it).
    """
    t0 = time.monotonic()
    eng = create_engine(
        ctx.database_url,
        poolclass=NullPool,
        isolation_level="AUTOCOMMIT",
        future=True,
    )
    conn = eng.connect()
    try:
        got = conn.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:k))"),
            {"k": LOCK_KEY_TEXT},
        ).scalar()
    except Exception:
        conn.close()
        eng.dispose()
        raise
    elapsed = time.monotonic() - t0
    if not got:
        conn.close()
        eng.dispose()
        ctx.timings["acquire_lock"] = elapsed
        log.error(
            _kv(
                "acquire_lock",
                result="fail",
                cause="lock_unavailable",
                key=LOCK_KEY_TEXT,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        raise BootstrapError(
            "lock_unavailable",
            "Could not acquire advisory lock — another bootstrap is in "
            "progress (or a previous run died holding the lock).",
        )
    ctx.lock_engine = eng
    ctx.lock_conn = conn
    ctx.timings["acquire_lock"] = elapsed
    log.info(
        _kv(
            "acquire_lock",
            result="ok",
            key=LOCK_KEY_TEXT,
            elapsed=f"{elapsed:.2f}s",
        )
    )


def release_advisory_lock(ctx: BootstrapContext) -> None:
    if ctx.lock_conn is None:
        return
    t0 = time.monotonic()
    try:
        try:
            ctx.lock_conn.execute(
                text("SELECT pg_advisory_unlock(hashtext(:k))"),
                {"k": LOCK_KEY_TEXT},
            )
        except Exception as e:
            log.warning(
                _kv(
                    "release_lock",
                    result="warn",
                    cause="unlock_failed",
                    error=type(e).__name__,
                )
            )
        ctx.lock_conn.close()
    finally:
        if ctx.lock_engine is not None:
            ctx.lock_engine.dispose()
        ctx.lock_conn = None
        ctx.lock_engine = None
    elapsed = time.monotonic() - t0
    ctx.timings["release_lock"] = elapsed
    log.info(_kv("release_lock", result="ok", elapsed=f"{elapsed:.2f}s"))


# ----------------------------------------------------------------------
# Step 3 — detect DB state (pure observability)
# ----------------------------------------------------------------------


def detect_db_state(ctx: BootstrapContext) -> str:
    """Return alembic current revision (or 'unstamped' if alembic_version
    table is missing). Pure logging — does not branch behaviour.
    """
    t0 = time.monotonic()
    eng = create_engine(ctx.database_url, poolclass=NullPool, future=True)
    try:
        with eng.connect() as c:
            exists = c.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
                    "WHERE table_name = 'alembic_version')"
                )
            ).scalar()
            if not exists:
                current = "unstamped"
            else:
                row = c.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                ).scalar()
                current = row or "unstamped"

        head = _alembic_heads()
    finally:
        eng.dispose()

    elapsed = time.monotonic() - t0
    ctx.timings["detect_state"] = elapsed
    log.info(
        _kv(
            "detect_state",
            result="ok",
            current=current,
            head=head,
            elapsed=f"{elapsed:.2f}s",
        )
    )
    return current


def _alembic_heads() -> str:
    """Return the alembic head revision id by inspecting the script directory.
    Version-agnostic — does NOT hardcode a revision string.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(_alembic_ini_path())
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()
    if len(heads) == 1:
        return heads[0]
    if len(heads) == 0:
        return "<no-heads>"
    return ",".join(heads)


def _alembic_ini_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "alembic.ini"))


# ----------------------------------------------------------------------
# Step 4 — alembic upgrade head
# ----------------------------------------------------------------------


def alembic_upgrade(ctx: BootstrapContext, target: str, label: str) -> None:
    """Run ``alembic upgrade <target>``. ``target`` is a rev id or 'head'.

    Used twice during a cold start (see ``run_migrations_and_seeds``):
    once to land at the pre-seed boundary (so the tenant + RBAC seeds
    can run while the migration chain's mid-stream data dependency
    still needs satisfying), then again to advance the rest of the way
    to head. On a green DB, both calls are no-ops.
    """
    t0 = time.monotonic()
    from alembic import command
    from alembic.config import Config

    cfg = Config(_alembic_ini_path())
    cfg.set_main_option("sqlalchemy.url", ctx.database_url)
    try:
        command.upgrade(cfg, target)
    except Exception as e:
        _revive_logger()
        elapsed = time.monotonic() - t0
        ctx.timings[label] = elapsed
        log.error(
            _kv(
                label,
                result="fail",
                cause="alembic_failed",
                target=target,
                error=type(e).__name__,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        log.error("[bootstrap] alembic stderr: %r", e)
        raise BootstrapError(
            "alembic_failed",
            f"alembic upgrade {target} failed: {e}",
        ) from e
    _revive_logger()
    elapsed = time.monotonic() - t0
    ctx.timings[label] = elapsed
    log.info(_kv(label, result="ok", target=target, elapsed=f"{elapsed:.2f}s"))


def _enum_values(database_url: str, enum_name: str) -> set:
    """Return the current set of values for a Postgres enum type (or empty set
    if the type does not yet exist)."""
    eng = create_engine(database_url, poolclass=NullPool, future=True)
    try:
        with eng.connect() as c:
            return {
                r[0] for r in c.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_type t "
                        "JOIN pg_enum e ON e.enumtypid = t.oid "
                        "WHERE t.typname = :n"
                    ),
                    {"n": enum_name},
                ).all()
            }
    finally:
        eng.dispose()


def seed_rbac_filtered_to_enum(ctx: BootstrapContext) -> None:
    """Run ``seed_rbac`` with PERMISSION_CATALOGUE filtered to actions that
    currently exist in the ``permission_action`` enum.

    The full PERMISSION_CATALOGUE references the post-0020 enum values
    (``submit``, ``view_financials``); on a cold start those don't exist
    until alembic 0020 has run. We must therefore seed RBAC twice during
    a cold start: once at the pre-seed boundary with the catalogue
    filtered to the values that exist (so 0018's data step finds
    tenants + users + RBAC), and a second time at head with the full
    catalogue (idempotent — adds the two new permissions).

    On a fully-migrated DB this filter is the identity (every action in
    the catalogue exists in the enum) and the call collapses into a
    normal idempotent reseed.
    """
    t0 = time.monotonic()
    valid_actions = _enum_values(ctx.database_url, "permission_action")
    valid_resources = _enum_values(ctx.database_url, "permission_resource")

    import app.seed_rbac as rbac
    original = list(rbac.PERMISSION_CATALOGUE)
    if valid_actions:
        # Filter on BOTH action and resource — any new permission resource
        # introduced in a post-0017 migration (e.g. Chat 24's `suppliers`
        # and `pos`) must also be filtered until that migration runs.
        # Tuple layout: (code, resource, action, description, is_sensitive).
        filtered = [
            p for p in original
            if p[2] in valid_actions
            and (not valid_resources or p[1] in valid_resources)
        ]
    else:
        # permission_action enum doesn't exist yet (DB pre-0002). seed_rbac
        # cannot run at all; the orchestrator only invokes this AFTER
        # alembic_upgrade(PRE_SEED_REV) so this branch should never trigger.
        filtered = original
    rbac.PERMISSION_CATALOGUE = filtered
    try:
        try:
            rbac.seed_rbac()
        except Exception as e:
            _revive_logger()
            elapsed = time.monotonic() - t0
            ctx.timings["seed_rbac_pre"] = elapsed
            log.error(
                _kv(
                    "seed_rbac_pre",
                    result="fail",
                    cause="seed_failed",
                    error=type(e).__name__,
                    elapsed=f"{elapsed:.2f}s",
                )
            )
            log.exception("[bootstrap] seed_rbac (pre) raised")
            raise BootstrapError(
                "seed_failed", f"seed_rbac (pre) failed: {e}"
            ) from e
    finally:
        rbac.PERMISSION_CATALOGUE = original
    _revive_logger()
    elapsed = time.monotonic() - t0
    ctx.timings["seed_rbac_pre"] = elapsed
    log.info(
        _kv(
            "seed_rbac_pre",
            result="ok",
            permissions_seeded=len(filtered),
            full_catalogue=len(original),
            elapsed=f"{elapsed:.2f}s",
        )
    )


def run_migrations_and_seeds(ctx: BootstrapContext) -> None:
    """Drive the staged migration + seed dance.

    Why staged?
    -----------
    Migration 0018 (sdlt_appraisal_defaults) has a data step that requires
    rows in the ``tenants`` table; on a cold start the tenant seed has
    not yet run. Migration 0020 adds the ``submit`` and ``view_financials``
    values to the ``permission_action`` enum that the full
    PERMISSION_CATALOGUE references.

    The dance:
    1. alembic upgrade 0017_audit_remediation_patch_3 (just before the
       data dependency)
    2. seed.seed() — creates the tenant + entities expected by 0018
    3. seed_rbac with PERMISSION_CATALOGUE filtered to existing enum
       actions — creates permissions, roles, role_permissions, and the
       super_admin user
    4. alembic upgrade head — runs 0018 data step (now finds tenants),
       0019, 0020 (adds enum values), 0021, 0022
    5. seed_rbac with the full catalogue — idempotent top-up that adds
       the two post-0020 permissions

    On a green DB at head, alembic upgrade is a no-op both times and the
    seed calls are idempotent. The orchestrator runs the full dance
    every time so cold-start and snapshot-restore paths share one code
    path; idempotence is asserted by tests/test_bootstrap.py.
    """
    PRE_SEED_REV = "0017_audit_remediation_patch_3"
    alembic_upgrade(ctx, PRE_SEED_REV, label="alembic_pre_seed")
    seed_tenant_and_entities(ctx)
    seed_rbac_filtered_to_enum(ctx)
    alembic_upgrade(ctx, "head", label="alembic_head")
    seed_rbac(ctx)


# ----------------------------------------------------------------------
# Step 5/6/7 — seeds
# ----------------------------------------------------------------------


def seed_tenant_and_entities(ctx: BootstrapContext) -> None:
    t0 = time.monotonic()
    try:
        from app.seed import seed
        seed()
    except Exception as e:
        elapsed = time.monotonic() - t0
        ctx.timings["seed_tenant"] = elapsed
        log.error(
            _kv(
                "seed_tenant",
                result="fail",
                cause="seed_failed",
                error=type(e).__name__,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        log.exception("[bootstrap] seed.seed() raised")
        raise BootstrapError("seed_failed", f"seed.seed() failed: {e}") from e
    elapsed = time.monotonic() - t0
    ctx.timings["seed_tenant"] = elapsed
    log.info(_kv("seed_tenant", result="ok", elapsed=f"{elapsed:.2f}s"))


def seed_rbac(ctx: BootstrapContext) -> None:
    t0 = time.monotonic()
    try:
        from app.seed_rbac import seed_rbac as _seed_rbac
        _seed_rbac()
    except Exception as e:
        elapsed = time.monotonic() - t0
        ctx.timings["seed_rbac"] = elapsed
        log.error(
            _kv(
                "seed_rbac",
                result="fail",
                cause="seed_failed",
                error=type(e).__name__,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        log.exception("[bootstrap] seed_rbac() raised")
        raise BootstrapError("seed_failed", f"seed_rbac() failed: {e}") from e
    elapsed = time.monotonic() - t0
    ctx.timings["seed_rbac"] = elapsed
    log.info(_kv("seed_rbac", result="ok", elapsed=f"{elapsed:.2f}s"))


def seed_system_config_step(ctx: BootstrapContext) -> None:
    """Run the system_config seeds (39 platform-wide config keys + role
    grants for the system_config.* permissions).

    These were previously run only inside the FastAPI lifespan startup;
    folding them into bootstrap means a cold-started DB is fully usable
    by server.py without depending on lifespan to back-fill data. The
    seeds are imported from ``app.seed_system_config`` (idempotent —
    they UPSERT each row).
    """
    t0 = time.monotonic()
    try:
        from app.seed_system_config import (
            seed_system_config,
            seed_system_config_role_grants,
        )
        seed_system_config_role_grants()
        seed_system_config()
    except Exception as e:
        elapsed = time.monotonic() - t0
        ctx.timings["seed_system_config"] = elapsed
        log.error(
            _kv(
                "seed_system_config",
                result="fail",
                cause="seed_failed",
                error=type(e).__name__,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        log.exception("[bootstrap] seed_system_config raised")
        raise BootstrapError(
            "seed_failed", f"seed_system_config failed: {e}"
        ) from e
    elapsed = time.monotonic() - t0
    ctx.timings["seed_system_config"] = elapsed
    log.info(
        _kv("seed_system_config", result="ok", elapsed=f"{elapsed:.2f}s")
    )


def seed_test_users(ctx: BootstrapContext) -> None:
    t0 = time.monotonic()
    here = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.normpath(
        os.path.join(here, "..", "scripts", "seed_test_users.py")
    )
    if not os.path.exists(script_path):
        elapsed = time.monotonic() - t0
        ctx.timings["seed_test_users"] = elapsed
        log.info(
            _kv(
                "seed_test_users",
                result="skip",
                reason="script_not_found",
                path=script_path,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        return
    try:
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.dirname(script_path) + "/..",
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"seed_test_users.py exited {result.returncode}: "
                f"stderr={result.stderr.strip()[:500]}"
            )
    except Exception as e:
        elapsed = time.monotonic() - t0
        ctx.timings["seed_test_users"] = elapsed
        log.error(
            _kv(
                "seed_test_users",
                result="fail",
                cause="seed_failed",
                error=type(e).__name__,
                elapsed=f"{elapsed:.2f}s",
            )
        )
        raise BootstrapError(
            "seed_failed", f"seed_test_users failed: {e}"
        ) from e
    elapsed = time.monotonic() - t0
    ctx.timings["seed_test_users"] = elapsed
    log.info(
        _kv("seed_test_users", result="ok", elapsed=f"{elapsed:.2f}s")
    )


# ----------------------------------------------------------------------
# Step 8 — verify invariants
# ----------------------------------------------------------------------


def verify_invariants(ctx: BootstrapContext) -> dict:
    """Verify the DB is in the expected post-bootstrap shape.

    Raises BootstrapError on the first failure; otherwise returns a dict of
    summary counts for the final log line.
    """
    t0 = time.monotonic()

    # Import lazily so module imports are cheap in failure paths.
    from app.seed_rbac import (
        PERMISSION_CATALOGUE,
        ROLE_CATALOGUE,
        ROLE_PERMISSIONS,
    )

    eng = create_engine(ctx.database_url, poolclass=NullPool, future=True)
    summary: dict = {}
    try:
        with eng.connect() as c:
            # 1. alembic current == head
            current = c.execute(
                text("SELECT version_num FROM alembic_version LIMIT 1")
            ).scalar()
            head = _alembic_heads()
            if current != head:
                _verify_fail(
                    ctx, t0, "alembic_drift",
                    f"alembic current {current!r} != head {head!r}",
                )
            summary["alembic"] = current
            log.info(_kv("verify.alembic", result="ok", current=current, head=head))

            # 2. permissions count
            perms_actual = c.execute(
                text("SELECT count(*) FROM permissions")
            ).scalar() or 0
            perms_expected = len(PERMISSION_CATALOGUE)
            if perms_actual != perms_expected:
                _verify_fail(
                    ctx, t0, "perm_count_mismatch",
                    f"expected {perms_expected} permissions, found {perms_actual}",
                )
            summary["perms"] = perms_actual
            log.info(
                _kv(
                    "verify.perms",
                    result="ok",
                    expected=perms_expected,
                    actual=perms_actual,
                )
            )

            # 3. roles count
            roles_actual = c.execute(
                text("SELECT count(*) FROM roles")
            ).scalar() or 0
            roles_expected = len(ROLE_CATALOGUE)
            if roles_actual != roles_expected:
                _verify_fail(
                    ctx, t0, "role_count_mismatch",
                    f"expected {roles_expected} roles, found {roles_actual}",
                )
            summary["roles"] = roles_actual
            log.info(
                _kv(
                    "verify.roles",
                    result="ok",
                    expected=roles_expected,
                    actual=roles_actual,
                )
            )

            # 4. super_admin user exists for BOOTSTRAP_ADMIN_EMAIL
            admin_email = ctx.bootstrap_admin_email.strip().lower()
            user_id = c.execute(
                text("SELECT id FROM users WHERE lower(email) = :e LIMIT 1"),
                {"e": admin_email},
            ).scalar()
            if user_id is None:
                _verify_fail(
                    ctx, t0, "super_admin_user_missing",
                    f"no User row for BOOTSTRAP_ADMIN_EMAIL={admin_email}",
                )
            summary["super_admin"] = admin_email
            log.info(
                _kv(
                    "verify.super_admin_user",
                    result="ok",
                    email=admin_email,
                )
            )

            # 5. Active super_admin user_role
            sa_role_id = c.execute(
                text("SELECT id FROM roles WHERE code = 'super_admin' LIMIT 1")
            ).scalar()
            if sa_role_id is None:
                _verify_fail(
                    ctx, t0, "super_admin_role_missing",
                    "no Role row with code='super_admin'",
                )
            ur_status = c.execute(
                text(
                    "SELECT status FROM user_roles "
                    "WHERE user_id = :u AND role_id = :r"
                ),
                {"u": user_id, "r": sa_role_id},
            ).scalar()
            if ur_status != "Active":
                _verify_fail(
                    ctx, t0, "super_admin_role_not_active",
                    f"user_role status for {admin_email} is {ur_status!r} "
                    "(expected 'Active')",
                )
            log.info(_kv("verify.super_admin_role", result="ok", status=ur_status))

            # 6. Every code in ROLE_PERMISSIONS resolves to a permissions row
            referenced = set()
            for codes in ROLE_PERMISSIONS.values():
                referenced.update(codes)
            if referenced:
                rows = c.execute(
                    text("SELECT code FROM permissions WHERE code = ANY(:codes)"),
                    {"codes": list(referenced)},
                ).all()
                resolved = {r[0] for r in rows}
                missing = sorted(referenced - resolved)
                if missing:
                    _verify_fail(
                        ctx, t0, "role_perm_unknown_code",
                        "ROLE_PERMISSIONS references unknown permission "
                        f"code(s): {missing}",
                    )
            log.info(
                _kv(
                    "verify.role_perm_codes",
                    result="ok",
                    referenced=len(referenced),
                )
            )
    finally:
        eng.dispose()

    elapsed = time.monotonic() - t0
    ctx.timings["verify"] = elapsed
    log.info(_kv("verify", result="ok", elapsed=f"{elapsed:.2f}s"))
    return summary


def _verify_fail(ctx: BootstrapContext, t0: float, cause: str, detail: str) -> None:
    elapsed = time.monotonic() - t0
    ctx.timings["verify"] = elapsed
    log.error(
        _kv(
            "verify",
            result="fail",
            cause=cause,
            detail=detail,
            elapsed=f"{elapsed:.2f}s",
        )
    )
    raise BootstrapError(cause, f"Verify failed: {detail}")


# ----------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------


def main() -> int:
    """Run the full bootstrap pipeline. Returns an int exit code.

    Never raises — all known failures are mapped to exit codes; unknown
    failures map to EXIT_UNEXPECTED.
    """
    overall_t0 = time.monotonic()
    ctx: Optional[BootstrapContext] = None
    try:
        ctx = env_precheck()
        wait_for_postgres(ctx)
        acquire_advisory_lock(ctx)
        try:
            detect_db_state(ctx)
            run_migrations_and_seeds(ctx)
            seed_system_config_step(ctx)
            seed_test_users(ctx)
            summary = verify_invariants(ctx)
        finally:
            release_advisory_lock(ctx)
        total = time.monotonic() - overall_t0
        # Final summary line — single, greppable, includes per-step timings.
        timing_str = " ".join(
            f"{k}={v:.2f}s" for k, v in ctx.timings.items()
        )
        log.info(
            "[bootstrap] OK alembic=%s perms=%s roles=%s super_admin=%s "
            "total_elapsed=%.2fs %s",
            summary.get("alembic"),
            summary.get("perms"),
            summary.get("roles"),
            summary.get("super_admin"),
            total,
            timing_str,
        )
        return EXIT_OK

    except BootstrapError as e:
        if ctx is not None:
            release_advisory_lock(ctx)
        return _exit_for_cause(e.cause)
    except SystemExit as e:
        if ctx is not None:
            release_advisory_lock(ctx)
        return int(e.code) if isinstance(e.code, int) else EXIT_UNEXPECTED
    except Exception as e:
        if ctx is not None:
            release_advisory_lock(ctx)
        log.exception(
            "[bootstrap] step=main result=fail cause=unexpected error=%s",
            type(e).__name__,
        )
        return EXIT_UNEXPECTED


def _exit_for_cause(cause: str) -> int:
    if cause in ("env_missing", "env_invalid"):
        return EXIT_PRECHECK
    if cause == "pg_unreachable":
        return EXIT_PG_UNREACHABLE
    if cause == "lock_unavailable":
        return EXIT_LOCK_UNAVAILABLE
    if cause == "alembic_failed":
        return EXIT_ALEMBIC
    if cause == "seed_failed":
        return EXIT_SEED
    return EXIT_VERIFY


if __name__ == "__main__":
    sys.exit(main())
