"""System config seed — Prompt 1.7.

Source of truth for the 39 seed keys. Idempotent: skips any key already
present. On first boot, called from lifespan AFTER seed_rbac() so that
role IDs exist. On subsequent boots, the no-op fast path triggers.

A dedicated module (rather than an alembic data migration) because the
seed depends on `roles.id` which is itself populated at lifespan time
by `seed_rbac`. Alembic migrations run BEFORE seed_rbac, so a pure-SQL
data migration can't resolve the FK target on first boot.

Records ONE summary audit row per seed-run when rows are inserted.
"""
from __future__ import annotations

import logging
import uuid
from typing import Iterable

from sqlalchemy import select, insert
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models.audit import AuditLog
from app.models.rbac import Role
from app.models.system_config import SystemConfig


log = logging.getLogger("syhomes.seed.system_config")


# (key, value, value_type, category, role_hint, description)
SEEDS: list[tuple[str, str, str, str, str, str]] = [
    # Finance
    ("finance.default_hurdle_on_cost_pct", "20", "Decimal", "Finance",
     "director", "Default minimum profit on cost for go/no-go"),
    ("finance.default_hurdle_on_gdv_pct", "17", "Decimal", "Finance",
     "director", "Default minimum profit on GDV alternative hurdle"),
    ("finance.build_cost_inflation_pct_pa", "3.0", "Decimal", "Finance",
     "director", "Annual build cost inflation for appraisals"),
    # Appraisal
    ("appraisal.default_contingency_pct", "5", "Decimal", "Appraisal",
     "director", "Default contingency percentage in appraisals"),
    ("appraisal.default_architect_fee_pct", "6", "Decimal", "Appraisal",
     "director", "Default architect fee percentage"),
    ("appraisal.default_structural_fee_pct", "1.5", "Decimal", "Appraisal",
     "director", "Default structural engineer fee percentage"),
    ("appraisal.default_qs_fee_pct", "1.0", "Decimal", "Appraisal",
     "director", "Default QS fee percentage"),
    ("appraisal.default_selling_agents_pct", "1.5", "Decimal", "Appraisal",
     "director", "Default selling agent fee percentage"),
    ("appraisal.default_legal_on_sale_pct", "0.25", "Decimal", "Appraisal",
     "director", "Default legal-on-sale fee percentage"),
    ("appraisal.default_prelims_pct", "12", "Decimal", "Appraisal",
     "director", "Default preliminaries percentage"),
    ("appraisal.default_mc_oh_p_pct", "5", "Decimal", "Appraisal",
     "director", "Default main-contractor overhead+profit percentage"),
    # Budget
    ("budget.variance_threshold_amber_pct", "5", "Decimal", "Budget",
     "director", "Amber variance threshold (vs approved budget)"),
    ("budget.variance_threshold_red_pct", "10", "Decimal", "Budget",
     "director", "Red variance threshold (vs approved budget)"),
    ("budget.approval_threshold_pm_gbp", "5000", "Integer", "Budget",
     "director", "PM approval ceiling (GBP) for budget changes"),
    ("budget.approval_threshold_finance_gbp", "25000", "Integer", "Budget",
     "director", "Finance approval ceiling (GBP) for budget changes"),
    ("budget.approval_threshold_director_gbp", "100000", "Integer", "Budget",
     "super_admin", "Director approval ceiling (GBP) for budget changes"),
    # Build Pack 2.4C — Budget Approval Controls (Segregation of Duties).
    # GBP threshold at/above which a budget's creator may NOT activate it
    # (creator != activator required). Stage 1 = single global threshold;
    # Stage 2 (per-role/per-user limits) is on the backlog (B43).
    ("budget.self_approval_threshold_gbp", "10000.00", "Decimal", "Budget",
     "super_admin", "GBP threshold at/above which a budget's creator may not "
     "self-activate (segregation of duties; Stage 1 single global threshold)"),
    # Security
    ("security.session_idle_timeout_minutes", "60", "Integer", "Security",
     "super_admin", "Session idle timeout in minutes"),
    ("security.password_min_length", "12", "Integer", "Security",
     "super_admin", "Minimum password length"),
    ("security.lockout_attempts", "5", "Integer", "Security",
     "super_admin", "Failed-login attempts before lockout"),
    ("security.lockout_duration_minutes", "15", "Integer", "Security",
     "super_admin", "Initial lockout duration in minutes (escalates)"),
    ("security.refresh_token_days", "30", "Integer", "Security",
     "super_admin", "Refresh token lifetime in days"),
    ("security.refresh_token_days_remember_me", "90", "Integer", "Security",
     "super_admin", "Refresh token lifetime when remember-me set"),
    ("security.mfa_required_roles",
     '["super_admin","director","finance"]', "JSON", "Security",
     "super_admin", "Roles requiring MFA enforcement"),
    # Audit
    ("audit.retention_purge_enabled", "false", "Boolean", "Audit",
     "super_admin", "Master gate for audit retention sweep"),
    ("audit.retention_years", "7", "Integer", "Audit",
     "super_admin", "Years to retain audit log (7-year hard floor)"),
    # Integration
    ("xero.sync_interval_minutes", "15", "Integer", "Integration",
     "super_admin", "Xero sync interval in minutes"),
    ("xero.rate_limit_per_minute", "60", "Integer", "Integration",
     "super_admin", "Xero API rate-limit per minute"),
    # Notification
    ("notification.digest_time", "08:00", "String", "Notification",
     "director", "Daily digest send time (deferred feature; key seeded)"),
    ("notification.email_from_address",
     "platform@sy-homes.co.uk", "String", "Notification",
     "super_admin", "From-address for notification emails"),
    ("notification.auto_expire_days", "30", "Integer", "Notification",
     "super_admin", "Default expires_at offset for new notifications (days)"),
    ("notification.group_threshold_count", "3", "Integer", "Notification",
     "super_admin", "Min count to trigger lazy grouping"),
    ("notification.group_window_minutes", "60", "Integer", "Notification",
     "super_admin", "Time window (minutes) for lazy grouping"),
    # Programme
    ("programme.alert_task_starting_lookahead_days", "7", "Integer", "Programme",
     "director", "Lookahead window for task-start alerts (days)"),
    ("programme.alert_milestone_lookahead_days",
     "[30,14,7]", "JSON", "Programme",
     "director", "Milestone lookahead alert thresholds (days)"),
    ("programme.alert_no_update_threshold_days", "14", "Integer", "Programme",
     "director", "Days without an update before alerting"),
    ("programme.alert_duration_overrun_threshold_pct", "110", "Decimal", "Programme",
     "director", "Duration overrun threshold percentage"),
    # Reporting
    ("reporting.weekly_report_day", "Friday", "String", "Reporting",
     "director", "Day of week to send weekly report"),
    ("reporting.weekly_report_time", "17:00", "String", "Reporting",
     "director", "Time of day for weekly report"),
]


