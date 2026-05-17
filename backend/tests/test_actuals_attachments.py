"""Actuals attachments regression tests — Chat 19C §R0.6.3 (B36 lock-in).

The original B36 symptom — `POST /actuals/:id/attachments` returns 201 but the
immediate subsequent `GET /actuals/:id/attachments` returns `count=0` — is not
reproducible at HEAD (see chat-19c-closing.md §"B36 RCA — not reproducible").
This test locks the invariant: after a successful POST the row must be visible
to a fresh-session GET on the same actual_id. Future regressions of the
read-after-write contract are caught here before the surface-level E2E.

The test runs in-process against the FastAPI app via TestClient with overridden
auth dependencies — it does NOT depend on the live supervisor server or
on `test-admin` having a valid login cookie. The B36 path was at the HTTP layer,
so we exercise the HTTP layer; we just bypass cookie-based auth to keep the
test self-contained and fast.
"""
from __future__ import annotations

import os
import uuid
from datetime import date

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.auth.deps import get_current_user, require_permission
from app.auth.permissions import UserPermissions
from app.models.user import User

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


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
    """Build a minimal but valid project → appraisal → active budget → line
    chain that we can hang a Draft actual off. Same pattern as
    `tests/test_ai_capture.py::seeds` (kept locally so this file is
    self-contained).
    """
    refs: dict = {}
    with engine.begin() as c:
        entity_id = c.execute(text("SELECT id FROM entities LIMIT 1")).scalar()
        admin = c.execute(text(
            "SELECT id, tenant_id FROM users WHERE email='test-admin@example.test'"
        )).first()
        if not (entity_id and admin):
            pytest.skip("required seed rows missing")
        refs.update(entity_id=entity_id, user_id=admin.id,
                    tenant_id=admin.tenant_id)

        project_id = uuid.uuid4()
        c.execute(text("""
            INSERT INTO projects
              (id, project_code, name, primary_entity_id, project_type,
               land_ownership_method, status, tenure, current_stage,
               stage_entered_at, site_address, site_postcode,
               implementation_required, created_by_user_id)
            VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                    'Active', 'Freehold', 'Lead', NOW(),
                    '1 B36 Way', 'SY4 9BB', false, :u)
        """), {"id": project_id, "code": f"B36-{project_id.hex[:6]}",
               "name": f"B36 Test {project_id.hex[:6]}",
               "ent": entity_id, "u": admin.id})
        refs["project_id"] = project_id

        ag = uuid.uuid4()
        ap = uuid.uuid4()
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number
            ) VALUES (:id, :pid, 'B36 Base', CURRENT_DATE,
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
            VALUES (:id, :bid, :cc, 1, 'B36 line', :ent, 'Manual',
                    500000, 0, 500000, 0, 0, 0, 0, 500000, 500000,
                    0, 0, 'Green', false, false)
        """), {"id": line_id, "bid": budget_id, "cc": cc_id, "ent": entity_id})
        refs["line_id"] = line_id

    yield refs

    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": refs["project_id"]})
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actual_attachments WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": refs["project_id"]})
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
def _wipe_between(engine, seeds):
    yield
    with engine.begin() as c:
        c.execute(text("ALTER TABLE actuals_change_log DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals_change_log WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": seeds["project_id"]})
        c.execute(text("ALTER TABLE actuals_change_log ENABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actual_attachments WHERE actual_id IN "
                       "(SELECT id FROM actuals WHERE project_id=:p)"),
                  {"p": seeds["project_id"]})
        c.execute(text("ALTER TABLE actuals DISABLE TRIGGER USER"))
        c.execute(text("DELETE FROM actuals WHERE project_id=:p"),
                  {"p": seeds["project_id"]})
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


@pytest.fixture
def client(admin_user, perms, seeds):
    """TestClient with admin auth wired in by overriding the shared upstream
    `get_current_principal` dependency. This propagates to `get_current_user`
    and `require_permission(...)` (which depends on get_current_principal) so
    every permission gate downstream sees a fully-permissioned admin.
    """
    from server import app
    from app.auth.deps import get_current_principal, Principal

    def _principal():
        return Principal(
            user=admin_user,
            tenant_id=seeds["tenant_id"],
            token_type="access",
            session=None,
        )
    app.dependency_overrides[get_current_principal] = _principal
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# B36 regression — read-after-write invariant
# ---------------------------------------------------------------------------

class TestB36AttachmentReadAfterWrite:
    """Locks the invariant: POST /actuals/:id/attachments → 201; immediate GET
    on the same actual_id MUST surface the new row.

    Chat-19A operator report: GET returned `count=0` after a successful POST
    on the preview backend, blocking the delete-trigger E2E. Chat-19C
    walkthrough (see chat-19c-closing.md "B36 RCA — not reproducible") found
    the symptom no longer manifests at HEAD — the hypothesised silent fix is
    chat-19B's `freshActual` factory rework (dynamic active-budget
    resolution). This test pins the contract so the surface cannot regress
    silently.
    """

    def _create_draft_actual(self, client, seeds) -> str:
        body = {
            "project_id": str(seeds["project_id"]),
            "budget_line_id": str(seeds["line_id"]),
            "entity_id": str(seeds["entity_id"]),
            "source_type": "Manual_Entry",
            "transaction_date": str(date.today()),
            "description": "B36 read-after-write",
            "net_amount": "100.00",
            "vat_amount": "20.00",
            "vat_rate_pct": "20",
            "supplier_name_snapshot": "B36 Supplier Ltd",
        }
        r = client.post("/api/v1/actuals", json=body)
        assert r.status_code == 201, r.text
        return r.json()["id"]

    def test_post_attachment_immediately_visible_in_list(self, client, seeds):
        actual_id = self._create_draft_actual(client, seeds)

        # POST a multipart attachment — same payload shape the React
        # dropzone sends (file + source=Manual_Upload).
        files = {"file": ("b36.pdf", b"%PDF-1.4 b36 repro\n%%EOF\n",
                          "application/pdf")}
        data = {"source": "Manual_Upload"}
        r_post = client.post(
            f"/api/v1/actuals/{actual_id}/attachments",
            files=files, data=data,
        )
        assert r_post.status_code == 201, r_post.text
        posted_id = r_post.json()["id"]

        # Immediate GET — no sleep, no second request to anything else. The
        # original B36 symptom would surface here as `count=0`.
        r_get = client.get(f"/api/v1/actuals/{actual_id}/attachments")
        assert r_get.status_code == 200, r_get.text
        body = r_get.json()
        assert body["count"] == 1, (
            f"B36 regression — expected count=1 immediately after POST, "
            f"got count={body['count']}. POSTed id={posted_id}."
        )
        assert body["items"][0]["id"] == posted_id, (
            "B36 regression — list returned a different attachment than the "
            "one just POSTed."
        )
        assert body["items"][0]["original_filename"] == "b36.pdf"
        assert body["items"][0]["file_type"] == "application/pdf"
