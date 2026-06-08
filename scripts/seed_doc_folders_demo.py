#!/usr/bin/env python3
"""
Build Pack 2.7-DOCS-FE-fix §R2 (B81) — eyeball-test fixture for the
document folder browser (B79-FE).

Creates two `[DEMO]`-marked suppliers with a representative folder
tree + a handful of documents so the operator has something to click
on when the page loads:

  [DEMO] Northgate Builders Ltd
    ├── Compliance/                  (2 docs — PL + EL)
    ├── Insurance/
    │   ├── 2024/
    │   └── 2025/                    (1 doc — Pro Indemnity 2025)
    └── Contracts/                   (empty — operator can test
                                       "archive empty folder")

  [DEMO] Severn Plant Hire
    └── Compliance/                  (1 doc — mirrors what a real
                                       migrated supplier looks like)

Idempotent: re-runs match on the `[DEMO]` name marker; prior demo
suppliers' folders + docs are wiped and re-seeded. **NEVER** touches
non-demo suppliers (every delete is scoped to demo supplier ids).

Run:    python scripts/seed_doc_folders_demo.py
Verify: navigate to a supplier detail page → Documents tab.
"""
from __future__ import annotations

import os
import sys
import uuid
from typing import Optional

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)

ADMIN_EMAIL = "test-admin@example.test"

# Sole identification marker — the suffix is in the supplier name so
# re-runs and cleanup are scoped to demo rows only. NEVER widen these
# matchers; broadening them risks deleting real supplier data.
DEMO_MARKER = "[DEMO]"
DEMO_SUPPLIERS = [
    "[DEMO] Northgate Builders Ltd",
    "[DEMO] Severn Plant Hire",
]


def _fail(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)
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


def _wipe_demo(conn, tenant_id: uuid.UUID) -> None:
    """Delete prior `[DEMO]`-suppliers and ALL their folders/docs.

    Idempotent + safe — every delete is scoped to demo supplier ids
    via `name LIKE '[DEMO]%'`. Non-demo rows are NEVER touched.
    """
    demo_ids = [
        str(r.id) for r in conn.execute(text("""
            SELECT id FROM suppliers
             WHERE tenant_id = :tid AND name LIKE :marker
        """), {"tid": tenant_id, "marker": f"{DEMO_MARKER}%"})
    ]
    if not demo_ids:
        return
    conn.execute(text("""
        DELETE FROM supplier_documents
         WHERE supplier_id::text = ANY(:ids)
    """), {"ids": demo_ids})
    conn.execute(text("""
        DELETE FROM document_folders
         WHERE owner_type = 'supplier'
           AND owner_id::text = ANY(:ids)
    """), {"ids": demo_ids})
    conn.execute(text("""
        DELETE FROM suppliers
         WHERE id::text = ANY(:ids)
    """), {"ids": demo_ids})


def _mk_supplier(conn, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
                 name: str) -> uuid.UUID:
    row = conn.execute(text("""
        INSERT INTO suppliers
            (tenant_id, name, created_by, updated_by)
        VALUES (:tid, :name, :uid, :uid)
        RETURNING id
    """), {"tid": tenant_id, "name": name, "uid": user_id}).first()
    return row.id


def _mk_folder(conn, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
               supplier_id: uuid.UUID, name: str,
               parent_id: Optional[uuid.UUID] = None) -> uuid.UUID:
    row = conn.execute(text("""
        INSERT INTO document_folders
            (tenant_id, owner_type, owner_id, parent_id, name,
             is_archived, created_by, updated_by)
        VALUES (:tid, 'supplier', :sid, :pid, :name, false, :uid, :uid)
        RETURNING id
    """), {
        "tid": tenant_id, "sid": supplier_id, "pid": parent_id,
        "name": name, "uid": user_id,
    }).first()
    return row.id


def _mk_doc(conn, *, tenant_id: uuid.UUID, user_id: uuid.UUID,
            supplier_id: uuid.UUID, folder_id: uuid.UUID,
            doc_type: Optional[str], title: Optional[str],
            issued_on: Optional[str] = None,
            expires_on: Optional[str] = None,
            notes: Optional[str] = None) -> uuid.UUID:
    row = conn.execute(text("""
        INSERT INTO supplier_documents
            (tenant_id, supplier_id, doc_type, title, folder_id,
             issued_on, expires_on, notes, is_archived,
             created_by, updated_by)
        VALUES (:tid, :sid, :dt, :title, :fid,
                :iss, :exp, :notes, false,
                :uid, :uid)
        RETURNING id
    """), {
        "tid": tenant_id, "sid": supplier_id,
        "dt": doc_type, "title": title, "fid": folder_id,
        "iss": issued_on, "exp": expires_on, "notes": notes,
        "uid": user_id,
    }).first()
    return row.id


