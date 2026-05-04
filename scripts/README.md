# SY Hub bootstrap scripts

## `on-restart.sh`

Canonical copy of the Emergent pod-restart hook. Owned by the
**bootstrap-fix-p0** build pack.

The live script that Emergent invokes on every pod boot lives at
`/root/.emergent/on-restart.sh` (outside the repository — it is part of
the per-pod hook directory, not the application bundle).
This file is the source of truth; on a fresh Emergent fork the agent
must install it once:

```bash
sudo install -m 0755 /app/scripts/on-restart.sh /root/.emergent/on-restart.sh
```

After that, every container start triggers the script automatically.
The script's only job is to source `.env`, activate the venv, cd into
`/app/backend`, and invoke `python -m app.bootstrap`. All sequencing,
locking, seeding, and verification logic lives in `app.bootstrap` —
see that module's docstring for the full runbook and exit-code map.

To keep the live copy in sync with the canonical copy after edits:

```bash
sudo install -m 0755 /app/scripts/on-restart.sh /root/.emergent/on-restart.sh
```
(idempotent; copies + chmods atomically.)


## Supervisor backend gating

`on-restart.sh` is a fail-loud orchestrator. To prevent it from being
paired with a fail-soft supervisor, `[program:backend]` in
`/etc/supervisor/conf.d/supervisord.conf` has been edited to:

```ini
[program:backend]
...
autostart=false
autorestart=false
```

This is intentional and **required** for the bootstrap-fix-p0 contract:

* `autostart=false` — the backend does not come up on container boot.
  It is started only by `on-restart.sh` after `python -m app.bootstrap`
  exits with rc=0.
* `autorestart=false` — supervisor will not silently revive a failed
  backend against a half-initialised DB. A crash leaves the program
  STOPPED and visible via `supervisorctl status`; recovery is an
  explicit operator action (re-run `on-restart.sh`).

The hook completes its rc-translation case statement and then runs:

```bash
if [[ "${rc}" -eq 0 ]]; then
    sudo supervisorctl start backend
fi
```

so the backend transitions from STOPPED → RUNNING only on a clean
bootstrap.

`/etc/supervisor/conf.d/supervisord.conf` carries a `# READONLY FILE`
banner that is convention, not enforcement. The edit above is a
principled deviation; if Emergent's platform rewrites the file on a
future system update, the next fork must re-apply it (the inline
comment block above the autostart lines documents the contract for the
next reader).

**Frontend is intentionally not gated.** `[program:frontend]` keeps
`autostart=true autorestart=true` because the React dev server is
decoupled from the API at startup (axios calls happen at runtime) and
degrades gracefully when the backend is STOPPED.

### R7.7 verification (manual)

1. Break a bootstrap invariant (e.g., `DELETE FROM permissions WHERE
   action = '<some_seeded_action>'`).
2. Run `sudo /root/.emergent/on-restart.sh`. Expect non-zero rc and a
   `[on-restart] skipping supervisorctl start backend` line.
3. `sudo supervisorctl status backend` → `STOPPED`.
4. Restore the row (re-run RBAC seed, or re-run bootstrap which is
   idempotent), run `sudo /root/.emergent/on-restart.sh` again.
5. `sudo supervisorctl status backend` → `RUNNING`.
