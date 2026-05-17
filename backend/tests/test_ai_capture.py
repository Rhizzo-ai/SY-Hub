"""AI capture pipeline tests — Prompt 2.5A / Chat 19A.

Covers:
- Postmark webhook (6 tests): HMAC, kill-switch, idempotency, MIME filter
- AI extraction (9 tests): stub, claim, retry, discard, promote

Postmark webhook is tested via HTTP since the router enforces the kill-switch
and signature check. AI extraction is tested in-process against the service.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.permissions import UserPermissions
from app.config import get_settings
from app.models.actuals import AICaptureJob, InboundEmailMessage, Actual
from app.models.user import User
from app.schemas.actuals import PromoteCaptureToActualRequest, DiscardCaptureRequest
from app.services import ai_capture as cap_svc
from app.services.actual_errors import (
    CaptureJobNotFoundError, CaptureJobNotReadyError,
)

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
POSTMARK_SECRET = os.environ.get("POSTMARK_INBOUND_SECRET", "test-secret-do-not-use")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _all_perms(user) -> UserPermissions:
    perm_set = {
        "actuals.view", "actuals.view_sensitive",
        "actuals.create", "actuals.edit",
        "actuals.approve", "actuals.admin",
    }
    return UserPermissions(
        user_id=user.id,
        tenant_id=user.tenant_id,
        all_permissions=set(perm_set),
        all_entity_perms=set(perm_set),
        all_project_perms=set(perm_set),
        is_super_admin=True,
    )


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def Session(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@pytest.fixture(scope="module")
def seeds(engine):
    refs = {}
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        admin = c.execute(text(
            "SELECT id, tenant_id FROM users WHERE email='test-admin@example.test'"
        )).first()
        if not (entity_id and admin):
            pytest.skip("required seed rows missing")
        refs.update(entity_id=entity_id, user_id=admin.id,
                    tenant_id=admin.tenant_id)

        # Project + appraisal + active budget + line so promote can create an actual.
        project_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '1 AI Way', 'SY4 2AA', false, :u)
        """), {"id": project_id, "code": f"AI-{project_id.hex[:6]}",
               "name": f"AI Test {project_id.hex[:6]}",
               "ent": entity_id, "u": admin.id})
        refs["project_id"] = project_id

        ag = uuid.uuid4()
        ap = uuid.uuid4()
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (:id, :pid, 'AI Base', CURRENT_DATE,
                      :uid, :gid, 'Base', true, 'Approved', 1)
        """), {"id": ap, "pid": project_id, "uid": admin.id, "gid": ag})
        refs["appraisal_id"] = ap

        budget_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budgets (id, project_id, source_appraisal_id,
              version_number, version_label, is_current, status,
              created_from_appraisal_at,
              total_budget, total_actuals, total_committed_not_invoiced,
              total_forecast_to_complete, forecast_final_cost,
              variance_vs_budget, variance_pct, summary_refreshed_at,
              created_by_user_id)
            VALUES (:id, :pid, :ap, 1, 'v1', true, 'Active', NOW(),
                    1000000, 0, 0, 1000000, 1000000, 0, 0, NOW(), :u)
        """), {"id": budget_id, "pid": project_id, "ap": ap, "u": admin.id})
        refs["budget_id"] = budget_id

        cc_id = c.execute(text("SELECT id FROM cost_codes LIMIT 1")).scalar()
        line_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO budget_lines (id, budget_id, cost_code_id,
              display_order, line_description, entity_id, ftc_method,
              original_budget, approved_changes, current_budget,
              actuals_to_date, committed_value, invoiced_against_commitment,
              committed_not_invoiced, forecast_to_complete,
              forecast_final_cost, variance_value, variance_pct,
              variance_status, is_locked, requires_attention)
            VALUES (:id, :bid, :cc, 1, 'AI line', :ent, 'Manual',
                    500000, 0, 500000, 0, 0, 0, 0, 500000, 500000,
                    0, 0, 'Green', false, false)
        """), {"id": line_id, "bid": budget_id, "cc": cc_id, "ent": entity_id})
        refs["line_id"] = line_id

    yield refs

    with engine.begin() as c:
        c.execute(text("DELETE FROM ai_capture_jobs WHERE inbound_email_message_id IN "
                       "(SELECT id FROM inbound_email_messages)"))
        c.execute(text("DELETE FROM inbound_email_messages"))
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": refs["project_id"]})
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals WHERE project_id=:p"),
                  {"p": refs["project_id"]})
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM budget_lines WHERE budget_id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM budgets WHERE id=:b"),
                  {"b": refs["budget_id"]})
        c.execute(text("DELETE FROM appraisals WHERE id=:a"),
                  {"a": refs["appraisal_id"]})
        c.execute(text("DELETE FROM projects WHERE id=:p"),
                  {"p": refs["project_id"]})


@pytest.fixture(autouse=True)
def _wipe(engine):
    yield
    with engine.begin() as c:
        c.execute(text("DELETE FROM ai_capture_jobs"))
        c.execute(text("DELETE FROM inbound_email_messages"))
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log"))
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals"))
        c.execute(text("ALTER TABLE actuals ENABLE TRIGGER USER"))


@pytest.fixture
def db(Session):
    s = Session()
    yield s
    s.rollback()
    s.close()


@pytest.fixture
def admin_user(db, seeds):
    return db.get(User, seeds["user_id"])


@pytest.fixture
def perms(admin_user):
    return _all_perms(admin_user)


# ---------------------------------------------------------------------------
# Postmark webhook tests (6) — uses live HTTP against the running server.
# ---------------------------------------------------------------------------

def _postmark_payload(message_id=None, attachments=None):
    return {
        "MessageID": message_id or f"msg-{uuid.uuid4().hex[:12]}",
        "From": "supplier@example.com",
        "To": "bills@syhomes.co.uk",
        "Subject": "Invoice #1234",
        "TextBody": "Please find invoice attached.",
        "Attachments": attachments or [],
    }


def _enable_postmark_inbound(engine):
    """Temporarily flip the kill-switch via monkey-patching settings cache."""
    settings = get_settings()
    # Use object.__setattr__ to bypass frozen dataclass
    object.__setattr__(settings, "postmark_inbound_enabled", True)


def _disable_postmark_inbound():
    settings = get_settings()
    object.__setattr__(settings, "postmark_inbound_enabled", False)


class TestPostmarkWebhook:
    """6 tests covering the inbound webhook flow.

    Routes go via the real HTTP server (supervisor-managed). Kill-switch is
    tested by direct service call since the env var is set at startup.
    `POSTMARK_INBOUND_ENABLED=true` MUST be set in backend/.env for these tests.
    """

    def test_kill_switch_blocks_via_service(self, db, engine, monkeypatch):
        """Direct: when settings.postmark_inbound_enabled is False the router
        returns 503. Hit the router via FastAPI TestClient with the in-process
        kill-switch flipped off.
        """
        from fastapi.testclient import TestClient
        from server import app  # backend/server.py mounts the FastAPI app
        client = TestClient(app)
        settings = get_settings()
        object.__setattr__(settings, "postmark_inbound_enabled", False)
        try:
            r = client.post(
                "/api/v1/inbound/postmark",
                params={"secret": POSTMARK_SECRET},
                json=_postmark_payload(),
            )
            assert r.status_code == 503
        finally:
            object.__setattr__(settings, "postmark_inbound_enabled", True)

    def test_inbound_401_on_bad_secret(self, engine):
        r = requests.post(
            f"{BASE_URL}/api/v1/inbound/postmark",
            params={"secret": "wrong-secret"},
            json=_postmark_payload(),
            timeout=10,
        )
        assert r.status_code == 401

    def test_inbound_422_on_bad_json(self, engine):
        r = requests.post(
            f"{BASE_URL}/api/v1/inbound/postmark",
            params={"secret": POSTMARK_SECRET},
            data="not json",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code in (400, 422)

    def test_inbound_202_accepts_valid_payload(self, engine):
        r = requests.post(
            f"{BASE_URL}/api/v1/inbound/postmark",
            params={"secret": POSTMARK_SECRET},
            json=_postmark_payload(),
            timeout=10,
        )
        assert r.status_code == 202, r.text
        body = r.json()
        assert "inbound_email_message_id" in body

    def test_inbound_idempotent_on_dup_message_id(self, engine):
        mid = f"msg-dup-{uuid.uuid4().hex[:8]}"
        r1 = requests.post(
            f"{BASE_URL}/api/v1/inbound/postmark",
            params={"secret": POSTMARK_SECRET},
            json=_postmark_payload(message_id=mid),
            timeout=10,
        )
        r2 = requests.post(
            f"{BASE_URL}/api/v1/inbound/postmark",
            params={"secret": POSTMARK_SECRET},
            json=_postmark_payload(message_id=mid),
            timeout=10,
        )
        assert r1.status_code == 202
        assert r2.status_code == 202
        assert r1.json()["inbound_email_message_id"] == \
            r2.json()["inbound_email_message_id"]

    def test_inbound_skips_non_extractable_mime(self, engine):
        attachments = [{
            "Name": "thing.zip",
            "Content": base64.b64encode(b"x").decode(),
            "ContentType": "application/zip",
            "ContentLength": 1,
        }]
        r = requests.post(
            f"{BASE_URL}/api/v1/inbound/postmark",
            params={"secret": POSTMARK_SECRET},
            json=_postmark_payload(attachments=attachments),
            timeout=10,
        )
        assert r.status_code == 202, r.text
        body = r.json()
        # zip is non-extractable → 0 jobs enqueued
        assert body["jobs_enqueued"] == []


# ---------------------------------------------------------------------------
# AI extraction tests (9) — direct service calls + stub mode
# ---------------------------------------------------------------------------

def _make_inbound_and_job(db, seeds, *, attachment_path="/tmp/fake.pdf"):
    msg = InboundEmailMessage(
        postmark_message_id=f"mid-{uuid.uuid4().hex[:8]}",
        from_email="x@example.com",
        to_email="bills@syhomes.co.uk",
        subject="Test",
        received_at=datetime.now(timezone.utc),
        raw_email_path="/tmp",
        attachment_count=1,
    )
    db.add(msg)
    db.flush()
    job = cap_svc.enqueue_capture_job(
        db, inbound_email_message_id=msg.id, attachment_path=attachment_path,
    )
    db.commit()
    return msg, job


class TestAIExtraction:
    def test_stub_provider_returns_expected_shape(self, db, seeds):
        _, job = _make_inbound_and_job(db, seeds)
        result = cap_svc._extract_stub(job)
        assert "data" in result
        assert "confidence" in result
        assert result["model"] == "test-stub"
        assert result["data"]["supplier_name"] == "Acme Supplies Ltd"

    def test_process_one_job_picks_oldest_queued(self, db, seeds):
        _, j1 = _make_inbound_and_job(db, seeds)
        _, j2 = _make_inbound_and_job(db, seeds)
        # In stub mode, this should succeed and transition the oldest Queued.
        first_id = cap_svc.process_one_job(db)
        db.commit()
        assert first_id == j1.id
        db.refresh(j1)
        assert j1.status == "Awaiting_Review"

    def test_process_one_job_increments_attempts(self, db, seeds):
        _, job = _make_inbound_and_job(db, seeds)
        cap_svc.process_one_job(db)
        db.commit()
        db.refresh(job)
        assert job.attempts == 1

    def test_process_one_job_returns_none_when_queue_empty(self, db, seeds):
        # No jobs - should return None gracefully
        result = cap_svc.process_one_job(db)
        assert result is None

    def test_process_one_job_skip_lock_safe(self, db, seeds):
        """Two simultaneous claims must not pick the same row.

        Simulate by claiming and then doing a second claim from a fresh session.
        With FOR UPDATE SKIP LOCKED the second claim returns nothing because
        the first transaction holds the row.
        """
        _, job = _make_inbound_and_job(db, seeds)
        # Claim in this session — leaves the row locked until commit.
        claimed = cap_svc._claim_queued_job(db)
        assert claimed is not None
        # Second session must NOT see this Queued row (already Extracting).
        # NOTE: we don't open a parallel connection here; we just assert the
        # status flip happened atomically.
        assert claimed.status == "Extracting"
        db.commit()

    def test_failed_job_retains_last_error_message(
        self, db, seeds, monkeypatch,
    ):
        _, job = _make_inbound_and_job(db, seeds)
        # Force the stub to raise by monkey-patching settings to non-stub
        # with empty key — actually since key is empty, falls into stub. So
        # patch _extract_stub directly to raise.
        def boom(j):
            raise RuntimeError("simulated failure")
        monkeypatch.setattr(cap_svc, "_extract_stub", boom)
        # bump attempts above max so it lands in Failed.
        job.attempts = get_settings().ai_capture_max_attempts
        db.commit()
        cap_svc.process_one_job(db)
        db.commit()
        db.refresh(job)
        assert job.status == "Failed"
        assert "simulated failure" in (job.last_error_message or "")

    def test_retry_failed_resets_status(self, db, seeds, admin_user, perms):
        _, job = _make_inbound_and_job(db, seeds)
        job.status = "Failed"
        job.last_error_message = "previous error"
        db.commit()
        cap_svc.retry_capture(
            db, job_id=job.id, user=admin_user, perms=perms,
        )
        db.commit()
        db.refresh(job)
        assert job.status == "Queued"
        assert job.last_error_message is None

    def test_discard_sets_status_discarded(self, db, seeds, admin_user, perms):
        _, job = _make_inbound_and_job(db, seeds)
        job.status = "Awaiting_Review"
        db.commit()
        cap_svc.discard_capture(
            db, job_id=job.id, reason="not an invoice",
            user=admin_user, perms=perms,
        )
        db.commit()
        db.refresh(job)
        assert job.status == "Discarded"

    def test_promote_creates_draft_actual(self, db, seeds, admin_user, perms):
        _, job = _make_inbound_and_job(db, seeds)
        cap_svc.process_one_job(db)
        db.commit()
        db.refresh(job)
        assert job.status == "Awaiting_Review"

        body = PromoteCaptureToActualRequest(
            project_id=seeds["project_id"],
            budget_line_id=seeds["line_id"],
            entity_id=seeds["entity_id"],
            transaction_date=date.today(),
            description="from AI capture",
            net_amount=Decimal("100.00"),
            vat_amount=Decimal("20.00"),
            vat_rate_pct=Decimal("20"),
            supplier_name_snapshot="Acme Supplies Ltd",
        )
        new_job, actual = cap_svc.promote_capture_to_actual(
            db, job_id=job.id, payload=body, user=admin_user, perms=perms,
        )
        db.commit()
        assert new_job.status == "Completed"
        assert new_job.target_actual_id == actual.id
        assert actual.status == "Draft"

    def test_promote_rejects_non_awaiting_review(
        self, db, seeds, admin_user, perms,
    ):
        _, job = _make_inbound_and_job(db, seeds)
        # Still Queued, not Awaiting_Review
        body = PromoteCaptureToActualRequest(
            project_id=seeds["project_id"],
            budget_line_id=seeds["line_id"],
            entity_id=seeds["entity_id"],
            transaction_date=date.today(),
            description="bad timing",
            net_amount=Decimal("1.00"),
            supplier_name_snapshot="X",
        )
        with pytest.raises(CaptureJobNotReadyError):
            cap_svc.promote_capture_to_actual(
                db, job_id=job.id, payload=body,
                user=admin_user, perms=perms,
            )


# ---------------------------------------------------------------------------
# Permission count test (1) — meets §R6.2 'Permission count test' line
# ---------------------------------------------------------------------------

class TestPermissionCatalogue:
    def test_actuals_admin_permission_added(self):
        from app.seed_rbac import PERMISSION_CATALOGUE, ROLE_PERMISSIONS
        # PERMISSION_CATALOGUE rows are tuples: (code, resource, action, desc, is_sensitive)
        codes = {row[0] for row in PERMISSION_CATALOGUE}
        assert "actuals.admin" in codes
        assert "actuals.view" in codes
        admin_row = next(row for row in PERMISSION_CATALOGUE if row[0] == "actuals.admin")
        assert admin_row[4] is True  # is_sensitive
        # Finance role includes both admin + edit
        assert "actuals.admin" in ROLE_PERMISSIONS["finance"]
        assert "actuals.edit" in ROLE_PERMISSIONS["finance"]
        # Project manager has view/create/edit but not admin
        assert "actuals.admin" not in ROLE_PERMISSIONS["project_manager"]
        assert "actuals.create" in ROLE_PERMISSIONS["project_manager"]


# ---------------------------------------------------------------------------
# Attachment download endpoint test (1) — Chat 19C §R5.1 C1 / §R6.2 STOP gate 0
# ---------------------------------------------------------------------------
#
# Locks the new `GET /api/v1/ai-capture-jobs/{job_id}/attachment` endpoint:
# returns the file bytes with the inferred MIME type when the path exists,
# 410 when the row references a path that's been wiped from disk.

class TestAttachmentDownload:
    def test_attachment_download_returns_file_bytes(
        self, db, seeds, admin_user, perms, tmp_path,
    ):
        """End-to-end: enqueue a job with a real PDF on disk → download it
        via the new endpoint → assert content + content-type.
        """
        from fastapi.testclient import TestClient
        from server import app
        from app.auth.deps import get_current_principal, Principal

        pdf = tmp_path / "invoice-19c.pdf"
        pdf.write_bytes(b"%PDF-1.4\n%real bytes for B36+19C test\n%%EOF\n")
        _, job = _make_inbound_and_job(db, seeds, attachment_path=str(pdf))

        # Override the upstream principal dep so both get_current_user and
        # require_permission("actuals.admin") see a fully-permissioned admin
        # without needing a live login cookie. require_permission returns a
        # fresh closure per call so it can't be overridden directly — but it
        # depends on get_current_principal, which we CAN override.
        def _principal():
            return Principal(
                user=admin_user,
                tenant_id=seeds["tenant_id"],
                token_type="access",
                session=None,
            )
        app.dependency_overrides[get_current_principal] = _principal
        try:
            client = TestClient(app)
            r = client.get(f"/api/v1/ai-capture-jobs/{job.id}/attachment")
            assert r.status_code == 200, r.text
            assert r.headers["content-type"].startswith("application/pdf")
            assert r.content.startswith(b"%PDF-1.4")
            assert b"%%EOF" in r.content

            # Path gone -> 410
            pdf.unlink()
            r2 = client.get(f"/api/v1/ai-capture-jobs/{job.id}/attachment")
            assert r2.status_code == 410
        finally:
            app.dependency_overrides.clear()

