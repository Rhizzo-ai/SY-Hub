#!/usr/bin/env bash
# /app/scripts/provision_postgres.sh
#
# Durable pod-recycle recovery for SY Hub.
# Owned by Track 8 / pre-launch hardening.
#
# Lives in /app/scripts/ (NOT /tmp/) so it survives Emergent pod recycles —
# the writable layer wipe-pattern observed in Chat 17 erases /usr/lib/postgresql/,
# /var/lib/postgresql/, /tmp/*, and the `postgres` system user, but leaves /app
# and /root/.emergent intact.
#
# Idempotent: skips any step that's already complete (install present, role
# present, supervisor config present). Safe to run after every pod restart.
#
# Invocation:
#   bash /app/scripts/provision_postgres.sh
#
# Expected total runtime: 60-120s on a cold pod (apt-get dominates).
#
# Exit codes:
#   0  success — supervisor running, postgres up, bootstrap ok, backend started
#   1  apt-get install failed
#   2  postgres failed to start standalone for role provisioning
#   3  bootstrap (python -m app.bootstrap) failed
#
# Recovery sequence:
#   1. Install postgresql-16 from PGDG apt repo (if missing).
#   2. Start a one-shot postgres on the default cluster.
#   3. Create role `syhomes` + database `syhomes` + pgcrypto extension
#      (skip if already present — idempotent CREATE OR REPLACE via DO block).
#   4. Stop the one-shot postgres.
#   5. Ensure /etc/supervisor/conf.d/supervisord_postgres.conf exists.
#   6. Start supervisor (`service supervisor start`).
#   7. Run /root/.emergent/on-restart.sh which calls `python -m app.bootstrap`
#      (alembic upgrade head, seeds RBAC/permissions/test-users, starts backend).
#
# Open question (Track 8 investigation):
#   The bootstrap-fix-p0 contract states `on-restart.sh` should detect this
#   failure and re-provision automatically. Empirically, on a fresh pod
#   recycle, supervisord refuses to start because [program:postgres] in
#   /etc/supervisor/conf.d/supervisord_postgres.conf references user=postgres
#   which no longer exists — and `service supervisor start` exits early with
#   that config error, never invoking on-restart.sh.

set -uo pipefail

ts() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }
log() { echo "$(ts) [provision-pg] $*" >&2; }

# ─── 1. Install postgresql-16 if absent ──────────────────────────────
if [ ! -d /usr/lib/postgresql/16 ]; then
    log "step=install_pg result=missing — installing postgresql-16 from PGDG"
    sudo install -d /usr/share/postgresql-common/pgdg
    sudo curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
         -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc 2>/dev/null
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
         | sudo tee /etc/apt/sources.list.d/pgdg.list > /dev/null
    sudo apt-get update -qq
    if ! sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
            postgresql-16 postgresql-contrib-16 postgresql-client-16; then
        log "step=install_pg result=FAIL exit=1"
        exit 1
    fi
    log "step=install_pg result=ok"
else
    log "step=install_pg result=skip (already installed)"
fi

# ─── 2. Start one-shot postgres for role provisioning ────────────────
if [ ! -f /tmp/pg_provisioned.flag ] || ! id postgres &> /dev/null; then
    : # always run when system user state uncertain
fi

# Detect whether we still need to provision the role.
PG_BIN=/usr/lib/postgresql/16/bin/postgres
PSQL_BIN=/usr/lib/postgresql/16/bin/psql

# Stop any existing standalone we might have left running.
sudo pkill -INT -f "${PG_BIN}.*-D /var/lib/postgresql/16/main" 2>/dev/null || true
sleep 1

log "step=start_oneshot starting postgres for role provisioning"
sudo -u postgres "${PG_BIN}" -D /var/lib/postgresql/16/main \
  -c config_file=/etc/postgresql/16/main/postgresql.conf \
  -c hba_file=/etc/postgresql/16/main/pg_hba.conf \
  -c ident_file=/etc/postgresql/16/main/pg_ident.conf > /tmp/pg_oneshot.log 2>&1 &
ONESHOT_PID=$!

# Wait up to 15s for socket.
for _ in $(seq 1 15); do
    if sudo -u postgres "${PSQL_BIN}" -c "SELECT 1;" &> /dev/null; then break; fi
    sleep 1
done

