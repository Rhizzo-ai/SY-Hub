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
