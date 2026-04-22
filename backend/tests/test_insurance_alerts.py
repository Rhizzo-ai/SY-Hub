"""Insurance alert threshold sweep — exact-day firing tests.

Covers Prompt 1.1 acceptance criterion #5: alerts fire at 60, 30, 14, 7, 0 days
before expiry (and every day while expired). Monkey-patches `_emit_alert` to
capture invocations without hitting the notifications table (not yet built).
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.db import SessionLocal
from app.jobs import insurance_alerts as ia
from app.models import Entity, Tenant


@pytest.fixture()
def isolated_tenant():
    """Create a throw-away tenant + single entity row so sweeps are deterministic.

    Clean-up runs after each test.
    """
    db = SessionLocal()
    try:
        t = Tenant(name=f"TEST_T_{uuid.uuid4().hex[:8]}")
        db.add(t)
        db.flush()
        ent = Entity(
            tenant_id=t.id,
            name="TEST_InsuranceEntity",
            legal_name="TEST Insurance Entity Ltd",
            entity_type="SPV",
            registered_address="Test Address",
            default_currency="GBP",
            status="Active",
        )
        db.add(ent)
        db.commit()
        yield db, t, ent
    finally:
        db.execute(text("DELETE FROM entities WHERE tenant_id = :tid"), {"tid": t.id})
        db.execute(text("DELETE FROM tenants WHERE id = :tid"), {"tid": t.id})
        db.commit()
        db.close()


@pytest.fixture()
def captured_alerts(monkeypatch):
    captured: list[dict] = []

    def _fake_emit(alert, tenant_id, severity):
        captured.append(
            {
                "entity_name": alert.entity_name,
                "policy": alert.policy,
                "days": alert.days_until_expiry,
                "severity": severity,
                "tenant_id": tenant_id,
            }
        )

    monkeypatch.setattr(ia, "_emit_alert", _fake_emit)
    return captured


def _set_el_days(db, ent, days: int):
    ent.el_insurance_expires = date.today() + timedelta(days=days)
    # Clear the other policies so each test is isolated
    ent.pl_insurance_expires = None
    ent.pi_insurance_expires = None
    ent.all_risks_insurance_expires = None
    db.commit()


@pytest.mark.parametrize(
    "days,expected_severity",
    [
        (60, "60_day"),
        (30, "30_day"),
        (14, "14_day"),
        (7, "7_day"),
        (0, "0_day"),
    ],
)
def test_sweep_fires_at_exact_threshold(
    isolated_tenant, captured_alerts, days, expected_severity
):
    """At days=60, 30, 14, 7, 0 → exactly one emit with the right severity label."""
    db, tenant, ent = isolated_tenant
    _set_el_days(db, ent, days)

    emitted = ia.run_insurance_alert_sweep()

    mine = [a for a in captured_alerts if a["entity_name"] == "TEST_InsuranceEntity"]
    assert len(mine) == 1, (
        f"Expected exactly 1 emit at days={days}, got {len(mine)}: {mine}"
    )
    assert mine[0]["severity"] == expected_severity
    assert mine[0]["policy"] == "EL"
    assert mine[0]["days"] == days
    assert mine[0]["tenant_id"] == tenant.id
    assert emitted >= 1


@pytest.mark.parametrize("days", [59, 61, 45, 31, 29, 15, 13, 8, 6, 1])
def test_sweep_does_not_fire_off_threshold(isolated_tenant, captured_alerts, days):
    """At days NOT in {60,30,14,7,0} (and not expired) → no emit for this entity."""
    db, _, ent = isolated_tenant
    _set_el_days(db, ent, days)

    ia.run_insurance_alert_sweep()

    mine = [a for a in captured_alerts if a["entity_name"] == "TEST_InsuranceEntity"]
    assert mine == [], (
        f"Expected no emit at days={days}; got {mine}"
    )


@pytest.mark.parametrize("days_ago", [1, 7, 30, 365])
def test_sweep_fires_every_day_while_expired(
    isolated_tenant, captured_alerts, days_ago
):
    """Once past expiry, alert fires daily with severity='expired'."""
    db, _, ent = isolated_tenant
    _set_el_days(db, ent, -days_ago)

    ia.run_insurance_alert_sweep()

    mine = [a for a in captured_alerts if a["entity_name"] == "TEST_InsuranceEntity"]
    assert len(mine) == 1
    assert mine[0]["severity"] == "expired"
    assert mine[0]["days"] == -days_ago


def test_sweep_fires_once_per_policy(isolated_tenant, captured_alerts):
    """An entity with multiple policies at threshold fires once per policy."""
    db, _, ent = isolated_tenant
    today = date.today()
    ent.el_insurance_expires = today + timedelta(days=60)
    ent.pl_insurance_expires = today + timedelta(days=30)
    ent.pi_insurance_expires = today + timedelta(days=14)
    ent.all_risks_insurance_expires = today + timedelta(days=7)
    db.commit()

    ia.run_insurance_alert_sweep()

    mine = [a for a in captured_alerts if a["entity_name"] == "TEST_InsuranceEntity"]
    got = {(a["policy"], a["severity"]) for a in mine}
    assert got == {
        ("EL", "60_day"),
        ("PL", "30_day"),
        ("PI", "14_day"),
        ("All_Risks", "7_day"),
    }


def test_sweep_ignores_struck_off_entities(isolated_tenant, captured_alerts):
    """Struck-off entities are not surveyed."""
    db, _, ent = isolated_tenant
    _set_el_days(db, ent, 30)
    ent.status = "Struck_off"
    db.commit()

    ia.run_insurance_alert_sweep()

    mine = [a for a in captured_alerts if a["entity_name"] == "TEST_InsuranceEntity"]
    assert mine == []


def test_sweep_ignores_null_policies(isolated_tenant, captured_alerts):
    """Entities with no insurance dates set never appear."""
    db, _, ent = isolated_tenant
    # All policies already null from seed
    assert ent.el_insurance_expires is None

    ia.run_insurance_alert_sweep()

    mine = [a for a in captured_alerts if a["entity_name"] == "TEST_InsuranceEntity"]
    assert mine == []
