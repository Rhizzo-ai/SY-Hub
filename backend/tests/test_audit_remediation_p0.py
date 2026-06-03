"""Audit-remediation P0 acceptance tests — SY_Hub_Audit_Remediation_P0_BuildPack_v2.

Four critical findings, one test class each. These tests print the
literal evidence required by the build pack's SELF-REPORT section
(audit-row contents, 401/403 + 200 status codes, 429 + 200 status
codes) — assertions alone don't satisfy the gate, so the prints are
left in even on green runs.
"""
from __future__ import annotations

import importlib
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import jwt
import pyotp
import pytest
import requests
import sqlalchemy as sa
from dotenv import load_dotenv

from pathlib import Path
_REPO_ROOT = Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"

load_dotenv(str(_BACKEND / ".env"))

BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "https://bcr-fix-backend.preview.emergentagent.com"
)
DATABASE_URL = os.environ["DATABASE_URL"]
JWT_SECRET = os.environ["JWT_SECRET"]

TEST_PASSWORD = "TestUser-Dev-2026!"
PM = "test-pm@example.test"
ADMIN = "test-admin@example.test"
DIRECTOR = "test-director@example.test"
READONLY = "test-readonly@example.test"


@pytest.fixture(scope="module")
def db_engine():
    eng = sa.create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


def _new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _reset_user_mfa(db_engine, email: str) -> None:
    with db_engine.begin() as conn:
        conn.execute(sa.text(
            "UPDATE users SET mfa_enabled=false, mfa_method=NULL, "
            "mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL, "
            "mfa_enrolled_at=NULL, failed_login_attempts=0, "
            "locked_until=NULL, lockout_level=0 WHERE email=:e"
        ), {"e": email})


def _user_id_for(db_engine, email: str) -> uuid.UUID:
    with db_engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT id FROM users WHERE email=:e"
        ), {"e": email}).first()
        assert row, f"User {email} not seeded"
        return row[0]


def _user_id_and_tenant(db_engine, email: str):
    with db_engine.connect() as conn:
        row = conn.execute(sa.text(
            "SELECT id, tenant_id FROM users WHERE email=:e"
        ), {"e": email}).first()
        assert row, f"User {email} not seeded"
        return row[0], row[1]


