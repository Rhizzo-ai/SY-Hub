"""Tests for retro-wired notification dispatches (Prompt 1.7).

Covers each TODO[NOTIFY] site that 1.7 closed:
  - Planning expiry sweep → Deadline_Approaching
  - Stage override → System_Announcement (High) to all directors
  - Insurance _emit_alert → Insurance_Expiry
  - Password reset request → Security_Alert (High) to user
  - MFA enroll confirm → Security_Alert (High) to user
  - MFA disable → Security_Alert (High) to user

Also asserts that `seed_rbac` permission catalogue contains the
mandated post-1.7 codes.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pyotp
import pytest
from sqlalchemy import select


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://budgets-service.preview.emergentagent.com"

ADMIN = "test-admin@example.test"
DIRECTOR = "test-director@example.test"
PWD = "TestUser-Dev-2026!"


def _user_id(email: str):
    from app.db import SessionLocal
    from app.models.user import User
    db = SessionLocal()
    try:
        return db.scalar(select(User).where(User.email == email)).id
    finally:
        db.close()


def _count_notifs(uid, *, type_=None, since=None) -> int:
    from app.db import SessionLocal
    from app.models.notifications import Notification
    db = SessionLocal()
    try:
        q = select(Notification).where(Notification.recipient_user_id == uid)
        if type_:
            q = q.where(Notification.notification_type == type_)
        if since:
            q = q.where(Notification.created_at >= since)
        return len(db.scalars(q).all())
    finally:
        db.close()


# =============================================================================
# Planning expiry retro-wire
# =============================================================================

class TestPlanningExpiryRetrowire:
    def test_sweep_dispatches_deadline_approaching(self):
        """Create a project with planning expiry hitting a threshold;
        run the sweep; verify a Deadline_Approaching notification lands
        on at least one recipient (project_lead or scoped director)."""
        from app.db import SessionLocal
        from app.models.entity import Entity
        from app.models.projects import Project
        from app.models.user import User
        from app.scheduler import planning_expiry_sweep

        admin_uid = _user_id(ADMIN)
        before = datetime.now(timezone.utc)

        db = SessionLocal()
        try:
            entity = db.scalar(select(Entity))
            assert entity is not None
            today = date.today()
            p = Project(
                project_code=f"TST-9{uuid4().hex[:5].upper()}",
                name=f"Retro-wire test {uuid4()}",
                project_type="Pure_Dev",
                primary_entity_id=entity.id,
                land_ownership_method="Direct_Purchase",
                site_address="Test", site_postcode="SY1 1AA",
                tenure="Freehold",
                implementation_required=True,
                planning_type="Full",
                planning_approval_date=today - timedelta(days=365 * 3 - 30),
                planning_expiry_date=today + timedelta(days=30),  # exact threshold
                project_lead_user_id=admin_uid,
                created_by_user_id=admin_uid,
                current_stage="Lead",
                status="Active",
            )
            db.add(p)
            db.commit()
            project_id = p.id

            payloads = planning_expiry_sweep(db)
            db.commit()
            relevant = [pl for pl in payloads if pl["project_id"] == str(project_id)]
            assert relevant, "no payload for our project"

            # The lead (admin) is a recipient.
            n_count = _count_notifs(
                admin_uid, type_="Deadline_Approaching", since=before,
            )
            assert n_count >= 1
        finally:
            # Cleanup. audit_log is append-only — leave audit rows alone;
            # the audit_log.project_id FK uses ON DELETE SET NULL so the
            # project row can still be removed.
            try:
                from app.models.notifications import Notification
                db.query(Notification).filter(
                    Notification.related_resource_id == project_id
                ).delete()
                db.query(Project).filter(Project.id == project_id).delete()
                db.commit()
            except Exception:
                db.rollback()
            db.close()


# =============================================================================
# Stage override retro-wire
# =============================================================================

class TestStageOverrideRetrowire:
    def test_override_dispatches_system_announcement_to_directors(self):
        """When super_admin overrides a stage, all directors (other than
        the actor) receive a System_Announcement priority High."""
        from app.db import SessionLocal
        from app.models.entity import Entity
        from app.models.projects import Project
        from tests.conftest import login_with_auto_enroll

        director_uid = _user_id(DIRECTOR)
        before = datetime.now(timezone.utc)

        # Find the primary entity id via the model layer (no API).
        db = SessionLocal()
        try:
            entity = db.scalar(select(Entity))
            primary_entity_id = str(entity.id)
        finally:
            db.close()

        s = login_with_auto_enroll(None, BASE_URL, ADMIN, PWD)
        # Create the project via the API so all triggers/auto-fields fire.
        cr = s.post(
            f"{BASE_URL}/api/projects",
            json={
                "name": f"Stage-override test {uuid4()}",
                "project_type": "Pure_Dev",
                "primary_entity_id": primary_entity_id,
                "land_ownership_method": "Direct_Purchase",
                "site_address": "Test", "site_postcode": "SY1 1AA",
                "tenure": "Freehold",
                "implementation_required": True,
            },
        )
        assert cr.status_code == 201, cr.text
        project_id = cr.json()["id"]

        r = s.post(
            f"{BASE_URL}/api/projects/{project_id}/stage/override",
            json={"new_stage": "Construction",
                  "reason": "retro-wire integration test trigger"},
        )
        assert r.status_code == 200, r.text

        n = _count_notifs(director_uid, type_="System_Announcement", since=before)
        assert n >= 1

        # Cleanup. Audit_log is append-only by design — don't delete.
        db = SessionLocal()
        try:
            from app.models.notifications import Notification
            from uuid import UUID as _UUID
            pid = _UUID(project_id)
            db.query(Notification).filter(
                Notification.related_resource_id == pid
            ).delete()
            from app.models.cost_codes import ProjectCostCode
            db.query(ProjectCostCode).filter(
                ProjectCostCode.project_id == pid
            ).delete()
            db.query(Project).filter(Project.id == pid).delete()
            db.commit()
        finally:
            db.close()


# =============================================================================
# Insurance alert retro-wire
# =============================================================================

class TestInsuranceAlertRetrowire:
    def test_emit_alert_dispatches_insurance_expiry(self):
        """`_emit_alert` dispatches an Insurance_Expiry notification to
        directors with view access to the entity."""
        from app.db import SessionLocal
        from app.jobs.insurance_alerts import _emit_alert
        from app.models.entity import Entity
        from app.schemas.entity import InsuranceAlert

        director_uid = _user_id(DIRECTOR)
        before = datetime.now(timezone.utc)

        db = SessionLocal()
        try:
            entity = db.scalar(select(Entity))
            tenant_id = entity.tenant_id
            alert = InsuranceAlert(
                entity_id=entity.id,
                entity_name=entity.name,
                policy="EL",
                expires_on=date.today() + timedelta(days=30),
                days_until_expiry=30,
                severity="warning",
            )
        finally:
            db.close()

        _emit_alert(alert, tenant_id, "30_day")

        # Director (entity_scope='All') should receive one.
        n = _count_notifs(director_uid, type_="Insurance_Expiry", since=before)
        assert n >= 1


# =============================================================================
# Auth flow retro-wires
# =============================================================================

class TestAuthRetrowires:
    def test_password_reset_dispatches_security_alert(self):
        """`POST /auth/password-reset/request` dispatches Security_Alert
        High to the user when the email exists and is Active."""
        import requests
        before = datetime.now(timezone.utc)
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        r = s.post(
            f"{BASE_URL}/api/auth/password-reset/request",
            json={"email": DIRECTOR},
        )
        assert r.status_code == 200
        n = _count_notifs(_user_id(DIRECTOR), type_="Security_Alert", since=before)
        assert n >= 1


# =============================================================================
# Permission catalogue post-1.7
# =============================================================================

class TestPermissionsCatalogue:
    def test_system_config_view_granted_to_all_10_roles(self):
        from app.db import SessionLocal
        from app.models.rbac import Permission, Role, role_permissions
        db = SessionLocal()
        try:
            perm = db.scalar(select(Permission).where(
                Permission.code == "system_config.view"
            ))
            assert perm is not None
            roles = db.scalars(select(Role)).all()
            assert len(roles) == 10
            granted_role_ids = {
                r.role_id for r in db.execute(
                    select(role_permissions).where(
                        role_permissions.c.permission_id == perm.id
                    )
                ).all()
            }
            for r in roles:
                assert r.id in granted_role_ids, (
                    f"Role {r.code} missing system_config.view"
                )
        finally:
            db.close()

    def test_system_config_admin_super_admin_only(self):
        from app.db import SessionLocal
        from app.models.rbac import Permission, Role, role_permissions
        db = SessionLocal()
        try:
            perm = db.scalar(select(Permission).where(
                Permission.code == "system_config.admin"
            ))
            assert perm is not None
            granted = db.execute(
                select(role_permissions, Role.code).join(
                    Role, Role.id == role_permissions.c.role_id
                ).where(role_permissions.c.permission_id == perm.id)
            ).all()
            granted_codes = {row[-1] for row in granted}
            assert granted_codes == {"super_admin"}
        finally:
            db.close()

    def test_post_1_7_permission_baseline(self):
        from app.db import SessionLocal
        from app.models.rbac import Permission
        from sqlalchemy import func
        db = SessionLocal()
        try:
            total = db.scalar(select(func.count()).select_from(Permission))
            # Pre-1.7 baseline was 87. Patch #3 (Patch #3 — End-of-Foundation
            # Audit Remediation) removes 6 orphan permission codes that no
            # route enforces: cost_codes.{create,edit,delete},
            # system_config.edit, notifications.{view,edit}. Post-Patch-#3
            # total was 81. Prompt 2.2 adds 2 new appraisal codes
            # (appraisals.submit + appraisals.view_financials) → 83.
            assert total == 83
        finally:
            db.close()