if ! sudo -u postgres "${PSQL_BIN}" -c "SELECT 1;" &> /dev/null; then
    log "step=start_oneshot result=FAIL pg_oneshot.log:"
    tail -5 /tmp/pg_oneshot.log >&2
    exit 2
fi

log "step=provision_role creating role + DB if absent (idempotent)"
sudo -u postgres "${PSQL_BIN}" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='syhomes') THEN
    CREATE ROLE syhomes WITH LOGIN PASSWORD 'syhomes_dev' CREATEDB;
  END IF;
END$$;

SELECT 'create db' WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname='syhomes')
\gexec
SQL
sudo -u postgres "${PSQL_BIN}" -tc "SELECT 1 FROM pg_database WHERE datname='syhomes'" | grep -q 1 || \
    sudo -u postgres "${PSQL_BIN}" -c "CREATE DATABASE syhomes OWNER syhomes;"
sudo -u postgres "${PSQL_BIN}" -d syhomes -c "CREATE EXTENSION IF NOT EXISTS pgcrypto;" > /dev/null

log "step=stop_oneshot stopping standalone postgres"
sudo pkill -INT -f "${PG_BIN}.*-D /var/lib/postgresql/16/main" 2>/dev/null || true
sleep 3

# ─── 3. Ensure supervisor postgres config ───────────────────────────
if [ ! -f /etc/supervisor/conf.d/supervisord_postgres.conf ]; then
    log "step=supervisor_conf writing /etc/supervisor/conf.d/supervisord_postgres.conf"
    sudo tee /etc/supervisor/conf.d/supervisord_postgres.conf > /dev/null <<CONF
[program:postgres]
command=/usr/lib/postgresql/16/bin/postgres -D /var/lib/postgresql/16/main -c config_file=/etc/postgresql/16/main/postgresql.conf -c hba_file=/etc/postgresql/16/main/pg_hba.conf -c ident_file=/etc/postgresql/16/main/pg_ident.conf
user=postgres
autostart=true
autorestart=true
priority=50
stopsignal=INT
stopwaitsecs=30
stdout_logfile=/var/log/supervisor/postgres.out.log
stderr_logfile=/var/log/supervisor/postgres.err.log
CONF
else
    log "step=supervisor_conf result=skip (present)"
fi

# ─── 4. Start supervisor ─────────────────────────────────────────────
if [ ! -S /var/run/supervisor.sock ]; then
    log "step=start_supervisor"
    sudo service supervisor start 2>&1 | tail -3 >&2
    sleep 6
else
    log "step=start_supervisor result=skip (already running)"
fi

# ─── 4.5. Self-install on-restart.sh wiring (Track 8 P0) ─────────────
# Durability: /root/.emergent/on-restart.sh lives outside the repo and may
# be wiped on pod recycle. The repo-resident template at
# /app/scripts/on-restart.sh.template is the durable source of truth.
# Self-install must happen BEFORE step 5 (which invokes on-restart.sh),
# otherwise a cold pod with no /root/.emergent/on-restart.sh would fail
# step 5 before we ever reach an end-of-script self-install. Idempotent:
# we only (re)install if the live copy does not reference this script.
if ! grep -q "provision_postgres.sh" /root/.emergent/on-restart.sh 2>/dev/null; then
    log "step=self_install installing on-restart.sh from /app/scripts/on-restart.sh.template"
    sudo mkdir -p /root/.emergent
    if [ ! -f /app/scripts/on-restart.sh.template ]; then
        log "step=self_install result=FAIL template missing at /app/scripts/on-restart.sh.template"
        exit 3
    fi
    sudo cp /app/scripts/on-restart.sh.template /root/.emergent/on-restart.sh
    sudo chmod +x /root/.emergent/on-restart.sh
    log "step=self_install result=ok"
else
    log "step=self_install result=skip (on-restart.sh already references provision_postgres.sh)"
fi

# ─── 5. Run app bootstrap (alembic + seeds + backend start) ──────────
log "step=app_bootstrap invoking on-restart.sh"
if ! bash /root/.emergent/on-restart.sh 2>&1 | tail -5 >&2; then
    log "step=app_bootstrap result=FAIL"
    exit 3
fi

log "step=verify supervisor status:"
sudo supervisorctl status 2>&1 | sed 's/^/  /' >&2

log "DONE"
