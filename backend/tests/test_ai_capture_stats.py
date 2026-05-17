"""AI capture cost stats tests — Chat 20 / Prompt 2.5D (B38).

Covers the new `GET /api/v1/ai-capture-jobs/stats` endpoint:
- Permission gating (ai_capture.view_costs required; actuals.admin alone is NOT enough)
- Aggregation correctness (totals SUM, daily zero-fill, status breakdown buckets)
- Validation (from_date > to_date, future to_date, default window)
- seed_rbac catalogue + finance role membership

Pattern: module-scoped engine + explicit _wipe; HTTP tests via cookies-only
login (test-admin / test-finance / test-pm / test-director seeded users).
In-process tests use sessionmaker directly against the compute_capture_stats
service function.
"""
from __future__ import annotations

import os
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tests.conftest import login_with_auto_enroll


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
DIRECTOR_EMAIL = "test-director@example.test"
FINANCE_EMAIL = "test-finance@example.test"
PM_EMAIL = "test-pm@example.test"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def Session(db_engine):
    return sessionmaker(bind=db_engine, expire_on_commit=False, future=True)


def _wipe(engine):
    """Clear AI capture jobs + inbound emails before/after each test."""
    with engine.begin() as c:
        c.execute(text("DELETE FROM ai_capture_jobs"))
        c.execute(text("DELETE FROM inbound_email_messages"))


@pytest.fixture(autouse=True)
def _per_test_wipe(db_engine):
    _wipe(db_engine)
    yield
    _wipe(db_engine)


def _seed_inbound(engine) -> uuid.UUID:
    """Seed a minimal inbound_email_message row required by the FK."""
    mid = uuid.uuid4()
    with engine.begin() as c:
        admin_id = c.execute(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        )).scalar()
        if not admin_id:
            pytest.skip("test-admin user missing — run seed_test_users.py")
        c.execute(text("""
            INSERT INTO inbound_email_messages
              (id, postmark_message_id, from_email, to_email,
               subject, received_at, attachment_count)
            VALUES (:id, :pmid, 'supplier@example.com', 'bills@syhomes.co.uk',
                    'Test invoice', NOW(), 1)
        """), {
            "id": mid,
            "pmid": f"pm-{mid.hex[:12]}",
        })
    return mid


def _insert_job(engine, *, status: str, created_at: datetime,
                cost_pence: int = 100, prompt_tokens: int = 50,
                completion_tokens: int = 25,
                inbound_id: uuid.UUID | None = None) -> uuid.UUID:
    """Seed one ai_capture_jobs row with explicit timestamps."""
    job_id = uuid.uuid4()
    if inbound_id is None:
        inbound_id = _seed_inbound(engine)
    with engine.begin() as c:
        c.execute(text("""
            INSERT INTO ai_capture_jobs
              (id, inbound_email_message_id, attachment_path, status,
               attempts, model_used, prompt_tokens, completion_tokens,
               cost_pence, created_at, updated_at)
            VALUES (:id, :iid, :path, :status, 0, 'test-stub',
                    :pt, :ct, :cp, :ts, :ts)
        """), {
            "id": job_id, "iid": inbound_id,
            "path": f"/tmp/test-{job_id.hex[:8]}.pdf",
            "status": status,
            "pt": prompt_tokens, "ct": completion_tokens,
            "cp": cost_pence,
            "ts": created_at,
        })
    return job_id


# ---------------------------------------------------------------------------
# Permission tests (HTTP)
# ---------------------------------------------------------------------------

class TestCaptureStatsPermissions:
    """ai_capture.view_costs gate. actuals.admin alone is NOT sufficient."""

    def test_unauthenticated_returns_401(self):
        r = requests.get(
            f"{BASE_URL}/api/v1/ai-capture-jobs/stats",
            timeout=10,
        )
        assert r.status_code == 401

    def test_finance_role_returns_200(self):
        s = login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)
        r = s.get(f"{BASE_URL}/api/v1/ai-capture-jobs/stats", timeout=10)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "totals" in body
        assert "daily_series" in body
        assert "by_status" in body

    def test_director_role_returns_200(self):
        s = login_with_auto_enroll(None, BASE_URL, DIRECTOR_EMAIL, PWD)
        r = s.get(f"{BASE_URL}/api/v1/ai-capture-jobs/stats", timeout=10)
        assert r.status_code == 200, r.text

    def test_project_manager_alone_returns_403(self):
        """PM has actuals.* but not ai_capture.view_costs — must 403."""
        s = login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)
        r = s.get(f"{BASE_URL}/api/v1/ai-capture-jobs/stats", timeout=10)
        assert r.status_code == 403


