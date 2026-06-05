"""Chat 41 §R6 (Prompt 2.7-BE-rev-A) — idempotent contact-book seed.

Seeds a starter trade vocabulary and a varied sample of contacts across
all four `supplier_type` values (Contractor / Supplier / Consultant /
Other) into the default tenant.

Chat 41 §R-eyeball-Step2B Part 3 (Prompt 2.7-FE-revision) — the seed
was expanded from 4 contacts to ~12 with varied data to exercise the
search/sort/filter flows on the Suppliers list:
  * 2–3 contacts per type
  * shared trades (two Electricians) to test sort grouping
  * mix of CIS statuses on contractors (gross, net_20, net_30,
    Unverified) — current_cis_status is service-maintained so we set
    cis_status alongside Contractor rows; current_cis_status stays
    'Unverified' on create
  * a couple archived rows
  * notes containing searchable keywords
  * trading_name + contact_name populated on several
  * a couple with full address blocks

Idempotent semantics:
  * Trades are upserted by `(tenant_id, LOWER(name))` via
    `services.trades.get_or_create_trade` — re-runs return existing rows.
  * Suppliers are upserted by `(tenant_id, LOWER(name))` (matches the
    `ux_suppliers_tenant_name_ci` index). If a matching supplier exists,
    its trade_id, supplier_type AND the §R-eyeball-Step2B "rich-data"
    fields (cis_status, trading_name, contact_name, notes, address
    block, is_archived) are repaired so a re-run converges on the same
    final state — no duplicates.

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
# The expanded sample below references some by name (case-insensitive)
# and intentionally has two Contractor rows sharing a trade (Electrical)
# so sort grouping is visible.
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


# Sample contacts — 2–3 per type, varied data to exercise search/sort.
# Field shape: dict so we can omit cleanly. Names use the "Sample"
# prefix on the starter four so re-runs match the existing rows.
SAMPLE_CONTACTS: tuple[dict, ...] = (
    # ─── Contractors (CIS subcontractor sub-type) ────────────────────
    {
        "name": "Sample Bricklayers Ltd",
        "supplier_type": "Contractor",
        "trade": "Bricklaying",
        "cis_status": "gross",
        "trading_name": "SBL Trading",
        "contact_name": "Joseph Mason",
        "notes": "Preferred bricklayer for Phase 1 schemes.",
    },
    {
        "name": "Sample Sparks Electrical",
        "supplier_type": "Contractor",
        "trade": "Electrical",
        "cis_status": "net_20",
        "contact_name": "Lina Volt",
    },
    {
        "name": "Wired-Up Contractors",
        "supplier_type": "Contractor",
        "trade": "Electrical",         # shares trade with Sample Sparks
        "cis_status": "net_30",
        "notes": "Backup electrical contractor.",
    },
    # ─── Suppliers ───────────────────────────────────────────────────
    {
        "name": "Sample Builders' Merchants",
        "supplier_type": "Supplier",
        "contact_name": "Reg Stock",
        "notes": "Trade discount account #4421. Brickwork bulk orders.",
        "address_line1": "Unit 5 Trade Park",
        "city": "Shrewsbury",
        "postcode": "SY1 3AB",
        "country": "United Kingdom",
    },
    {
        "name": "Severn Timber Supplies",
        "supplier_type": "Supplier",
        "trade": "Carpentry",
        "trading_name": "STS Timber",
    },
    {
        "name": "ArchivedCo Merchants",
        "supplier_type": "Supplier",
        "is_archived": True,            # tests "Show archived" toggle
        "notes": "Legacy supplier - replaced by Severn Timber.",
    },
    # ─── Consultants ─────────────────────────────────────────────────
    {
        "name": "Sample QS Consultants",
        "supplier_type": "Consultant",
        "contact_name": "Priya Knott",
        "address_line1": "Floor 4, 18 Castle St",
        "city": "Shrewsbury",
        "postcode": "SY1 2BQ",
        "country": "United Kingdom",
    },
    {
        "name": "Northern Planning Partners",
        "supplier_type": "Consultant",
        "notes": "Planning consultancy - used for Brickwork-heavy plots.",
    },
    # ─── Other (one-off / out-of-the-box) ────────────────────────────
    {
        "name": "Sample Hire Plant Co",
        "supplier_type": "Other",
        "trade": "Groundworks",
        "trading_name": "Plant On Demand",
    },
    {
        "name": "SkipsRUs",
        "supplier_type": "Other",
        "notes": "Weekly waste skips; favoured for Roofing tear-offs.",
    },
    {
        "name": "Ghost Vendors (Archived)",
        "supplier_type": "Other",
        "is_archived": True,            # second archived row
    },
)

# Fields the upsert path "repairs" so a re-run converges on the same
# state. is_archived is included so flipping a sample to archived in
# the script reliably re-applies on the next run.
_REPAIRABLE_FIELDS: tuple[str, ...] = (
    "supplier_type",
    "trade_id",
    "cis_status",
    "trading_name",
    "contact_name",
    "notes",
    "address_line1",
    "address_line2",
    "city",
    "postcode",
    "country",
    "is_archived",
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


def _payload_for(spec: dict, trade_by_name: dict[str, uuid.UUID]) -> dict:
    """Translate a SAMPLE_CONTACTS spec into the dict used by both the
    create path and the upsert-repair path. `trade` (name) resolves to
    `trade_id` here; unknown trade names hard-fail so a typo doesn't
    silently NULL the column."""
    payload: dict = {
        "supplier_type": spec.get("supplier_type", "Supplier"),
        "cis_status":    spec.get("cis_status"),     # None → NULL is fine
        "trading_name":  spec.get("trading_name"),
        "contact_name":  spec.get("contact_name"),
        "notes":         spec.get("notes"),
        "address_line1": spec.get("address_line1"),
        "address_line2": spec.get("address_line2"),
        "city":          spec.get("city"),
        "postcode":      spec.get("postcode"),
        "country":       spec.get("country") or "United Kingdom",
        "is_archived":   bool(spec.get("is_archived", False)),
    }
    trade_name = spec.get("trade")
    if trade_name:
        tid = trade_by_name.get(trade_name.lower())
        if tid is None:
            raise SystemExit(
                f"Sample contact {spec['name']!r} references unknown "
                f"trade {trade_name!r}; add it to STARTER_TRADES."
            )
        payload["trade_id"] = tid
    else:
        payload["trade_id"] = None
    return payload


def _get_or_create_supplier(
    db, tenant_id: uuid.UUID, user_id: uuid.UUID,
    *, name: str, fields: dict,
) -> tuple[Supplier, bool]:
    """Upsert-by-name. Returns (row, created_bool).

    On repair the fields in `_REPAIRABLE_FIELDS` are set unconditionally
    so a re-run converges on whatever the script asks for. Fields not
    listed (created_at, banking PII, etc.) stay untouched.
    """
    existing = db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == tenant_id,
            func.lower(Supplier.name) == name.lower(),
        )
    )
    if existing is not None:
        changed = False
        for key in _REPAIRABLE_FIELDS:
            new_val = fields.get(key)
            if getattr(existing, key) != new_val:
                setattr(existing, key, new_val)
                changed = True
        if changed:
            existing.updated_by = user_id
            db.flush()
        return existing, False

    row = Supplier(
        tenant_id=tenant_id,
        name=name,
        supplier_type=fields["supplier_type"],
        trade_id=fields["trade_id"],
        cis_status=fields["cis_status"],
        trading_name=fields["trading_name"],
        contact_name=fields["contact_name"],
        notes=fields["notes"],
        address_line1=fields["address_line1"],
        address_line2=fields["address_line2"],
        city=fields["city"],
        postcode=fields["postcode"],
        country=fields["country"],
        is_archived=fields["is_archived"],
        # Contractor seed gets the default Unverified cache; others stay NULL.
        current_cis_status=(
            "Unverified" if fields["supplier_type"] == "Contractor" else None
        ),
        payment_terms_days=30,
        # Chat 41 §R-eyeball-Step2A — vat_registered dropped.
        cis_registered=False,
        portal_enabled=False,
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(row)
    db.flush()
    return row, True


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

        # 2) Sample suppliers — upsert by name with rich fields.
        created = 0
        repaired = 0
        for spec in SAMPLE_CONTACTS:
            fields = _payload_for(spec, trade_by_name)
            _, was_created = _get_or_create_supplier(
                db, tenant.id, user_id,
                name=spec["name"], fields=fields,
            )
            if was_created:
                created += 1
            else:
                repaired += 1

        db.commit()
        print(
            f"seed_contact_book: tenant={tenant.name!r} "
            f"trades={len(STARTER_TRADES)} "
            f"contacts_total={len(SAMPLE_CONTACTS)} "
            f"contacts_created={created} contacts_repaired={repaired}"
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
