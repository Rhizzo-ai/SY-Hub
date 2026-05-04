#!/usr/bin/env bash
# /root/.emergent/on-restart.sh
#
# SY Hub pod-restart orchestrator. Owned by the bootstrap-fix-p0 build pack.
# Runs once per pod boot before the backend serves traffic.
#
# Contract:
#   - Source /app/backend/.env (export every variable).
#   - Activate the project venv (/root/.venv).
#   - Run `python -m app.bootstrap` from /app/backend.
#   - Propagate the bootstrap exit code so supervisor/pod sees a real failure
#     when bootstrap fails (rather than silently starting the backend on a
#     half-initialised DB).
#
# Exit-code mapping is the orchestrator's:
#   0 ok | 1 precheck | 2 pg_unreachable | 3 lock_unavailable
#   4 alembic | 5 seed | 6 verify | 7 unexpected
#
# Concurrent-run safety: the orchestrator holds a Postgres advisory lock,
# so this script may safely be invoked twice in parallel — the second
# invocation will exit 3 (lock_unavailable) without touching the DB.
#
# Logging: everything goes to stderr, prefixed [on-restart], and is
# captured by supervisor / pod log aggregation. Per-step structured lines
# (`[bootstrap] step=...`) come from the orchestrator itself.

set -uo pipefail
# NOTE: deliberately NOT `set -e`: we want to inspect $? after the bootstrap
# call and surface a clear diagnostic line before exiting non-zero.

APP_BACKEND_DIR="/app/backend"
ENV_FILE="${APP_BACKEND_DIR}/.env"
VENV_ACTIVATE="/root/.venv/bin/activate"

log() { printf '%s [on-restart] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }

log "starting"

# 1. Locate the env file. Fail loud if it's missing — the orchestrator can't
#    do its precheck without DATABASE_URL / BOOTSTRAP_ADMIN_*.
if [[ ! -f "${ENV_FILE}" ]]; then
    log "FATAL env file not found: ${ENV_FILE}"
    exit 1
fi

# 2. Export every key=value from .env. Use `set -a` so each `source` line
#    becomes an export. Quoted values are handled by bash's source semantics.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a
log "env sourced from ${ENV_FILE}"

# 3. Activate the venv. The orchestrator imports SQLAlchemy / alembic /
#    psycopg from the venv's site-packages, so this must succeed.
if [[ ! -f "${VENV_ACTIVATE}" ]]; then
    log "FATAL venv activate script not found: ${VENV_ACTIVATE}"
    exit 1
fi
# shellcheck disable=SC1090
source "${VENV_ACTIVATE}"
log "venv activated: $(python -c 'import sys; print(sys.executable)')"

# 4. Change into the backend dir so relative paths inside the orchestrator
#    (alembic.ini, scripts/seed_test_users.py) resolve.
cd "${APP_BACKEND_DIR}" || { log "FATAL cd ${APP_BACKEND_DIR} failed"; exit 1; }

# 5. Run the bootstrap orchestrator. All step output streams through to
#    stderr already — we add a marker on either side for log slicing.
log "invoking python -m app.bootstrap"
python -m app.bootstrap
rc=$?

# 6. Diagnose + propagate. The orchestrator already logged the cause on
#    failure; we just translate the exit code to a human-readable line so
#    log skim is fast.
case "${rc}" in
    0)  log "bootstrap ok (rc=0)" ;;
    1)  log "bootstrap FAIL precheck (rc=1) — fix BOOTSTRAP_ADMIN_* / DATABASE_URL in .env" ;;
    2)  log "bootstrap FAIL pg_unreachable (rc=2) — sudo supervisorctl status postgres" ;;
    3)  log "bootstrap FAIL lock_unavailable (rc=3) — another bootstrap in progress" ;;
    4)  log "bootstrap FAIL alembic (rc=4) — migration error; check stderr above" ;;
    5)  log "bootstrap FAIL seed (rc=5) — seed.seed/seed_rbac/seed_test_users; check stderr" ;;
    6)  log "bootstrap FAIL verify (rc=6) — invariant violated; cause= line above" ;;
    7)  log "bootstrap FAIL unexpected (rc=7) — see traceback above" ;;
    *)  log "bootstrap FAIL unknown rc=${rc}" ;;
esac

exit "${rc}"