# ---------------------------------------------------------------------------
# Aggregation tests (in-process service)
# ---------------------------------------------------------------------------

class TestCaptureStatsAggregation:
    """compute_capture_stats correctness."""

    def test_empty_range_returns_zeros(self, db_engine, Session):
        from app.services.ai_capture import compute_capture_stats
        with Session() as s:
            out = compute_capture_stats(
                s,
                from_date=date(2026, 1, 1),
                to_date=date(2026, 1, 7),
            )
        assert out["totals"]["total_jobs"] == 0
        assert out["totals"]["total_cost_pence"] == 0
        assert out["totals"]["avg_cost_pence"] == 0
        # Zero-filled daily series (7 days inclusive)
        assert len(out["daily_series"]) == 7
        for pt in out["daily_series"]:
            assert pt["cost_pence"] == 0
            assert pt["job_count"] == 0
        # Status buckets always present
        statuses = [b["status"] for b in out["by_status"]]
        assert statuses == ["Completed", "Failed", "Discarded"]
        for b in out["by_status"]:
            assert b["cost_pence"] == 0
            assert b["job_count"] == 0

    def test_totals_sum_correctly_across_statuses(self, db_engine, Session):
        from app.services.ai_capture import compute_capture_stats
        # Use today (London-local) to stay inside the range. We pick a
        # midday UTC ts to avoid tz-boundary surprises.
        london_today = datetime.now(timezone.utc).astimezone().date()
        ts = datetime(london_today.year, london_today.month, london_today.day,
                      12, 0, tzinfo=timezone.utc)
        inbound = _seed_inbound(db_engine)
        _insert_job(db_engine, status="Completed", created_at=ts,
                    cost_pence=150, prompt_tokens=10, completion_tokens=5,
                    inbound_id=inbound)
        _insert_job(db_engine, status="Failed", created_at=ts,
                    cost_pence=200, prompt_tokens=20, completion_tokens=10,
                    inbound_id=inbound)
        _insert_job(db_engine, status="Discarded", created_at=ts,
                    cost_pence=50, prompt_tokens=5, completion_tokens=2,
                    inbound_id=inbound)
        # Queued — counted in totals but NOT in by_status (in-flight)
        _insert_job(db_engine, status="Queued", created_at=ts,
                    cost_pence=0, prompt_tokens=0, completion_tokens=0,
                    inbound_id=inbound)

        with Session() as s:
            out = compute_capture_stats(
                s, from_date=london_today, to_date=london_today,
            )
        assert out["totals"]["total_jobs"] == 4
        assert out["totals"]["total_cost_pence"] == 400
        assert out["totals"]["total_prompt_tokens"] == 35
        assert out["totals"]["total_completion_tokens"] == 17
        # avg = 400 / 4 = 100
        assert out["totals"]["avg_cost_pence"] == 100

    def test_daily_series_zero_filled_for_gap_days(self, db_engine, Session):
        from app.services.ai_capture import compute_capture_stats
        london_today = datetime.now(timezone.utc).astimezone().date()
        # Use today - 3 .. today (4 days). Insert on today and today-3 only.
        from_d = london_today - timedelta(days=3)
        to_d = london_today
        ts_today = datetime(london_today.year, london_today.month,
                            london_today.day, 12, 0, tzinfo=timezone.utc)
        ts_minus_3 = ts_today - timedelta(days=3)
        inbound = _seed_inbound(db_engine)
        _insert_job(db_engine, status="Completed", created_at=ts_today,
                    cost_pence=100, inbound_id=inbound)
        _insert_job(db_engine, status="Completed", created_at=ts_minus_3,
                    cost_pence=300, inbound_id=inbound)

        with Session() as s:
            out = compute_capture_stats(s, from_date=from_d, to_date=to_d)
        assert len(out["daily_series"]) == 4
        # First day (minus 3) has the 300 pence row
        assert out["daily_series"][0]["cost_pence"] == 300
        assert out["daily_series"][0]["job_count"] == 1
        # Middle days zero-filled
        assert out["daily_series"][1]["cost_pence"] == 0
        assert out["daily_series"][1]["job_count"] == 0
        assert out["daily_series"][2]["cost_pence"] == 0
        assert out["daily_series"][2]["job_count"] == 0
        # Last day (today) has the 100 pence row
        assert out["daily_series"][3]["cost_pence"] == 100
        assert out["daily_series"][3]["job_count"] == 1

    def test_by_status_excludes_in_flight(self, db_engine, Session):
        """Queued / Extracting / Awaiting_Review must NOT appear in by_status."""
        from app.services.ai_capture import compute_capture_stats
        london_today = datetime.now(timezone.utc).astimezone().date()
        ts = datetime(london_today.year, london_today.month, london_today.day,
                      12, 0, tzinfo=timezone.utc)
        inbound = _seed_inbound(db_engine)
        for st in ("Queued", "Extracting", "Awaiting_Review"):
            _insert_job(db_engine, status=st, created_at=ts,
                        cost_pence=999, inbound_id=inbound)
        _insert_job(db_engine, status="Completed", created_at=ts,
                    cost_pence=100, inbound_id=inbound)

        with Session() as s:
            out = compute_capture_stats(
                s, from_date=london_today, to_date=london_today,
            )
        # Buckets are fixed — always (Completed, Failed, Discarded)
        statuses = [b["status"] for b in out["by_status"]]
        assert statuses == ["Completed", "Failed", "Discarded"]
        completed = next(b for b in out["by_status"] if b["status"] == "Completed")
        assert completed["job_count"] == 1
        assert completed["cost_pence"] == 100
        failed = next(b for b in out["by_status"] if b["status"] == "Failed")
        assert failed["job_count"] == 0
        # Totals still count all 4 jobs
        assert out["totals"]["total_jobs"] == 4


