"""Patch #3 — End-of-Foundation audit remediation regression tests."""
from __future__ import annotations

from sqlalchemy import func, select, text


class TestPatch3Permissions:
    """Items 1-3: six orphan codes must be GONE from the catalogue."""

    def test_orphan_permissions_removed_from_db(self):
        from app.db import SessionLocal
        from app.models.rbac import Permission
        orphans = [
            "cost_codes.create",
            "cost_codes.edit",
            "cost_codes.delete",
            "system_config.edit",
            "notifications.view",
            "notifications.edit",
        ]
        db = SessionLocal()
        try:
            rows = db.scalars(
                select(Permission).where(Permission.code.in_(orphans))
            ).all()
            assert rows == [], (
                f"orphan permissions still present: "
                f"{[r.code for r in rows]}"
            )
        finally:
            db.close()

    def test_orphan_permissions_removed_from_catalogue(self):
        """The source-of-truth PERMISSION_CATALOGUE in seed_rbac.py must
        no longer include the 6 orphan codes — otherwise the next seed
        run would re-create them."""
        from app.seed_rbac import PERMISSION_CATALOGUE
        codes = {row[0] for row in PERMISSION_CATALOGUE}
        assert "cost_codes.create" not in codes
        assert "cost_codes.edit" not in codes
        assert "cost_codes.delete" not in codes
        assert "system_config.edit" not in codes
        assert "notifications.view" not in codes
        assert "notifications.edit" not in codes

    def test_total_permission_count_is_81(self):
        from app.db import SessionLocal
        from app.models.rbac import Permission
        db = SessionLocal()
        try:
            total = db.scalar(select(func.count()).select_from(Permission))
            # Patch #3 baseline was 81. Prompt 2.2 adds two new appraisal
            # permission codes (appraisals.submit + appraisals.view_financials).
            # Prompt 2.4A adds budgets.admin → 84.
            # Prompt 2.5A adds actuals.admin → 85.
            # Prompt 2.5C / mig 0026 adds ai_capture.view_costs (chat-20) → 86.
            # Function name retains "81" — renaming is out of scope (see
            # chat-22 §2 + Future_Tasks polish entry).
            assert total == 86
        finally:
            db.close()


class TestPatch3SER10Retired:
    """Item 4: SER-10 retired, replaced_by_code_id → SER-06."""

    def test_ser10_retired(self):
        from app.db import SessionLocal
        from app.models.cost_codes import CostCode
        db = SessionLocal()
        try:
            ser10 = db.scalar(select(CostCode).where(CostCode.code == "SER-10"))
            ser06 = db.scalar(select(CostCode).where(CostCode.code == "SER-06"))
            assert ser10 is not None
            assert ser06 is not None
            assert ser10.status == "Retired"
            assert ser10.retired_at is not None
            assert ser10.retired_reason is not None
            assert "SER-06" in ser10.retired_reason
            assert ser10.replaced_by_code_id == ser06.id
        finally:
            db.close()

    def test_ser06_still_active(self):
        """Item 4 is a one-sided retire; SER-06 stays the canonical row."""
        from app.db import SessionLocal
        from app.models.cost_codes import CostCode
        db = SessionLocal()
        try:
            ser06 = db.scalar(select(CostCode).where(CostCode.code == "SER-06"))
            assert ser06.status == "Active"
            assert ser06.retired_at is None
            assert ser06.replaced_by_code_id is None
        finally:
            db.close()


class TestPatch3SeedRunEnum:
    """Item 5: audit_action enum now carries 'Seed_Run'."""

    def test_seed_run_in_pg_enum(self):
        from app.db import SessionLocal
        db = SessionLocal()
        try:
            rows = db.execute(text(
                "SELECT enumlabel FROM pg_enum "
                "JOIN pg_type ON pg_enum.enumtypid = pg_type.oid "
                "WHERE pg_type.typname = 'audit_action'"
            )).all()
            labels = {r[0] for r in rows}
            assert "Seed_Run" in labels
        finally:
            db.close()

    def test_seed_run_in_model_tuple(self):
        from app.models.audit import AUDIT_ACTIONS
        assert "Seed_Run" in AUDIT_ACTIONS

    def test_service_layer_accepts_seed_run(self):
        """record_audit(action='Seed_Run', ...) must succeed end-to-end."""
        from uuid import uuid4
        from app.db import SessionLocal
        from app.models.audit import AuditLog
        from app.services.audit import record_audit
        db = SessionLocal()
        try:
            rid = uuid4()
            record_audit(
                db, action="Seed_Run", resource_type="migration",
                resource_id=rid, actor_user_id=None,
                metadata={"kind": "seed_run", "source": "patch3_test"},
            )
            db.commit()
            row = db.scalar(
                select(AuditLog).where(AuditLog.resource_id == rid)
            )
            assert row is not None
            assert row.action == "Seed_Run"
        finally:
            db.close()

    def test_lifespan_seed_emits_seed_run(self):
        """The system_config seed, when inserting rows, emits Seed_Run.
        Rather than re-running the seed (which is idempotent and would
        insert nothing), assert that the initial Patch #3 migration
        summary row carries Seed_Run."""
        from app.db import SessionLocal
        from app.models.audit import AuditLog
        db = SessionLocal()
        try:
            row = db.scalar(
                select(AuditLog)
                .where(AuditLog.action == "Seed_Run")
                .order_by(AuditLog.created_at.desc())
                .limit(1)
            )
            assert row is not None, (
                "no Seed_Run audit rows found — migration 0017 summary "
                "row should carry this action"
            )
        finally:
            db.close()
