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
`/etc/supervisor/conf.d/supervisord.conf` must have:

```ini
[program:backend]
...
autostart=false
autorestart=false
```

This is the bootstrap-fix-p0 contract:

* `autostart=false` — the backend does not come up on container boot.
  It is started only by `on-restart.sh` after `python -m app.bootstrap`
  exits with rc=0.
* `autorestart=false` — supervisor will not silently revive a failed
  backend against a half-initialised DB. A crash leaves the program
  STOPPED and visible via `supervisorctl status`; recovery is an
  explicit operator action (re-run `on-restart.sh`).

### Self-healing template (no manual edit required)

The canonical block is checked in at
[`/app/scripts/supervisord_backend.conf.template`](./supervisord_backend.conf.template).
`on-restart.sh` runs an idempotent self-heal as **step 0**, before
bootstrap:

1. Read `/etc/supervisor/conf.d/supervisord.conf`. Look inside
   `[program:backend]` for `autostart=false`.
2. **If found:** log `supervisor config already gated` and skip — no
   rewrite, file is byte-identical between runs.
3. **If not found:** splice the template into the supervisor conf,
   preserving any existing `environment=` line from the live block
   (the platform injects `APP_URL` per pod; we do not clobber it).
   Then `supervisorctl reread && supervisorctl update`. Log
   `supervisor config gated (template applied)`.
4. Hook then proceeds with bootstrap as normal.

This pattern matches the bootstrap orchestrator itself: detect drift,
self-heal, prove invariants, never require manual operator
intervention on a fresh fork.

The hook completes its bootstrap rc-translation case statement and
then runs:

```bash
if [[ "${rc}" -eq 0 ]]; then
    sudo supervisorctl start backend
fi
```

so the backend transitions from STOPPED → RUNNING only on a clean
bootstrap.

`/etc/supervisor/conf.d/supervisord.conf` carries a `# READONLY FILE`
banner that is convention, not enforcement. The hook's self-heal step
is the principled, durable answer to that warning: instead of editing
the file by hand and praying the platform never resets it, we treat
the template as the source of truth and re-apply it every time we see
drift.

**Frontend is intentionally not gated.** `[program:frontend]` keeps
`autostart=true autorestart=true` because the React dev server is
decoupled from the API at startup (axios calls happen at runtime) and
degrades gracefully when the backend is STOPPED.

### R7.7 verification (manual)

Recreating the failure path:

1. Stop postgres: `sudo supervisorctl stop postgres`.
2. Run `sudo /root/.emergent/on-restart.sh`. Expect non-zero rc=2 and
   a `[on-restart] skipping supervisorctl start backend (bootstrap
   rc=2)` line.
3. `sudo supervisorctl status backend` → `STOPPED`.
4. Restore: `sudo supervisorctl start postgres`. Re-run hook;
   `backend` flips to `RUNNING`.

Recreating the supervisor self-heal path:

1. Manually flip `autostart=true` and `autorestart=true` inside
   `[program:backend]` of the live supervisor conf.
2. Run `sudo /root/.emergent/on-restart.sh`. Expect a
   `[on-restart] supervisor config NOT gated; applying template ...`
   line followed by `[on-restart] supervisor config gated (template
   applied; backend is now autostart=false autorestart=false)`.
3. Re-run the hook; expect
   `[on-restart] supervisor config already gated`. Verify the file is
   byte-identical between runs (`diff` returns empty).