# ---------------------------------------------------------------------------
# Validation tests (HTTP)
# ---------------------------------------------------------------------------

class TestCaptureStatsValidation:
    """Date-range guards."""

    def test_from_after_to_returns_422(self):
        s = login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)
        r = s.get(
            f"{BASE_URL}/api/v1/ai-capture-jobs/stats",
            params={"from_date": "2026-05-10", "to_date": "2026-05-01"},
            timeout=10,
        )
        assert r.status_code == 422
        body = r.json()
        assert body["detail"]["code"] == "invalid_date_range"

    def test_future_to_date_returns_422(self):
        s = login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)
        future = (
            datetime.now(timezone.utc).astimezone().date() + timedelta(days=30)
        )
        r = s.get(
            f"{BASE_URL}/api/v1/ai-capture-jobs/stats",
            params={"to_date": future.isoformat()},
            timeout=10,
        )
        assert r.status_code == 422
        assert r.json()["detail"]["code"] == "future_date"

    def test_default_30_day_window(self):
        """No params → today and today-29, inclusive (30 days)."""
        s = login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)
        r = s.get(f"{BASE_URL}/api/v1/ai-capture-jobs/stats", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body["period"]["days"] == 30
        assert len(body["daily_series"]) == 30


# ---------------------------------------------------------------------------
# Permission catalogue tests (in-process)
# ---------------------------------------------------------------------------

class TestCaptureStatsPermissionCatalogue:
    """seed_rbac contains the new permission and the right role mappings."""

    def test_ai_capture_view_costs_in_catalogue(self):
        from app.seed_rbac import PERMISSION_CATALOGUE
        codes = {row[0] for row in PERMISSION_CATALOGUE}
        assert "ai_capture.view_costs" in codes

    def test_finance_role_set_includes_new_perm(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "ai_capture.view_costs" in ROLE_PERMISSIONS["finance"]

    def test_super_admin_and_director_have_perm_via_global_set(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "ai_capture.view_costs" in ROLE_PERMISSIONS["super_admin"]
        assert "ai_capture.view_costs" in ROLE_PERMISSIONS["director"]

    def test_project_manager_does_not_have_perm(self):
        from app.seed_rbac import ROLE_PERMISSIONS
        assert "ai_capture.view_costs" not in ROLE_PERMISSIONS["project_manager"]
        assert "ai_capture.view_costs" not in ROLE_PERMISSIONS["site_manager"]
        assert "ai_capture.view_costs" not in ROLE_PERMISSIONS["read_only"]
