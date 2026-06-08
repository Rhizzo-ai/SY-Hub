#!/usr/bin/env python3
"""
Chat 47 (Build Pack 2.8-FE-i) — eyeball-test fixture for the
Subcontracts surface on the supplier Contracts tab.

Creates ONE `[DEMO]`-marked Contractor supplier and a small set of
subcontracts in different lifecycle states, attached to an EXISTING
project, so the operator has something to click on the moment the
Contracts tab loads:

  [DEMO] Avon Groundworks Ltd   (supplier_type = 'Contractor')
    ├── Draft     subcontract — "Groundworks package"      (no signed_at — Activate should 409 until edited)
    ├── Draft     subcontract — "Drainage package"         (signed_at SET — Activate should succeed)
    ├── Active    subcontract — "Steel frame supply & fix"  (Complete / Terminate available)
    ├── Completed subcontract — "Site clearance"            (terminal — no action buttons)
    └── Terminated subcontract — "Scaffolding (cancelled)"  (terminal — no action buttons)

Each subcontract gets a sensible original_contract_sum/current_contract_sum
and a retention_pct so the sensitive-sum gating is visible.

REUSES, never invents:
  - the seed admin user + tenant (looked up; never created)
  - an EXISTING project on that tenant (projects require an entity +
    a dozen enum fields, so we attach to a real one rather than fabricate)

Idempotent: re-runs match on the `[DEMO]` supplier-name marker; the prior
demo Contractor + ALL its subcontracts (and their variations, via FK
CASCADE) are wiped and re-seeded. NEVER touches non-demo suppliers or
their subcontracts — every delete is scoped to the demo supplier id.

Run:    cd /app/backend && /root/.venv/bin/python /app/scripts/seed_subcontracts_demo.py
Verify: open the [DEMO] Avon Groundworks supplier → Contracts tab.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]

ADMIN_EMAIL = "test-admin@example.test"

# Sole identification marker — the suffix is in the supplier name so
# re-runs and cleanup are scoped to demo rows only. NEVER widen this
# matcher; broadening it risks deleting real supplier/subcontract data.
DEMO_MARKER = "[DEMO]"
DEMO_CONTRACTOR = "[DEMO] Avon Groundworks Ltd"


def _fail(msg: str) -> None:
    print(f"  \u2717 {msg}", file=sys.stderr)
    sys.exit(1)


def _admin_user(conn) -> tuple[uuid.UUID, uuid.UUID]:
    """Return (user_id, tenant_id) of the seed admin."""
    row = conn.execute(text("""
        SELECT id, tenant_id FROM users
         WHERE email = :email
    """), {"email": ADMIN_EMAIL}).first()
    if row is None:
        _fail(
            f"admin user {ADMIN_EMAIL!r} not found. Run "
            f"`python -m app.bootstrap` first."
        )
    return row.id, row.tenant_id


def _pick_project(conn) -> tuple[uuid.UUID, str]:
    """Reuse an existing Active project.

    Projects carry a required entity FK + many enum columns, so we do
    NOT fabricate one — we attach the demo subcontracts to a real
    project. Prefer an Active project; fall back to any project.

    NOTE: the `projects` table has NO `tenant_id` column (Pattern α —
    tenant resolution is via visible-project-id scoping elsewhere), so
    this picks the first Active project full stop. Fine for a
    single-tenant-live demo fixture.
    """
    row = conn.execute(text("""
        SELECT id, COALESCE(name, project_code) AS label
          FROM projects
         WHERE status = 'Active'
         ORDER BY created_at
         LIMIT 1
    """)).first()
    if row is None:
        row = conn.execute(text("""
            SELECT id, COALESCE(name, project_code) AS label
              FROM projects
             ORDER BY created_at
             LIMIT 1
        """)).first()
    if row is None:
        _fail(
            "no project found on this tenant. Create at least one "
            "project first (Projects screen), then re-run."
        )
    return row.id, row.label


def _wipe_demo(conn, tenant_id: uuid.UUID) -> None:
    """Delete prior [DEMO] Contractor(s) and ALL their subcontracts.

    Idempotent + safe — scoped to demo supplier ids via name LIKE
    '[DEMO]%'. Subcontract_variations cascade on the subcontract FK
    (ondelete=CASCADE). Non-demo rows are NEVER touched.
    """
    demo_ids = [
        str(r.id) for r in conn.execute(text("""
            SELECT id FROM suppliers
             WHERE tenant_id = :tid AND name LIKE :marker
        """), {"tid": tenant_id, "marker": f"{DEMO_MARKER}%"})
    ]
    if not demo_ids:
        return
    # Subcontracts first (variations cascade off the subcontract FK),
    # then the supplier rows.
    conn.execute(text("""
        DELETE FROM subcontracts
         WHERE subcontractor_id::text = ANY(:ids)
    """), {"ids": demo_ids})
    conn.execute(text("""
        DELETE FROM suppliers
         WHERE id::text = ANY(:ids)
    """), {"ids": demo_ids})


def _mk_contractor(conn, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
                   name: str) -> uuid.UUID:
    """Create a Contractor-type supplier (the subcontract gate keys on
    supplier_type='Contractor')."""
    row = conn.execute(text("""
        INSERT INTO suppliers
            (tenant_id, name, supplier_type, cis_registered,
             created_by, updated_by)
        VALUES (:tid, :name, 'Contractor', true, :uid, :uid)
        RETURNING id
    """), {"tid": tenant_id, "name": name, "uid": user_id}).first()
    return row.id


_REF_SEQ = 0


def _next_ref(project_label: str) -> str:
    """Generate a unique-per-project reference (uq_subcontracts_project_reference)."""
    global _REF_SEQ
    _REF_SEQ += 1
    return f"SC-DEMO-{_REF_SEQ:03d}"


def _mk_subcontract(conn, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
                    project_id: uuid.UUID, project_label: str,
                    subcontractor_id: uuid.UUID, title: str, status: str,
                    original_sum: str, retention_pct: str,
                    signed: bool) -> uuid.UUID:
    """Insert one subcontract row directly in the given lifecycle state.

    current_contract_sum mirrors original_contract_sum (no variations
    until 2.8-FE-iii). signed_at is set only when `signed` (lets the
    operator see Activate succeed vs 409-on-unsigned).
    """
    signed_at = datetime.now(timezone.utc) if signed else None
    signed_by = user_id if signed else None
    row = conn.execute(text("""
        INSERT INTO subcontracts
            (tenant_id, project_id, subcontractor_id, reference, title,
             scope_description, status, original_contract_sum,
             current_contract_sum, retention_pct, cis_applies,
             signed_at, signed_by, created_by)
        VALUES (:tid, :pid, :sid, :ref, :title,
                :scope, :status, :osum,
                :osum, :ret, true,
                :signed_at, :signed_by, :uid)
        RETURNING id
    """), {
        "tid": tenant_id, "pid": project_id, "sid": subcontractor_id,
        "ref": _next_ref(project_label), "title": title,
        "scope": f"Demo subcontract — {title}.",
        "status": status, "osum": original_sum, "ret": retention_pct,
        "signed_at": signed_at, "signed_by": signed_by, "uid": user_id,
    }).first()
    return row.id


def main() -> int:
    engine = create_engine(DATABASE_URL, future=True)
    with engine.begin() as conn:
        user_id, tenant_id = _admin_user(conn)
        project_id, project_label = _pick_project(conn)
        _wipe_demo(conn, tenant_id)

        c_id = _mk_contractor(
            conn, tenant_id=tenant_id, user_id=user_id,
            name=DEMO_CONTRACTOR,
        )

        # Draft, NOT signed — Activate should 409 ("signed date required").
        _mk_subcontract(
            conn, tenant_id=tenant_id, user_id=user_id,
            project_id=project_id, project_label=project_label,
            subcontractor_id=c_id, title="Groundworks package",
            status="Draft", original_sum="125000.00",
            retention_pct="5.00", signed=False,
        )
        # Draft, signed — Activate should succeed.
        _mk_subcontract(
            conn, tenant_id=tenant_id, user_id=user_id,
            project_id=project_id, project_label=project_label,
            subcontractor_id=c_id, title="Drainage package",
            status="Draft", original_sum="48500.00",
            retention_pct="5.00", signed=True,
        )
        # Active — Complete / Terminate available.
        _mk_subcontract(
            conn, tenant_id=tenant_id, user_id=user_id,
            project_id=project_id, project_label=project_label,
            subcontractor_id=c_id, title="Steel frame supply & fix",
            status="Active", original_sum="312750.00",
            retention_pct="3.00", signed=True,
        )
        # Completed — terminal, no action buttons.
        _mk_subcontract(
            conn, tenant_id=tenant_id, user_id=user_id,
            project_id=project_id, project_label=project_label,
            subcontractor_id=c_id, title="Site clearance",
            status="Completed", original_sum="22000.00",
            retention_pct="0.00", signed=True,
        )
        # Terminated — terminal, no action buttons.
        _mk_subcontract(
            conn, tenant_id=tenant_id, user_id=user_id,
            project_id=project_id, project_label=project_label,
            subcontractor_id=c_id, title="Scaffolding (cancelled)",
            status="Terminated", original_sum="0.00",
            retention_pct="0.00", signed=False,
        )

        print(f"  \u2713 seeded {DEMO_CONTRACTOR!r}")
        print(f"  \u2713 5 subcontracts on project {project_label!r}")
        print("  \u2713 states: Draft(unsigned), Draft(signed), Active, "
              "Completed, Terminated")
        print()
        print("  Open the supplier \u2192 Contracts tab to eyeball.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