def main() -> int:
    engine = create_engine(DATABASE_URL, future=True)
    with engine.begin() as conn:
        user_id, tenant_id = _admin_user(conn)
        _wipe_demo(conn, tenant_id)

        # ─── Supplier 1: a fuller tree ──────────────────────────────
        s1_id = _mk_supplier(
            conn, tenant_id=tenant_id, user_id=user_id,
            name=DEMO_SUPPLIERS[0],
        )
        compliance = _mk_folder(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, name="Compliance",
        )
        insurance = _mk_folder(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, name="Insurance",
        )
        _ = _mk_folder(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, name="2024", parent_id=insurance,
        )
        ins_2025 = _mk_folder(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, name="2025", parent_id=insurance,
        )
        _contracts = _mk_folder(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, name="Contracts",
        )
        # 2 compliance docs — Public Liability with explicit title +
        # Employers Liability with null title (shows the auto-fill
        # behaviour on the list).
        _mk_doc(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, folder_id=compliance,
            doc_type="Public_Liability",
            title="Public Liability 2025-2026",
            issued_on="2025-04-01", expires_on="2026-03-31",
        )
        _mk_doc(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, folder_id=compliance,
            doc_type="Employers_Liability",
            title=None,
            issued_on="2025-01-15", expires_on="2026-01-14",
            notes="Renewal letter due before expiry.",
        )
        # 1 PI doc in 2025/.
        _mk_doc(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s1_id, folder_id=ins_2025,
            doc_type="Professional_Indemnity",
            title="PI 2025",
            issued_on="2025-04-01", expires_on="2026-03-31",
        )

        # ─── Supplier 2: migrated-style single Compliance folder ────
        s2_id = _mk_supplier(
            conn, tenant_id=tenant_id, user_id=user_id,
            name=DEMO_SUPPLIERS[1],
        )
        s2_compliance = _mk_folder(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s2_id, name="Compliance",
        )
        _mk_doc(
            conn, tenant_id=tenant_id, user_id=user_id,
            supplier_id=s2_id, folder_id=s2_compliance,
            doc_type="Other",
            title="CIS verification letter (HMRC)",
            issued_on="2025-02-10",
        )

        # Summary counts AFTER all inserts (still inside the same
        # transaction so the read sees the writes).
        s_count = conn.execute(text("""
            SELECT COUNT(*) FROM suppliers
             WHERE tenant_id = :tid AND name LIKE :marker
        """), {"tid": tenant_id, "marker": f"{DEMO_MARKER}%"}).scalar()
        f_count = conn.execute(text("""
            SELECT COUNT(*) FROM document_folders df
              JOIN suppliers s ON s.id = df.owner_id
             WHERE df.tenant_id = :tid
               AND df.owner_type = 'supplier'
               AND s.name LIKE :marker
        """), {"tid": tenant_id, "marker": f"{DEMO_MARKER}%"}).scalar()
        d_count = conn.execute(text("""
            SELECT COUNT(*) FROM supplier_documents sd
              JOIN suppliers s ON s.id = sd.supplier_id
             WHERE s.tenant_id = :tid AND s.name LIKE :marker
        """), {"tid": tenant_id, "marker": f"{DEMO_MARKER}%"}).scalar()

    print("──────────────────────────────────────────────────────────")
    print(" Document-folder demo seed — Build Pack 2.7-DOCS-FE-fix §R2")
    print("──────────────────────────────────────────────────────────")
    print(f"  Tenant:        {tenant_id}")
    print(f"  Admin user:    {ADMIN_EMAIL}")
    print(f"  Demo suppliers (re-seeded clean): {s_count}")
    print(f"  Folders:                          {f_count}")
    print(f"  Documents:                        {d_count}")
    print("  Suppliers created:")
    for n in DEMO_SUPPLIERS:
        print(f"    • {n}")
    print("")
    print("  Open the app → Suppliers → click a [DEMO] supplier.")
    print(f"  Backend:  {BASE_URL}/api/v1/suppliers")
    print("  Re-run is idempotent — same script, same counts, no dupes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