def _mint_access_token(user_id, tenant_id, email):
    """Mint a session-shaped access token bypassing the MFA dance. Used
    only inside tests for routes that need an authenticated principal.
    """
    payload = {
        "sub": str(user_id), "email": email, "tenant_id": str(tenant_id),
        "iat": int(time.time()), "exp": int(time.time()) + 3600,
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _mint_mfa_pending_token(user_id, email, tenant_id):
    """Replicates the mfa_pending token shape (`type: mfa_pending`)
    issued at auth.py:406, with the same 15-minute lifetime.
    """
    payload = {
        "sub": str(user_id), "email": email, "tenant_id": str(tenant_id),
        "iat": int(time.time()), "exp": int(time.time()) + 900,
        "type": "mfa_pending",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def _mint_mfa_challenge_token(user_id, email, tenant_id):
    """Replicates the mfa_challenge token shape issued at auth.py:395.
    """
    payload = {
        "sub": str(user_id), "email": email, "tenant_id": str(tenant_id),
        "iat": int(time.time()), "exp": int(time.time()) + 300,
        "type": "mfa_challenge",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


# ======================================================================
# P0.1 — Appraisal recompute lock helper
# ======================================================================

class TestP0_1_AppraisalLockHelper:
    """The lock helper must be called for every mutating appraisal
    handler. The grep evidence + a concurrency proof together satisfy
    AC1.
    """

    def test_lock_present_at_all_13_recompute_sites(self):
        """Every `appraisal_calc.recompute(db, a)` line in the router
        is immediately preceded (after any blank lines) by a call to
        `_lock_appraisal_for_update`. The build pack lists 13 sites;
        we assert >=13 to allow Batch-2 sites to add more.
        """
        path = str(_BACKEND / "app" / "routers" / "appraisals.py")
        with open(path) as f:
            lines = f.readlines()
        recompute_idxs = [
            i for i, line in enumerate(lines)
            if line.lstrip() == "appraisal_calc.recompute(db, a)\n"
        ]
        print(f"\nP0.1 — found {len(recompute_idxs)} recompute call sites")
        assert len(recompute_idxs) == 13, (
            f"expected 13 recompute sites per build pack; found {len(recompute_idxs)}"
        )
        for idx in recompute_idxs:
            # Walk backwards over blank lines to find the preceding statement.
            j = idx - 1
            while j >= 0 and lines[j].strip() == "":
                j -= 1
            assert "_lock_appraisal_for_update" in lines[j], (
                f"line {idx + 1}: recompute call is NOT preceded by lock "
                f"helper; preceding line is {lines[j]!r}"
            )

    def test_concurrent_select_for_update_serialises(self, db_engine):
        """Direct two-session concurrency proof. Session A takes
        `SELECT ... FOR UPDATE` on the appraisal via the helper, holds
        the transaction open. Session B tries the same with `NOWAIT` —
        it must raise OperationalError because the row is locked. After
        A commits, B succeeds.

        This is the build pack's "no torn write" guarantee in its purest
        form: two appraisal mutators cannot simultaneously hold the row
        for the duration of the recompute pipeline.
        """
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy import select as sa_select
        from sqlalchemy.exc import OperationalError, DBAPIError

        # Seed: directly insert the minimal project + appraisal we need.
        with db_engine.begin() as conn:
            admin = conn.execute(sa.text("""
                SELECT u.id FROM users u
                JOIN user_roles ur ON ur.user_id = u.id AND ur.status = 'Active'
                JOIN roles r ON r.id = ur.role_id
                WHERE r.code = 'super_admin'
                ORDER BY u.created_at LIMIT 1
            """)).scalar()
            entity = conn.execute(sa.text(
                "SELECT id FROM entities ORDER BY created_at LIMIT 1"
            )).scalar()
            assert admin and entity, "missing bootstrap user / entity"

            proj_id = uuid.uuid4()
            conn.execute(sa.text("""
                INSERT INTO projects
                  (id, project_code, name, project_type, primary_entity_id,
                   land_ownership_method, site_address, site_postcode,
                   created_by_user_id, current_stage)
                VALUES (:id, :code, :name, 'Pure_Dev', :ent,
                        'Direct_Purchase', '1 Test St', 'AB1 2CD', :uid, 'Lead')
            """), {
                "id": str(proj_id),
                "code": f"P0-{uuid.uuid4().hex[:6].upper()}",
                "name": "P0.1 concurrent lock test",
                "ent": str(entity),
                "uid": str(admin),
            })

            group_id = uuid.uuid4()  # not a real FK on this schema —
            # appraisal_group_id is just a UUID column, no separate
            # group table. Use any UUID.

            appraisal_id = uuid.uuid4()
            conn.execute(sa.text("""
                INSERT INTO appraisals
                  (id, project_id, name, reference_date,
                   created_by_user_id, appraisal_group_id, version_number)
                VALUES (:id, :pid, 'P0.1 appraisal', current_date,
                        :uid, :gid, 1)
            """), {
                "id": str(appraisal_id),
                "pid": str(proj_id),
                "uid": str(admin),
                "gid": str(group_id),
            })

        from app.routers.appraisals import _lock_appraisal_for_update
        from app.models.appraisals import Appraisal as AppraisalModel

        SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
        a_sess = SessionLocal()
        b_sess = SessionLocal()
        try:
            # Session A locks the row but does NOT commit.
            _lock_appraisal_for_update(a_sess, appraisal_id)

            # Session B tries to acquire the same lock with NOWAIT —
            # must raise.
            b_err = None
            try:
                b_sess.execute(
                    sa_select(AppraisalModel.id)
                    .where(AppraisalModel.id == appraisal_id)
                    .with_for_update(nowait=True)
                ).all()
            except (OperationalError, DBAPIError) as exc:
                b_err = exc
            b_sess.rollback()
            print(f"\nP0.1 — concurrent NOWAIT lock attempt by Session B "
                  f"while A holds: raised {type(b_err).__name__ if b_err else None}")
            assert b_err is not None, (
                "Session B's NOWAIT acquire should have raised "
                "OperationalError — but it succeeded. The lock helper "
                "is not actually taking a row lock."
            )

            # Now A commits, and B can proceed.
            a_sess.commit()
            b_rows = b_sess.execute(
                sa_select(AppraisalModel.id)
                .where(AppraisalModel.id == appraisal_id)
                .with_for_update(nowait=True)
            ).all()
            b_sess.commit()
            assert len(b_rows) == 1, "Session B failed to acquire after A committed"
            print(f"P0.1 — after A commits, B acquires cleanly: {b_rows[0][0]}")
        finally:
            try:
                a_sess.close()
            except Exception:
                pass
            try:
                b_sess.close()
            except Exception:
                pass
            # Cleanup our seeded rows so subsequent fixtures can wipe
            # projects without FK violations.
            with db_engine.begin() as conn:
                conn.execute(sa.text("DELETE FROM appraisals WHERE id=:id"),
                             {"id": str(appraisal_id)})
                conn.execute(sa.text("DELETE FROM projects WHERE id=:id"),
                             {"id": str(proj_id)})


# ======================================================================
# P0.2 — PO receipt audit-actor + all-lines lock
# ======================================================================

class TestP0_2_ReceiptAuditActor:
    """`_recompute_po_status_after_receipt_change` must record the
    receipting user as `actor_user_id`, not the PO header's last
    editor. All PO lines must be locked for the all-fully-received
    check.
    """

    def test_helper_signature_takes_keyword_actor(self):
        """The signature change forces every caller to pass actor_user_id
        explicitly. A positional call (the old shape) is a static error.
        """
        from app.services import po_receipts
        import inspect
        sig = inspect.signature(po_receipts._recompute_po_status_after_receipt_change)
        params = sig.parameters
        print(f"\nP0.2 — helper signature: {sig}")
        assert "actor_user_id" in params
        assert params["actor_user_id"].kind == inspect.Parameter.KEYWORD_ONLY

    def test_audit_row_actor_is_receipting_user(self, db_engine):
        """LIVE evidence — issue an approved PO as the admin (header
        editor), then fire a receipt as test-pm. Read the audit row
        and assert actor_user_id is test-pm's id, not the PO header's
        last editor.
        """
        # Find an APPROVED PO whose header editor isn't test-pm. We
        # ISSUE it first (admin) so it's eligible for receipting (only
        # issued / partially_receipted accept receipts per
        # po_receipts.ELIGIBLE_RECEIPT_STATUSES) — this also bumps the
        # header_editor to the admin, baking in the bug-shaped data
        # the test needs.
        admin_id, admin_tenant = _user_id_and_tenant(db_engine, ADMIN)
        admin_tok = _mint_access_token(admin_id, admin_tenant, ADMIN)
        admin_s = _new_session()
        admin_s.cookies.set("access_token", admin_tok)

        pm_id, pm_tenant = _user_id_and_tenant(db_engine, PM)

        # Self-bootstrap an issued PO if none exists in the DB. The
        # P0.2 audit-actor test is a financial-integrity proof — it
        # must NEVER silently skip just because the spot-check seed
        # isn't loaded. We insert the minimal chain (project →
        # supplier → budget → PO → line → number-prefix) directly via
        # SQL, then go through the lifecycle API as admin to land at
        # 'issued', which bakes admin in as the header editor (the
        # bug-shape this test exercises).
        with db_engine.connect() as conn:
            row = conn.execute(sa.text("""
                SELECT po.id, po.po_number, po.status
                FROM purchase_orders po
                WHERE po.status IN ('approved', 'issued', 'partially_receipted')
                ORDER BY (po.status = 'approved') DESC
                LIMIT 1
            """)).first()

        cleanup_ids = {}
        if row is None:
            # Bootstrap the full chain from scratch. The financial-integrity
            # proof must NEVER silently skip — and the full pytest suite
            # clears projects/budgets/lines so we can't assume seed data.
            with db_engine.connect() as conn:
                ent_row = conn.execute(sa.text(
                    "SELECT id, tenant_id FROM entities ORDER BY created_at LIMIT 1"
                )).first()
                assert ent_row, "no entities seeded — cannot bootstrap"
                entity_id, tenant_id_for_po = ent_row[0], ent_row[1]

                cc_row = conn.execute(sa.text(
                    "SELECT id, code FROM cost_codes ORDER BY code LIMIT 1"
                )).first()
                assert cc_row, "no cost_codes seeded"
                cost_code_id, cost_code_str = cc_row[0], cc_row[1]

            cleanup_ids["project_id"] = uuid.uuid4()
            cleanup_ids["appraisal_id"] = uuid.uuid4()
            cleanup_ids["supplier_id"] = uuid.uuid4()
            cleanup_ids["budget_id"] = uuid.uuid4()
            cleanup_ids["budget_line_id"] = uuid.uuid4()
            cleanup_ids["po_id"] = uuid.uuid4()
            cleanup_ids["po_line_id"] = uuid.uuid4()
            cleanup_ids["prefix_id"] = uuid.uuid4()
            cleanup_ids["bootstrapped_project"] = True

            with db_engine.begin() as conn:
                conn.execute(sa.text("""
                    INSERT INTO projects
                      (id, project_code, name, project_type, primary_entity_id,
                       land_ownership_method, site_address, site_postcode,
                       created_by_user_id, current_stage)
                    VALUES (:id, :code, 'P0.2 receipt-actor test PO',
                            'Pure_Dev', :ent, 'Direct_Purchase',
                            '1 Test Receipts', 'AB1 2CD', :uid, 'Lead')
                """), {
                    "id": str(cleanup_ids["project_id"]),
                    "code": f"P0-{uuid.uuid4().hex[:6].upper()}",
                    "ent": str(entity_id),
                    "uid": str(admin_id),
                })

                conn.execute(sa.text("""
                    INSERT INTO appraisals
                      (id, project_id, name, reference_date,
                       created_by_user_id, appraisal_group_id, version_number)
                    VALUES (:id, :pid, 'P0.2 appraisal', current_date,
                            :uid, :gid, 1)
                """), {
                    "id": str(cleanup_ids["appraisal_id"]),
                    "pid": str(cleanup_ids["project_id"]),
                    "uid": str(admin_id),
                    "gid": str(uuid.uuid4()),
                })

                conn.execute(sa.text("""
                    INSERT INTO budgets
                      (id, project_id, source_appraisal_id, status,
                       is_current, total_budget, created_by_user_id)
                    VALUES (:id, :pid, :aid, 'Active', true,
                            100000, :uid)
                """), {
                    "id": str(cleanup_ids["budget_id"]),
                    "pid": str(cleanup_ids["project_id"]),
                    "aid": str(cleanup_ids["appraisal_id"]),
                    "uid": str(admin_id),
                })

                conn.execute(sa.text("""
                    INSERT INTO budget_lines
                      (id, budget_id, cost_code_id, line_description,
                       entity_id,
                       original_budget, current_budget, display_order)
                    VALUES (:id, :bid, :cc, 'P0.2 test line',
                            :ent,
                            10000, 10000, 1)
                """), {
                    "id": str(cleanup_ids["budget_line_id"]),
                    "bid": str(cleanup_ids["budget_id"]),
                    "cc": str(cost_code_id),
                    "ent": str(entity_id),
                })

                conn.execute(sa.text("""
                    INSERT INTO suppliers
                      (id, tenant_id, name, default_vat_rate, is_archived,
                       created_by, updated_by)
                    VALUES (:id, :tid, :name, 20.0, false, :uid, :uid)
                """), {
                    "id": str(cleanup_ids["supplier_id"]),
                    "tid": str(tenant_id_for_po),
                    "name": f"P0.2 supplier {uuid.uuid4().hex[:6]}",
                    "uid": str(admin_id),
                })

                conn.execute(sa.text("""
                    INSERT INTO project_number_prefixes
                      (id, project_id, entity_type, middle_prefix,
                       description, is_default, is_archived,
                       next_sequence, created_by, updated_by)
                    VALUES (:id, :pid, 'po', :mid,
                            'P0.2 test prefix', false, false, 1,
                            :uid, :uid)
                """), {
                    "id": str(cleanup_ids["prefix_id"]),
                    "pid": str(cleanup_ids["project_id"]),
                    "mid": f"P{uuid.uuid4().hex[:4].upper()}",
                    "uid": str(admin_id),
                })

                unique_pono = f"PO-TEST-{uuid.uuid4().hex[:6].upper()}"
                conn.execute(sa.text("""
                    INSERT INTO purchase_orders
                      (id, tenant_id, project_id, supplier_id, budget_id,
                       po_number, status, approval_required,
                       subtotal_amount, vat_amount, total_amount,
                       submitted_by, submitted_at,
                       created_by, updated_by, issued_at, issued_by)
                    VALUES (:id, :tid, :pid, :sid, :bid,
                            :pono, 'issued', false,
                            1000, 200, 1200,
                            :uid, now(),
                            :uid, :uid, now(), :uid)
                """), {
                    "id": str(cleanup_ids["po_id"]),
                    "tid": str(tenant_id_for_po),
                    "pid": str(cleanup_ids["project_id"]),
                    "sid": str(cleanup_ids["supplier_id"]),
                    "bid": str(cleanup_ids["budget_id"]),
                    "pono": unique_pono,
                    "uid": str(admin_id),
                })

                conn.execute(sa.text("""
                    INSERT INTO purchase_order_lines
                      (id, purchase_order_id, line_number,
                       budget_line_id, cost_code, description,
                       quantity, unit_rate, vat_rate,
                       net_amount, vat_amount, gross_amount,
                       receipted_quantity,
                       created_by, updated_by)
                    VALUES (:id, :poid, 1,
                            :blid, :cc, 'P0.2 test line',
                            10, 100, 20,
                            1000, 200, 1200,
                            0,
                            :uid, :uid)
                """), {
                    "id": str(cleanup_ids["po_line_id"]),
                    "poid": str(cleanup_ids["po_id"]),
                    "blid": str(cleanup_ids["budget_line_id"]),
                    "cc": cost_code_str,
                    "uid": str(admin_id),
                })

            po_id = cleanup_ids["po_id"]
            po_number = unique_pono
            po_status = "issued"
        else:
            po_id, po_number, po_status = row[0], row[1], row[2]

        try:
            # If approved, issue it as admin so admin becomes header editor.
            if po_status == "approved":
                r = admin_s.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/issue", json={})
                assert r.status_code in (200, 204), (
                    f"PO issue failed ({r.status_code} {r.text[:200]})"
                )
            else:
                # Force admin to be the header editor by touching the PO.
                with db_engine.begin() as conn:
                    conn.execute(sa.text(
                        "UPDATE purchase_orders SET updated_by = :uid WHERE id = :p"
                    ), {"uid": admin_id, "p": str(po_id)})

            # Re-read header_editor — must be the admin now.
            with db_engine.connect() as conn:
                header_editor_id = conn.execute(sa.text(
                    "SELECT updated_by FROM purchase_orders WHERE id=:p"
                ), {"p": str(po_id)}).scalar()
            assert header_editor_id != pm_id, (
                "Header editor IS the receipter — bug-shape unreproducible"
            )

            # Mint receipter (test-pm) session.
            tok = _mint_access_token(pm_id, pm_tenant, PM)
            s = _new_session()
            s.cookies.set("access_token", tok)

            # Get PO lines to size the receipt.
            r = s.get(f"{BASE_URL}/api/v1/purchase-orders/{po_id}")
            assert r.status_code == 200, r.text
            po_detail = r.json()
            first_line = (po_detail.get("lines") or [None])[0]
            assert first_line is not None, "PO has no lines"

            # POST a 1-unit partial receipt as test-pm.
            receipt_payload = {
                "received_date": datetime.now(timezone.utc).date().isoformat(),
                "delivery_note_reference": f"P0.2-{uuid.uuid4().hex[:8]}",
                "lines": [{
                    "po_line_id": first_line["id"],
                    "quantity_received": 1,
                }],
            }
            r = s.post(
                f"{BASE_URL}/api/v1/purchase-orders/{po_id}/receipts",
                json=receipt_payload,
            )
            assert r.status_code in (200, 201), (
                f"receipt post failed ({r.status_code} {r.text[:200]})"
            )

            # Read the most-recent Status_Change audit row on this PO.
            with db_engine.connect() as conn:
                audit = conn.execute(sa.text("""
                    SELECT actor_user_id, action, resource_type, resource_id,
                           project_id, metadata_json, created_at
                    FROM audit_log
                    WHERE resource_type = 'purchase_order'
                      AND resource_id = :po_id
                      AND action = 'Status_Change'
                      AND (metadata_json->>'reason' = 'receipt_change'
                           OR metadata_json IS NULL)
                    ORDER BY created_at DESC
                    LIMIT 1
                """), {"po_id": str(po_id)}).first()

            # Literal evidence dump.
            print(f"\nP0.2 — Status_Change audit row on PO {po_number}:")
            assert audit is not None, (
                "Expected a receipt-driven Status_Change audit row after a "
                "1-unit partial receipt on an issued PO"
            )
            print(f"  actor_user_id  : {audit[0]}")
            print(f"  action         : {audit[1]}")
            print(f"  resource_type  : {audit[2]}")
            print(f"  resource_id    : {audit[3]}")
            print(f"  project_id     : {audit[4]}")
            print(f"  metadata       : {audit[5]}")
            print(f"  created_at     : {audit[6]}")
            print(f"  receipter id   : {pm_id}")
            print(f"  header editor  : {header_editor_id}")
            assert audit[0] == pm_id, (
                f"actor_user_id must equal receipter ({pm_id}); "
                f"got {audit[0]} (header editor was {header_editor_id})"
            )
        finally:
            # Tear down everything we bootstrapped so subsequent tests
            # / fixtures stay clean.
            if cleanup_ids:
                with db_engine.begin() as conn:
                    conn.execute(sa.text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
                    conn.execute(sa.text(
                        "DELETE FROM purchase_order_receipt_lines WHERE "
                        "receipt_id IN "
                        "(SELECT id FROM purchase_order_receipts WHERE purchase_order_id=:p)"
                    ), {"p": str(cleanup_ids["po_id"])})
                    conn.execute(sa.text(
                        "DELETE FROM purchase_order_receipts WHERE purchase_order_id=:p"
                    ), {"p": str(cleanup_ids["po_id"])})
                    conn.execute(sa.text(
                        "DELETE FROM purchase_order_lines WHERE purchase_order_id=:p"
                    ), {"p": str(cleanup_ids["po_id"])})
                    conn.execute(sa.text(
                        "DELETE FROM purchase_orders WHERE id=:p"
                    ), {"p": str(cleanup_ids["po_id"])})
                    conn.execute(sa.text(
                        "DELETE FROM audit_log WHERE resource_id=:p"
                    ), {"p": str(cleanup_ids["po_id"])})
                    conn.execute(sa.text(
                        "DELETE FROM project_number_prefixes WHERE id=:p"
                    ), {"p": str(cleanup_ids["prefix_id"])})
                    conn.execute(sa.text(
                        "DELETE FROM suppliers WHERE id=:s"
                    ), {"s": str(cleanup_ids["supplier_id"])})
                    if cleanup_ids.get("bootstrapped_project"):
                        conn.execute(sa.text(
                            "DELETE FROM budget_lines WHERE budget_id=:b"
                        ), {"b": str(cleanup_ids["budget_id"])})
                        conn.execute(sa.text(
                            "DELETE FROM budgets WHERE id=:b"
                        ), {"b": str(cleanup_ids["budget_id"])})
                        conn.execute(sa.text(
                            "DELETE FROM appraisals WHERE id=:a"
                        ), {"a": str(cleanup_ids["appraisal_id"])})
                        conn.execute(sa.text(
                            "UPDATE audit_log SET project_id=NULL WHERE project_id=:p"
                        ), {"p": str(cleanup_ids["project_id"])})
                        conn.execute(sa.text(
                            "DELETE FROM projects WHERE id=:p"
                        ), {"p": str(cleanup_ids["project_id"])})
                    conn.execute(sa.text("ALTER TABLE audit_log ENABLE TRIGGER USER"))

    def test_lines_taken_under_select_for_update(self):
        """Source-level guard: the helper's lines query carries
        `.with_for_update()` so concurrent receipts on different lines
        of one PO serialise the status-flip decision.
        """
        path = str(_BACKEND / "app" / "services" / "po_receipts.py")
        with open(path) as f:
            src = f.read()
        # Find the helper body and assert with_for_update is inside it.
        marker = "def _recompute_po_status_after_receipt_change"
        start = src.index(marker)
        end = src.index("\ndef ", start + 1)
        body = src[start:end]
        assert ".with_for_update()" in body, (
            "P0.2 helper must SELECT all PO lines FOR UPDATE before the "
            "all-fully-received check"
        )


# ======================================================================
# P0.3 — mfa_pending typed + blocked from /password/change
# ======================================================================

class TestP0_3_MfaPendingBlocked:
    """The 15-minute mfa_pending JWT (no session row, no idle-timeout)
    must NOT reach /password/change. It MUST still reach /me +
    /mfa/enroll/start for the legit enrol-before-first-login flow.
    """

    def test_token_type_literal_includes_mfa_pending(self):
        """Source-level guard — the Literal at tokens.py:33 lists all
        three token types. Drift here would silently re-allow
        unconstrained string token_type calls.
        """
        path = str(_BACKEND / "app" / "auth" / "tokens.py")
        with open(path) as f:
            src = f.read()
        assert (
            'Literal["access", "mfa_challenge", "mfa_pending"]' in src
        ), "tokens.py Literal must enumerate access / mfa_challenge / mfa_pending"

    def test_mfa_pending_rejected_by_password_change(self, db_engine):
        """LIVE 401/403: /password/change with an mfa_pending cookie.
        """
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_mfa_pending_token(pm_id, PM, tenant)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.post(f"{BASE_URL}/api/auth/password/change", json={
            "current_password": TEST_PASSWORD,
            "new_password": "Decoy-NewPwd-2026!",
        })
        print(f"\nP0.3 — /password/change with mfa_pending → HTTP {r.status_code} {r.text[:200]}")
        assert r.status_code in (401, 403), (
            f"mfa_pending must be rejected by /password/change; got {r.status_code}"
        )

    def test_mfa_pending_rejected_by_business_route(self, db_engine):
        """LIVE 401/403: any non-auth business route — pick /projects."""
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_mfa_pending_token(pm_id, PM, tenant)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.get(f"{BASE_URL}/api/projects")
        print(f"P0.3 — /api/projects with mfa_pending → HTTP {r.status_code}")
        assert r.status_code in (401, 403)

    def test_mfa_pending_accepted_by_me(self, db_engine):
        """LIVE 200: /auth/me must still accept mfa_pending so the
        pre-enrol UI can render the user's profile chrome.
        """
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_mfa_pending_token(pm_id, PM, tenant)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.get(f"{BASE_URL}/api/auth/me")
        print(f"P0.3 — /auth/me with mfa_pending → HTTP {r.status_code}")
        assert r.status_code == 200, r.text

    def test_mfa_pending_accepted_by_enroll_start(self, db_engine):
        """LIVE 200 (or 4xx-but-not-401/403): /mfa/enroll/start must
        still accept mfa_pending. We assert NOT 401/403 because the
        endpoint may legitimately 400 if MFA is already enrolled — but
        the dep itself must let the token through.
        """
        _reset_user_mfa(db_engine, PM)
        pm_id, tenant = _user_id_and_tenant(db_engine, PM)
        tok = _mint_mfa_pending_token(pm_id, PM, tenant)
        s = _new_session()
        s.cookies.set("access_token", tok)
        r = s.post(f"{BASE_URL}/api/auth/mfa/enroll/start", json={})
        print(f"P0.3 — /mfa/enroll/start with mfa_pending → HTTP {r.status_code}")
        assert r.status_code not in (401, 403), (
            f"enroll/start must accept mfa_pending; got {r.status_code} {r.text[:200]}"
        )


# ======================================================================
# P0.4 — /mfa/verify rate-limited
# ======================================================================

class TestP0_4_MfaVerifyRateLimit:
    """Bucket `mfa_verify_per_user` (5/min) caps grinding of TOTP /
    backup codes by a holder of a valid 5-min mfa_challenge.
    """

    def test_limits_dict_carries_mfa_verify_bucket(self):
        import app.services.rate_limit as rl
        rl = importlib.reload(rl)
        print(f"\nP0.4 — LIMITS dict includes: {sorted(rl.LIMITS.keys())}")
        assert "mfa_verify_per_user" in rl.LIMITS
        assert rl.LIMITS["mfa_verify_per_user"] == (5, 60)

    def test_http_endpoint_returns_429_on_sixth_post(self, db_engine, monkeypatch):
        """REAL AC4 proof. Fires 6 actual POST /api/auth/mfa/verify
        requests with a valid mfa_challenge token and asserts the 6th
        returns literal HTTP 429.

        The running backend (uvicorn under supervisord) has
        SYHOMES_RATE_LIMIT_DISABLED=1 + APP_ENV=test in its env, so the
        production deployment bypasses the limiter — that env is the
        suite's test-escape lever. To exercise the real HTTP path
        WITHOUT the bypass we mount the FastAPI app in-process via
        TestClient, with APP_ENV=test removed so _is_bypass_active()
        returns False at call time. The limiter state is global to the
        Python process, so this still proves the wiring + bucket math
        against the production code path (the same enforce → check
        → bucket-count flow the production endpoint executes).
        """
        # Turn the bypass OFF for this test process. _is_bypass_active
        # reads env at call time, so a monkeypatched env takes effect
        # immediately on the next enforce() call.
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("SYHOMES_RATE_LIMIT_DISABLED", raising=False)
        import app.services.rate_limit as rl
        rl = importlib.reload(rl)
        # Sanity — bypass must actually be off, otherwise the test is
        # meaningless.
        assert rl._is_bypass_active() is False, (
            "monkeypatch did not turn the bypass off — test escape "
            "envvars are still active"
        )
        # Wipe any residual bucket state from earlier tests so the
        # first request lands on an empty (capacity=5) bucket.
        rl.rate_limiter.reset()

        from fastapi.testclient import TestClient
        # Late import to ensure the running module sees the env we
        # patched above.
        from server import app
        client = TestClient(app)

        # Mint a valid mfa_challenge token for a fresh user UUID so the
        # bucket starts empty (key = "mfa_verify_per_user:{uid}").
        uid = str(uuid.uuid4())
        payload = {
            "sub": uid,
            "email": "rl-test@example.test",
            "tenant_id": str(uuid.uuid4()),
            "iat": int(time.time()),
            "exp": int(time.time()) + 300,
            "type": "mfa_challenge",
        }
        challenge = jwt.encode(payload, JWT_SECRET, algorithm="HS256")

        # Fire 6 POSTs. Each must reach enforce() before any database
        # lookup, since the route's enforce() sits BETWEEN the type
        # check and the User lookup. Calls 1-5 consume slots; call 6
        # is denied → 429 with Retry-After.
        responses = []
        for i in range(6):
            r = client.post(
                "/api/auth/mfa/verify",
                json={"challenge_token": challenge, "code": "000000"},
            )
            responses.append((r.status_code, r.headers.get("Retry-After"),
                              (r.text or "")[:120]))
            print(f"P0.4 — POST /mfa/verify attempt {i + 1}: "
                  f"HTTP {r.status_code} "
                  f"retry_after={r.headers.get('Retry-After')!r} "
                  f"body={(r.text or '')[:80]!r}")

        statuses = [s for s, _, _ in responses]
        # AC4: the 6th request must be 429 — that is the LITERAL proof
        # this test is here to capture. Calls 1-5 will be 401 (user
        # doesn't exist / MFA not enrolled) but MUST NOT be 429.
        assert statuses[5] == 429, (
            f"6th POST /mfa/verify should be HTTP 429; got {statuses[5]}. "
            f"Full sequence: {statuses}"
        )
        for i, code in enumerate(statuses[:5], start=1):
            assert code != 429, (
                f"attempt {i} 429'd BEFORE bucket exhausted (sequence={statuses}) "
                f"— bucket math wrong or wiring broken"
            )
        # Retry-After must be a positive integer string on the 429 response.
        assert responses[5][1] is not None, (
            "429 response must carry a Retry-After header"
        )
        assert int(responses[5][1]) >= 1

    def test_http_endpoint_clean_single_post_is_not_429(self, monkeypatch):
        """A single legitimate POST must NOT be rate-limited (clean
        path proof — the limiter doesn't bite the first request)."""
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("SYHOMES_RATE_LIMIT_DISABLED", raising=False)
        import app.services.rate_limit as rl
        rl = importlib.reload(rl)
        rl.rate_limiter.reset()
        assert rl._is_bypass_active() is False

        from fastapi.testclient import TestClient
        from server import app
        client = TestClient(app)

        payload = {
            "sub": str(uuid.uuid4()), "email": "rl-clean@example.test",
            "tenant_id": str(uuid.uuid4()),
            "iat": int(time.time()), "exp": int(time.time()) + 300,
            "type": "mfa_challenge",
        }
        challenge = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        r = client.post(
            "/api/auth/mfa/verify",
            json={"challenge_token": challenge, "code": "000000"},
        )
        print(f"\nP0.4 — clean single POST /mfa/verify → "
              f"HTTP {r.status_code} body={(r.text or '')[:120]!r}")
        assert r.status_code != 429, (
            f"clean single verify must not be rate-limited; got 429"
        )

    def test_enforce_returns_429_after_5_in_window(self, monkeypatch):
        """Direct in-process test against the limiter — the route-level
        test is impractical because the running backend is a separate
        process whose env vars pytest can't toggle, and the existing
        suite escapes the limiter via SYHOMES_RATE_LIMIT_DISABLED. We
        mirror the in-process pattern used by TestPatch3 for the
        login buckets.
        """
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.delenv("SYHOMES_RATE_LIMIT_DISABLED", raising=False)
        import app.services.rate_limit as rl
        rl = importlib.reload(rl)
        # Bypass must be off so the limiter actually decides.
        assert rl._is_bypass_active() is False

        uid = str(uuid.uuid4())
        results = []
        for _ in range(5):
            ok, retry = rl.enforce("mfa_verify_per_user", uid)
            results.append((ok, retry))
        # First 5 attempts must pass.
        for i, (ok, _) in enumerate(results):
            assert ok is True, f"attempt {i + 1} should pass; got ok={ok}"
        # 6th is denied.
        ok6, retry6 = rl.enforce("mfa_verify_per_user", uid)
        print(f"\nP0.4 — 6th attempt: ok={ok6} retry_after={retry6:.2f}s")
        assert ok6 is False, "6th attempt must be rate-limited"
        assert retry6 > 0, "denied response must carry a positive retry_after"

    def test_enforce_call_is_wired_into_mfa_verify_route(self):
        """Source-level guard — the enforce call must sit between the
        type-check and the user lookup so malformed tokens 401 first
        and don't consume a bucket slot.
        """
        path = str(_BACKEND / "app" / "routers" / "auth.py")
        with open(path) as f:
            src = f.read()
        # Find the /mfa/verify route body.
        marker = '@router.post("/mfa/verify"'
        start = src.index(marker)
        # End at the next @router decorator.
        end = src.index("\n@router.", start + 1)
        body = src[start:end]
        # Order check: type-check → enforce → User lookup.
        type_check_pos = body.index('claims.get("type") != "mfa_challenge"')
        enforce_pos = body.index('enforce("mfa_verify_per_user", claims["sub"])')
        user_lookup_pos = body.index("db.get(User, uuid.UUID(claims")
        print(f"\nP0.4 — wiring positions in /mfa/verify body: "
              f"type_check={type_check_pos} enforce={enforce_pos} "
              f"user_lookup={user_lookup_pos}")
        assert type_check_pos < enforce_pos < user_lookup_pos, (
            "enforce call must sit between the type check and the user lookup"
        )
        assert "status_code=429" in body
        assert 'headers={"Retry-After"' in body

    def test_clean_single_enforce_call_returns_ok(self, monkeypatch):
        """A single legitimate verify must not be rate-limited."""
        monkeypatch.setenv("APP_ENV", "test")
        monkeypatch.delenv("SYHOMES_RATE_LIMIT_DISABLED", raising=False)
        import app.services.rate_limit as rl
        rl = importlib.reload(rl)
        ok, retry = rl.enforce("mfa_verify_per_user", str(uuid.uuid4()))
        print(f"\nP0.4 — clean single enforce → ok={ok} retry_after={retry:.2f}")
        assert ok is True
        assert retry == 0.0
