"""Idempotent seed: SY Homes tenant + three legal entities.

Safe to run on every startup — uses upsert-by-unique-name logic.
"""
from __future__ import annotations

import logging
import os

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Entity, Tenant

log = logging.getLogger(__name__)

SEED_ENTITIES = [
    {
        "name": "SY Homes Ltd",
        "legal_name": "SY Homes Limited",
        "entity_type": "Parent",
        "parent_slot": None,
        "registered_address": "To be completed by admin",
        "default_currency": "GBP",
        "status": "Active",
    },
    {
        "name": "SY Homes (Shrewsbury) Ltd",
        "legal_name": "SY Homes (Shrewsbury) Limited",
        "entity_type": "SPV",
        "parent_slot": "SY Homes Ltd",
        "registered_address": "To be completed by admin",
        "default_currency": "GBP",
        "status": "Active",
    },
    {
        "name": "SY Homes (Construction) Ltd",
        "legal_name": "SY Homes (Construction) Limited",
        "entity_type": "ConstructionCo",
        "parent_slot": "SY Homes Ltd",
        "registered_address": "To be completed by admin",
        "default_currency": "GBP",
        "cis_status": "Contractor",
        "status": "Active",
    },
]


def seed(db: Session | None = None) -> None:
    own = db is None
    if db is None:
        db = SessionLocal()
    try:
        tenant_name = os.environ.get("DEFAULT_TENANT_NAME", "SY Homes")
        tenant = db.scalar(select(Tenant).where(Tenant.name == tenant_name))
        if tenant is None:
            tenant = Tenant(name=tenant_name)
            db.add(tenant)
            db.flush()
            log.info("Seeded tenant: %s (%s)", tenant.name, tenant.id)

        existing = {
            e.name: e
            for e in db.scalars(
                select(Entity).where(Entity.tenant_id == tenant.id)
            ).all()
        }

        created_by_name: dict[str, Entity] = dict(existing)
        # Two-pass: first create parents, then children (so parent_entity_id resolves).
        for row in SEED_ENTITIES:
            if row["name"] in existing:
                continue
            if row["parent_slot"] is not None:
                continue
            payload = {k: v for k, v in row.items() if k != "parent_slot"}
            ent = Entity(tenant_id=tenant.id, **payload)
            db.add(ent)
            db.flush()
            created_by_name[row["name"]] = ent
            log.info("Seeded entity (parent): %s (%s)", ent.name, ent.id)

        for row in SEED_ENTITIES:
            if row["name"] in existing:
                continue
            if row["parent_slot"] is None:
                continue
            parent_ent = created_by_name.get(row["parent_slot"])
            if parent_ent is None:
                log.warning(
                    "Skipping seed %s — parent %s not found",
                    row["name"],
                    row["parent_slot"],
                )
                continue
            payload = {k: v for k, v in row.items() if k != "parent_slot"}
            payload["parent_entity_id"] = parent_ent.id
            ent = Entity(tenant_id=tenant.id, **payload)
            db.add(ent)
            db.flush()
            created_by_name[row["name"]] = ent
            log.info("Seeded entity (child): %s (%s)", ent.name, ent.id)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        if own:
            db.close()
