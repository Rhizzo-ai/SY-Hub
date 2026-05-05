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
SUPERVISOR_CONF="/etc/supervisor/conf.d/supervisord.conf"
BACKEND_TEMPLATE="/app/scripts/supervisord_backend.conf.template"

log() { printf '%s [on-restart] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*" >&2; }

# 0. Self-heal supervisor wiring. The bootstrap-fix-p0 contract requires
#    [program:backend] to have `autostart=false autorestart=false`. On a
#    fresh container rebuild the supervisor config may be reset to the
#    Emergent template defaults (autostart=true), so we re-apply the
#    canonical block from /app/scripts/supervisord_backend.conf.template
#    every time — but idempotently: if the live config already has
#    autostart=false inside [program:backend], we skip the rewrite.
#
#    The template intentionally omits `environment=` because that line is
#    pod-specific (APP_URL holds this preview's URL). The Python helper
#    below preserves any existing `environment=` line from the live block
#    when splicing the template in, so platform-injected envs survive.
ensure_backend_gated() {
    if [[ ! -f "${SUPERVISOR_CONF}" ]]; then
        log "WARN supervisor conf not found at ${SUPERVISOR_CONF}; skipping self-heal"
        return 0
    fi
    if [[ ! -f "${BACKEND_TEMPLATE}" ]]; then
        log "FATAL backend template missing at ${BACKEND_TEMPLATE}"
        exit 1
    fi

    # Idempotence check: is the live [program:backend] block already gated?
    # We look for `autostart=false` between `[program:backend]` and the
    # next `[program:` (or EOF).
    if awk '
        /^\[program:backend\]/ { in_block=1; next }
        in_block && /^\[program:/ { exit }
        in_block && /^autostart=false[[:space:]]*$/ { found=1 }
        END { exit (found ? 0 : 1) }
    ' "${SUPERVISOR_CONF}"; then
        log "supervisor config already gated (autostart=false on [program:backend])"
        return 0
    fi

    log "supervisor config NOT gated; applying template ${BACKEND_TEMPLATE}"

    # Splice template into supervisor conf, preserving any existing
    # `environment=` line from the [program:backend] block.
    local tmpfile
    tmpfile="$(mktemp)"
    if ! sudo python3 - "${SUPERVISOR_CONF}" "${BACKEND_TEMPLATE}" "${tmpfile}" <<'PY'
import sys, pathlib

conf_path, template_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
conf = pathlib.Path(conf_path).read_text()
template = pathlib.Path(template_path).read_text().rstrip("\n") + "\n"

lines = conf.splitlines(keepends=True)
out, i, n = [], 0, len(lines)
preserved_env = None

while i < n:
    line = lines[i]
    if line.strip() == "[program:backend]":
        # Capture existing environment= line (if any) inside this block.
        j = i + 1
        while j < n and not lines[j].lstrip().startswith("[program:"):
            stripped = lines[j].lstrip()
            if stripped.startswith("environment="):
                preserved_env = lines[j]
            j += 1
        # Build the replacement block: template, plus preserved env line
        # spliced in just before stderr_logfile= so it lands in the same
        # spot the platform expects.
        block_lines = template.splitlines(keepends=True)
        if preserved_env is not None:
            spliced = []
            inserted = False
            for bl in block_lines:
                if not inserted and bl.startswith("stderr_logfile="):
                    spliced.append(preserved_env)
                    inserted = True
                spliced.append(bl)
            if not inserted:
                spliced.append(preserved_env)
            block_lines = spliced
        out.extend(block_lines)
        # Ensure exactly one blank line between this block and the next
        # section (or EOF).
        if j < n:
            out.append("\n")
        i = j
        continue
    out.append(line)
    i += 1

pathlib.Path(out_path).write_text("".join(out))
PY
    then
        log "FATAL python splice helper failed"
        rm -f "${tmpfile}"
        exit 1
    fi

    if ! sudo install -m 0644 "${tmpfile}" "${SUPERVISOR_CONF}"; then
        log "FATAL failed to install rewritten supervisor conf"
        rm -f "${tmpfile}"
        exit 1
    fi
    rm -f "${tmpfile}"

    if ! sudo supervisorctl reread >&2; then
        log "WARN supervisorctl reread failed"
    fi
    if ! sudo supervisorctl update >&2; then
        log "WARN supervisorctl update failed"
    fi

    log "supervisor config gated (template applied; backend is now autostart=false autorestart=false)"
}

log "starting"
ensure_backend_gated

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
#    log skim is fast. On rc=0 we explicitly start the backend program in
#    supervisor — supervisord.conf has `autostart=false autorestart=false`
#    on [program:backend], so the backend cannot serve traffic unless this
#    block runs to completion.
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

# 7. Gate supervisor: only flip [program:backend] to RUNNING when bootstrap
#    succeeded. On any non-zero rc the backend stays STOPPED so it cannot
#    serve requests against a half-initialised DB. We do NOT stop the
#    backend on failure — supervisord.conf already has autostart=false, and
#    if a previous good boot left it running we want operators to see the
#    drift via `supervisorctl status` rather than have it silently killed.
if [[ "${rc}" -eq 0 ]]; then
    log "starting backend via supervisorctl"
    if sudo supervisorctl start backend >&2; then
        log "backend start requested ok"
    else
        sup_rc=$?
        log "FATAL supervisorctl start backend failed (rc=${sup_rc})"
        exit "${sup_rc}"
    fi
else
    log "skipping supervisorctl start backend (bootstrap rc=${rc})"
fi

exit "${rc}"
