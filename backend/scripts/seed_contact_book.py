"""Chat 41 §R6 (Prompt 2.7-BE-rev-A) — idempotent contact-book seed.

Seeds a small starter trade vocabulary and four sample contacts (one of
each `supplier_type`: Contractor / Supplier / Consultant / Other) into
the default tenant. Designed to give a freshly-bootstrapped pod a
realistic Contact Book the moment it boots — useful for FE smoke checks
and operator demos.

Idempotent semantics:
  * Trades are upserted by `(tenant_id, LOWER(name))` via
    `services.trades.get_or_create_trade` — re-runs return existing rows.
  * Suppliers are upserted by `(tenant_id, LOWER(name))` (matches the
    `ux_suppliers_tenant_name_ci` index). If a matching supplier exists,
    only its `trade_id` is repaired (so re-running picks up new trade
    rows without touching other fields).

Run:
    python /app/backend/scripts/seed_contact_book.py
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy import func, select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models.suppliers import Supplier  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import trades as trades_svc  # noqa: E402


# Starter trade vocabulary — small, opinionated, easy to extend.
STARTER_TRADES: tuple[str, ...] = (
    "Groundworks",
    "Bricklaying",
    "Carpentry",
    "Electrical",
    "Plumbing",
    "Plastering",
    "Roofing",
    "Painting & Decorating",
)

# Sample contacts — one of each supplier_type, tagged with the trade
# they map to. Trade name lookup is case-insensitive at runtime.
SAMPLE_CONTACTS: tuple[tuple[str, str, str | None], ...] = (
    # (name,                         supplier_type, trade_name_or_None)
    ("Sample Bricklayers Ltd",       "Contractor",  "Bricklaying"),
    ("Sample Builders' Merchants",   "Supplier",    None),
    ("Sample QS Consultants",        "Consultant",  None),
    ("Sample Hire Plant Co",         "Other",       None),
)


def _resolve_seed_user(db, tenant_id: uuid.UUID) -> uuid.UUID:
    """Pick an admin user in the tenant to attribute audit rows to.

    Falls back to any user in the tenant if test-admin isn't present.
    """
    user = db.scalar(
        select(User).where(
            User.tenant_id == tenant_id,
            User.email == "test-admin@example.test",
        )
    )
    if user is None:
        user = db.scalar(
            select(User).where(User.tenant_id == tenant_id).limit(1)
        )
    if user is None:
        raise SystemExit(
            f"No users found in tenant {tenant_id}; "
            f"run scripts/seed_test_users.py first."
        )
    return user.id


def _get_or_create_supplier(
    db, tenant_id: uuid.UUID, user_id: uuid.UUID,
    *, name: str, supplier_type: str, trade_id: uuid.UUID | None,
) -> Supplier:
    """Upsert-by-name. If the supplier exists, repair its trade_id and
    supplier_type; if it doesn't, create with the starter defaults.
    """
    existing = db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            func.lower(Supplier.name) == name.lower(),
        )
    )
    if existing is not None:
        # Idempotent repair — touch trade + type only.
        changed = False
        if existing.trade_id != trade_id:
            existing.trade_id = trade_id
            changed = True
        if existing.supplier_type != supplier_type:
            existing.supplier_type = supplier_type
            changed = True
        if changed:
            existing.updated_by = user_id
            db.flush()
        return existing

    row = Supplier(
        tenant_id=tenant_id,
        name=name,
        supplier_type=supplier_type,
        trade_id=trade_id,
        # Contractor seed gets the default Unverified cache; others stay NULL.
        current_cis_status="Unverified" if supplier_type == "Contractor" else None,
        payment_terms_days=30,
        country="United Kingdom",
        # Chat 41 §R-eyeball-Step2A — vat_registered dropped.
        cis_registered=False,
        portal_enabled=False,
        is_archived=False,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    db.flush()
    return row


def main() -> None:
    db = SessionLocal()
    try:
        tenant_name = os.environ.get("DEFAULT_TENANT_NAME", "SY Homes")
        tenant = db.scalar(
            select(Tenant).where(Tenant.name == tenant_name)
        )
        if tenant is None:
            raise SystemExit(
                f"Tenant {tenant_name!r} not found; run app.bootstrap first."
            )

        user_id = _resolve_seed_user(db, tenant.id)

        # 1) Trades — get_or_create per name.
        trade_by_name: dict[str, uuid.UUID] = {}
        for name in STARTER_TRADES:
            t = trades_svc.get_or_create_trade(
                db, tenant.id, user_id, name,
            )
            trade_by_name[t.name.lower()] = t.id

        # 2) Sample suppliers — upsert by name; tag with trade where given.
        created = 0
        repaired = 0
        for sup_name, sup_type, trade_name in SAMPLE_CONTACTS:
            tid = trade_by_name.get(trade_name.lower()) if trade_name else None
            before_id = db.scalar(
                select(Supplier.id).where(
                    Supplier.tenant_id == tenant.id,
                    func.lower(Supplier.name) == sup_name.lower(),
                )
            )
            _get_or_create_supplier(
                db, tenant.id, user_id,
                name=sup_name, supplier_type=sup_type, trade_id=tid,
            )
            if before_id is None:
                created += 1
            else:
                repaired += 1

        db.commit()
        print(
            f"seed_contact_book: tenant={tenant.name!r} "
            f"trades={len(STARTER_TRADES)} "
            f"contacts_created={created} contacts_repaired={repaired}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