def seed_system_config(db: Session | None = None) -> int:
    """Insert any missing seed keys; return count inserted.

    Records ONE summary audit row when count > 0. Safe to call repeatedly.
    """
    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        roles = {r.code: r for r in db.scalars(
            select(Role).where(Role.code.in_(["super_admin", "director"]))
        ).all()}
        if "super_admin" not in roles or "director" not in roles:
            log.info("system_config seed: roles not yet present; skipping")
            return 0

        existing_keys = {
            k for (k,) in db.execute(select(SystemConfig.config_key)).all()
        }
        rows: list[dict] = []
        for (key, value, vtype, category, role_hint, desc) in SEEDS:
            if key in existing_keys:
                continue
            role = roles.get(role_hint, roles["super_admin"])
            rows.append({
                "config_key": key,
                "config_value": value,
                "value_type": vtype,
                "category": category,
                "description": desc,
                "is_system_locked": False,
                "minimum_role_to_edit": role.id,
                "default_value": value,
            })
        if not rows:
            return 0

        db.execute(insert(SystemConfig), rows)

        # Single summary audit row.
        # Patch #3: action='Seed_Run' (was 'Create'). Enum value is
        # added by migration 0017; lifespan-time this runs AFTER all
        # migrations so the value is always present.
        db.add(AuditLog(
            actor_user_id=None,
            action="Seed_Run",
            resource_type="system_config",
            resource_id=uuid.uuid4(),
            field_changes=[],
            metadata_json={
                "kind": "seed_run",
                "keys_inserted": len(rows),
                "total_keys": len(SEEDS),
            },
        ))
        if own_session:
            db.commit()
        else:
            db.flush()
        log.info("system_config seed: inserted %d keys", len(rows))
        return len(rows)
    except Exception:
        if own_session:
            db.rollback()
        raise
    finally:
        if own_session:
            db.close()


def seed_system_config_role_grants(db: Session | None = None) -> int:
    """Grant `system_config.view` to all 10 roles per Prompt 1.7 spec.

    Idempotent. Returns count of grants created. The catalogue itself
    is owned by `seed_rbac.PERMISSION_CATALOGUE`; this function exists
    to ensure every role has the view permission, since prior prompts
    only granted it implicitly via `super_admin → ALL`.

    Also revokes any pre-existing `system_config.{admin,edit}` grants
    held by non-super_admin roles. Prior prompts seeded those grants
    via the catch-all `director → ALL_PERMISSION_CODES - {…}` set;
    Prompt 1.7 narrows the exclusion to confine admin/edit to
    super_admin only.
    """
    from sqlalchemy import delete
    from app.models.rbac import Permission, Role, role_permissions

    own_session = db is None
    if own_session:
        db = SessionLocal()
    try:
        view_perm = db.scalar(
            select(Permission).where(Permission.code == "system_config.view")
        )
        if view_perm is None:
            return 0
        roles = db.scalars(select(Role)).all()
        existing_pairs = set(
            db.execute(
                select(role_permissions.c.role_id, role_permissions.c.permission_id)
                .where(role_permissions.c.permission_id == view_perm.id)
            ).all()
        )
        granted = 0
        for r in roles:
            if (r.id, view_perm.id) in existing_pairs:
                continue
            db.execute(insert(role_permissions).values(
                role_id=r.id, permission_id=view_perm.id,
            ))
            granted += 1

        # Revoke system_config.{admin,edit} from any non-super_admin role
        # (one-shot cleanup; idempotent).
        super_admin = db.scalar(select(Role).where(Role.code == "super_admin"))
        for code in ("system_config.admin", "system_config.edit"):
            perm = db.scalar(select(Permission).where(Permission.code == code))
            if perm is None or super_admin is None:
                continue
            db.execute(
                delete(role_permissions).where(
                    role_permissions.c.permission_id == perm.id,
                    role_permissions.c.role_id != super_admin.id,
                )
            )

        if own_session:
            db.commit()
        else:
            db.flush()
        return granted
    except Exception:
        if own_session:
            db.rollback()
        raise
    finally:
        if own_session:
            db.close()
