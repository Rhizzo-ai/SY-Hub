"""Patch #3 — End-of-Foundation audit remediation regression tests."""
from __future__ import annotations

from sqlalchemy import func, select, text


class TestPatch3Permissions:
    """Items 1-3: orphan codes must be GONE from the catalogue.

    B88 Pack 1 (Gate 2) RE-INTRODUCES cost_codes.{create,edit,delete}
    as wired permission codes routing the new section CRUD + code
    delete + reactivate endpoints. Those three codes are removed from
    this "must-be-absent" list; the remaining 3 (system_config.edit +
    notifications.{view,edit}) stay as live orphan guards.
    """

    def test_orphan_permissions_removed_from_db(self):
        from app.db import SessionLocal
        from app.models.rbac import Permission
        orphans = [
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
        no longer include the orphan codes — otherwise the next seed
        run would re-create them.

        B88 Pack 1 (Gate 2): cost_codes.{create,edit,delete} are NOT
        orphans anymore — they route real endpoints. Only the 3 below
        remain on the "must-be-absent" list.
        """
        from app.seed_rbac import PERMISSION_CATALOGUE
        codes = {row[0] for row in PERMISSION_CATALOGUE}
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
            # Chat 24 R1 adds suppliers.{view,view_sensitive,create,edit,
            #   archive} (+5) → 91.
            # Chat 24 R2 adds pos.{view,view_sensitive,create,edit,
            #   edit_issued,delete,submit,issue,void,close,receipt} (+11)
            #   → 102? Spec ships pos.* incrementally: R2 lays the 10
            #   action codes excluding approve; receipt placeholder lands
            #   in R2 too → 101. R3 adds pos.approve → 102.
            # Chat 32 / mig 0035 adds cis.* (+3) and supplier_documents.* (+5)
            #   → 110.
            # Chat 33 / mig 0036 adds budget_changes.submit + .apply (+2)
            #   → 112.
            # Chat 34 / mig 0037 (Prompt 2.8a) adds subcontracts.* +5
            #   and subcontract_variations.* +5 → 122.
            # Chat 35 / mig 0038 (Prompt 2.8b) adds
            #   subcontract_valuations.* +4 and payment_notices.* +3 → 129.
            # Chat 41 / mig 0040 (Prompt 2.7-BE-rev-A) adds trades.view
            #   + trades.create (+2) → 131.
            # Chat 41 operator eyeball (Prompt 2.7-FE-revision) adds
            #   suppliers.delete (+1) → 132.
            # Function name retains "81" — renaming is out of scope (see
            # chat-22 §2 + Future_Tasks polish entry).
            # B88 Pack 1 (Gate 2): +3 (cost_codes.{create,edit,delete}) → 136.
            assert total == 136
        finally:
            db.close()


class TestPatch3SER10Retired:
    """Item 4 (historical): SER-10 was retired, replaced by SER-06.

    B88 Pack 1 — Gate 4 (corrected canonical master 2026-06-09):
    SER-10 is RE-INSTATED as 'Lift installation (passenger, platform,
    stairlift)' under subgroup 4.05 Services. SER-06 is the canonical
    'Renewables & EV (solar PV, battery, ASHP, EV charger)'. Both are
    distinct, active rows in the master file — the retire/replace
    relationship no longer applies. This test was inverted to assert
    the post-Gate-4 truth.
    """

    def test_ser10_active_in_corrected_master(self):
        from app.db import SessionLocal
        from app.models.cost_codes import CostCode
        db = SessionLocal()
        try:
            ser10 = db.scalar(select(CostCode).where(CostCode.code == "SER-10"))
            assert ser10 is not None
            assert ser10.status == "Active", ser10.status
            assert ser10.replaced_by_code_id is None
            assert ser10.name == "Lift installation (passenger, platform, stairlift)"
        finally:
            db.close()

    def test_ser06_still_active(self):
        """SER-06 stays Active under the corrected master with the
        canonical name 'Renewables & EV (solar PV, battery, ASHP, EV
        charger)' (previously 'Lifts & access' on this pod)."""
        from app.db import SessionLocal
        from app.models.cost_codes import CostCode
        db = SessionLocal()
        try:
            ser06 = db.scalar(select(CostCode).where(CostCode.code == "SER-06"))
            assert ser06.status == "Active"
            assert ser06.retired_at is None
            assert ser06.replaced_by_code_id is None
            assert ser06.name == "Renewables & EV (solar PV, battery, ASHP, EV charger)"
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
