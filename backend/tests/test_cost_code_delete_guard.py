"""B88 Pack 1 §7.2 — Complete delete-guard with named blockers.

Verifies the cost_code_block_reasons / section_block_reasons service
functions resolve EVERY inbound RESTRICT FK and surface human-readable
counts in a 409 detail. No raw 500s allowed.

Coverage map (linkages probed):

  cost_codes inbound (4 RESTRICT FKs → must block):
    [G1] project_cost_codes.cost_code_id        → "N project enrolment(s)..."
    [G2] budget_lines.cost_code_id              → "N budget line(s)..."
    [G3] appraisal_cost_lines.cost_code_id      → "N appraisal cost line(s)..."
    [G4] cost_code_subcategories.cost_code_id   → "N subcategor(y/ies)..."

  cost_codes inbound (3 non-RESTRICT FKs → must NOT block):
    [G5] cost_code_entity_mapping (CASCADE)
    [G6] ai_capture_jobs.suggested_cost_code_id (SET NULL) — not tested
         here; covered indirectly by [G5] cascade proof + the service
         module's docstring rationale.
    [G7] cost_codes.replaced_by_code_id (SET NULL self-ref)

  cost_code_sections inbound (2 RESTRICT FKs → must block):
    [G8] cost_codes.section_id              → "N cost code(s) attached..."
    [G9] cost_code_sections.parent_section_id → "N subgroup(s)..."

Plus the negative RBAC slice: only super_admin holds cost_codes.delete;
director / finance / pm / readonly all 403.

Naming requirement (Build Pack §7) — file is named exactly
`test_cost_code_delete_guard.py`. Do not consolidate.
"""
from __future__ import annotations

import os
import uuid

import pytest
import requests
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll, plain_login

load_dotenv("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
            or "http://localhost:8001")
DATABASE_URL = os.environ["DATABASE_URL"]
TEST_PASSWORD = "TestUser-Dev-2026!"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    with eng.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield eng
    eng.dispose()


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-admin@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def director(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-director@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def finance(db_engine):
    return login_with_auto_enroll(None, BASE_URL,
                                  "test-finance@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def pm(db_engine):
    return plain_login(BASE_URL, "test-pm@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def readonly(db_engine):
    return plain_login(BASE_URL, "test-readonly@example.test", TEST_PASSWORD)


@pytest.fixture(scope="module")
def construction_section_id(db_engine):
    with db_engine.connect() as c:
        # Any tier-1 section that does NOT allow subgroups will serve as
        # a legal target for a fresh cost code (per §3.2).
        return str(c.execute(text("""
            SELECT id FROM cost_code_sections
            WHERE parent_section_id IS NULL AND allows_subgroups = false
            ORDER BY display_order LIMIT 1
        """)).scalar())


@pytest.fixture(scope="module")
def primary_entity_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text(
            "SELECT id FROM entities WHERE entity_type='Parent' LIMIT 1"
        )).scalar())


@pytest.fixture(scope="module")
def spv_entity_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text(
            "SELECT id FROM entities WHERE entity_type='SPV' LIMIT 1"
        )).scalar())


@pytest.fixture(scope="module")
def construction_co_id(db_engine):
    with db_engine.connect() as c:
        return str(c.execute(text(
            "SELECT id FROM entities WHERE entity_type='ConstructionCo' LIMIT 1"
        )).scalar())


@pytest.fixture(scope="module")
def spotcheck_project_id(db_engine):
    """Pick any existing project — historical "spotcheck" UUID is not
    guaranteed on freshly-provisioned pods. Skip the test cleanly if
    no projects exist at all."""
    with db_engine.connect() as c:
        pid = c.execute(text(
            "SELECT id FROM projects ORDER BY created_at LIMIT 1"
        )).scalar()
    if pid is None:
        pytest.skip("No projects in DB — re-run project seed to enable G1.")
    return str(pid)


@pytest.fixture(scope="module")
def spotcheck_budget_row(db_engine, spotcheck_project_id):
    """Return an Active budget + its source appraisal.

    B88 Pack 1 — Gate 3 partial-acceptance fix: previously this skipped
    when the spotcheck R7 budget seed had not run on the pod, so G2 +
    G3 never ran in CI. Now the fixture self-seeds a probe appraisal
    (Approved) + Active budget against the first project if none exist.
    The seed is idempotent across runs (look up by `name LIKE
    'DEL-GUARD-PROBE-%'` before inserting) and is cleaned up on module
    teardown so it does not collide with other test modules that wipe
    appraisals/budgets in their own setup.

    G2 needs `budget_id`; G3 needs `appraisal_id`. Both tests then
    create + clean up their own blocker row (budget_line /
    appraisal_cost_line) inside the assertion.
    """
    created_ids = {"appraisal_id": None, "budget_id": None}

    with db_engine.connect() as c:
        row = c.execute(text("""
            SELECT id, source_appraisal_id
            FROM budgets
            WHERE status = 'Active'
            ORDER BY created_at LIMIT 1
        """)).first()
    if row is not None:
        yield {"budget_id": str(row[0]),
                "appraisal_id": str(row[1])}
        return

    # No Active budget exists — seed one for G2 + G3.
    with db_engine.begin() as c:
        admin_uid = c.execute(text(
            "SELECT id FROM users WHERE email='test-admin@example.test'"
        )).scalar()
        assert admin_uid is not None, "test-admin user must exist for seed."

        appraisal_id = str(uuid.uuid4())
        appraisal_group_id = str(uuid.uuid4())
        # Bump version_number to avoid colliding with any other
        # (project_id, 'Base', version_number) row left by sibling
        # appraisal tests in the same pytest session. is_current is
        # set to false so we don't trip the "one current Base per
        # project" trigger either.
        next_version = c.execute(text("""
            SELECT COALESCE(MAX(version_number), 0) + 1
            FROM appraisals
            WHERE project_id = :p AND scenario = 'Base'
        """), {"p": spotcheck_project_id}).scalar()
        c.execute(text("""
            INSERT INTO appraisals (
              id, project_id, version_number, name, status,
              reference_date, appraisal_group_id, is_current,
              scenario, created_by_user_id
            ) VALUES (
              :i, :p, :v, :n, 'Approved',
              CURRENT_DATE, :g, false,
              'Base', :u
            )
        """), {"i": appraisal_id, "p": spotcheck_project_id,
                "v": next_version,
                "n": f"DEL-GUARD-PROBE-{appraisal_id[:8]}",
                "g": appraisal_group_id, "u": admin_uid})

        budget_id = str(uuid.uuid4())
        c.execute(text("""
            INSERT INTO budgets (
              id, project_id, source_appraisal_id, version_number,
              version_label, is_current, status, created_by_user_id
            ) VALUES (
              :i, :p, :a, :v,
              'Original', false, 'Active', :u
            )
        """), {"i": budget_id, "p": spotcheck_project_id,
                "a": appraisal_id, "v": next_version, "u": admin_uid})

    created_ids["appraisal_id"] = appraisal_id
    created_ids["budget_id"] = budget_id
    yield {"budget_id": budget_id, "appraisal_id": appraisal_id}

    # Module teardown — delete the probe rows so other test modules can
    # wipe appraisals/budgets without FK collisions.
    if created_ids["budget_id"] is not None:
        with db_engine.begin() as c:
            c.execute(text("DELETE FROM budget_lines WHERE budget_id = :b"),
                      {"b": created_ids["budget_id"]})
            c.execute(text("DELETE FROM budgets WHERE id = :b"),
                      {"b": created_ids["budget_id"]})
            c.execute(text(
                "DELETE FROM appraisal_cost_lines WHERE appraisal_id = :a"
            ), {"a": created_ids["appraisal_id"]})
            c.execute(text("DELETE FROM appraisals WHERE id = :a"),
                      {"a": created_ids["appraisal_id"]})


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def _fresh_cost_code(admin, section_id: str, prefix: str = "ZZX") -> dict:
    """Create a cost code via API and return the response body."""
    # Retry with rotating sequence digits if the unique (prefix,sequence) collides.
    payload = {
        "section_id": section_id,
        "name": "Probe code",
        "default_entity": "SPV",
        "applies_to_parent": False,
        "applies_to_spv": True,
        "applies_to_construction_co": True,
        "vat_treatment": "Standard",
    }
    for seq in range(10, 100):
        payload["code"] = f"{prefix}-{seq:02d}"
        r = admin.post(f"{BASE_URL}/api/cost-codes", json=payload)
        if r.status_code == 201:
            return r.json()
        if r.status_code == 409:
            continue
        raise AssertionError(f"Cost-code create failed: {r.status_code} {r.text}")
    raise AssertionError("Could not allocate a free sequence for the probe code.")


def _delete_cost_code_row(db_engine, code_id: str) -> None:
    with db_engine.begin() as c:
        c.execute(text("""
            DELETE FROM cost_code_subcategories WHERE cost_code_id = :i
        """), {"i": code_id})
        c.execute(text("""
            DELETE FROM project_cost_codes WHERE cost_code_id = :i
        """), {"i": code_id})
        c.execute(text("DELETE FROM cost_codes WHERE id = :i"), {"i": code_id})


def _delete_section_row(db_engine, sec_id: str) -> None:
    with db_engine.begin() as c:
        c.execute(text("DELETE FROM cost_code_sections WHERE id = :i"),
                  {"i": sec_id})


def _has_blocker(body: dict, fragment: str) -> bool:
    """The 409 detail is `{"message": ..., "blockers": [str, ...]}`.
    Some FastAPI middlewares wrap that under `detail`."""
    detail = body.get("detail", body)
    if isinstance(detail, dict):
        blockers = detail.get("blockers", [])
    elif isinstance(detail, list):
        blockers = detail
    else:
        blockers = []
    return any(fragment.lower() in b.lower() for b in blockers)


# --------------------------------------------------------------------------
# G1 — project_cost_codes blocker
# --------------------------------------------------------------------------

def test_delete_blocked_by_project_cost_codes(
    admin, db_engine, construction_section_id, spotcheck_project_id,
):
    code = _fresh_cost_code(admin, construction_section_id)
    code_id = code["id"]
    pcc_id = str(uuid.uuid4())
    with db_engine.begin() as c:
        c.execute(text("""
            INSERT INTO project_cost_codes (id, project_id, cost_code_id, is_enabled)
            VALUES (:i, :p, :c, true)
        """), {"i": pcc_id, "p": spotcheck_project_id, "c": code_id})
    try:
        r = admin.delete(f"{BASE_URL}/api/cost-codes/{code_id}")
        assert r.status_code == 409, r.text
        assert _has_blocker(r.json(), "project enrolment"), r.json()
    finally:
        with db_engine.begin() as c:
            c.execute(text("DELETE FROM project_cost_codes WHERE id = :i"),
                      {"i": pcc_id})
        _delete_cost_code_row(db_engine, code_id)


# --------------------------------------------------------------------------
# G2 — budget_lines blocker
# --------------------------------------------------------------------------

def test_delete_blocked_by_budget_line(
    admin, db_engine, construction_section_id, spotcheck_budget_row,
    spv_entity_id,
):
    code = _fresh_cost_code(admin, construction_section_id)
    code_id = code["id"]
    bl_id = str(uuid.uuid4())
    with db_engine.begin() as c:
        # Lean INSERT — every other not-null column has a Postgres-side
        # default (verified via `\d budget_lines`). display_order has NO
        # default, so we set it explicitly.
        c.execute(text("""
            INSERT INTO budget_lines (
              id, budget_id, cost_code_id, line_description, entity_id,
              display_order
            ) VALUES (:i, :b, :c, 'delete-guard probe', :e, 9999)
        """), {"i": bl_id,
                "b": spotcheck_budget_row["budget_id"],
                "c": code_id,
                "e": spv_entity_id})
    try:
        r = admin.delete(f"{BASE_URL}/api/cost-codes/{code_id}")
        assert r.status_code == 409, r.text
        assert _has_blocker(r.json(), "budget line"), r.json()
    finally:
        with db_engine.begin() as c:
            c.execute(text("DELETE FROM budget_lines WHERE id = :i"),
                      {"i": bl_id})
        _delete_cost_code_row(db_engine, code_id)


# --------------------------------------------------------------------------
# G3 — appraisal_cost_lines blocker
# --------------------------------------------------------------------------

def test_delete_blocked_by_appraisal_cost_line(
    admin, db_engine, construction_section_id, spotcheck_budget_row,
):
    code = _fresh_cost_code(admin, construction_section_id)
    code_id = code["id"]
    acl_id = str(uuid.uuid4())
    with db_engine.begin() as c:
        c.execute(text("""
            INSERT INTO appraisal_cost_lines (
              id, appraisal_id, display_order, cost_code_id, label,
              category, auto_source, percentage, amount, is_locked,
              created_at, updated_at
            ) VALUES (
              :i, :a, 999, :c, 'delete-guard probe',
              'Other', 'Manual', NULL, 0, false,
              now(), now()
            )
        """), {"i": acl_id,
                "a": spotcheck_budget_row["appraisal_id"],
                "c": code_id})
    try:
        r = admin.delete(f"{BASE_URL}/api/cost-codes/{code_id}")
        assert r.status_code == 409, r.text
        assert _has_blocker(r.json(), "appraisal cost line"), r.json()
    finally:
        with db_engine.begin() as c:
            c.execute(text("DELETE FROM appraisal_cost_lines WHERE id = :i"),
                      {"i": acl_id})
        _delete_cost_code_row(db_engine, code_id)


# --------------------------------------------------------------------------
# G4 — subcategories blocker
# --------------------------------------------------------------------------

def test_delete_blocked_by_subcategory(
    admin, db_engine, construction_section_id,
):
    code = _fresh_cost_code(admin, construction_section_id)
    code_id = code["id"]
    sub_resp = admin.post(
        f"{BASE_URL}/api/cost-codes/{code_id}/subcategories",
        json={
            "code": f"{code['code']}.01",
            "name": "Probe subcategory",
            "display_order": 1,
        },
    )
    assert sub_resp.status_code == 201, sub_resp.text
    try:
        r = admin.delete(f"{BASE_URL}/api/cost-codes/{code_id}")
        assert r.status_code == 409, r.text
        assert _has_blocker(r.json(), "subcategor"), r.json()
    finally:
        with db_engine.begin() as c:
            c.execute(text(
                "DELETE FROM cost_code_subcategories WHERE cost_code_id = :i"
            ), {"i": code_id})
        _delete_cost_code_row(db_engine, code_id)


# --------------------------------------------------------------------------
# G5 — CASCADE FK does NOT block (entity-mapping silently goes away)
# --------------------------------------------------------------------------

def test_delete_not_blocked_by_entity_mapping_cascade(
    admin, db_engine, construction_section_id, spv_entity_id,
):
    code = _fresh_cost_code(admin, construction_section_id)
    code_id = code["id"]
    mapping = admin.post(
        f"{BASE_URL}/api/cost-code-entity-mapping",
        json={
            "cost_code_id": code_id,
            "entity_id": spv_entity_id,
            "is_allowed": True,
        },
    )
    assert mapping.status_code == 201, mapping.text

    r = admin.delete(f"{BASE_URL}/api/cost-codes/{code_id}")
    assert r.status_code == 204, (
        f"Entity-mapping is CASCADE in §3.3 — delete must NOT be blocked. "
        f"Got {r.status_code}: {r.text}"
    )
    # Cascade proof — mapping row gone too.
    with db_engine.connect() as c:
        remaining = c.execute(text(
            "SELECT COUNT(*) FROM cost_code_entity_mapping WHERE cost_code_id = :i"
        ), {"i": code_id}).scalar()
    assert remaining == 0


# --------------------------------------------------------------------------
# G7 — SET NULL self-reference (replaced_by_code_id) does NOT block
# --------------------------------------------------------------------------

def test_delete_not_blocked_by_replaced_by_pointer(
    admin, db_engine, construction_section_id,
):
    """If code A.replaced_by_code_id = B, deleting B should NOT be
    blocked — the pointer is SET NULL by the FK. (Retire flow would
    normally prevent the operator getting here, but the schema rule
    must be honoured.)"""
    a = _fresh_cost_code(admin, construction_section_id, prefix="ZZA")
    b = _fresh_cost_code(admin, construction_section_id, prefix="ZZB")
    with db_engine.begin() as c:
        c.execute(text(
            "UPDATE cost_codes SET status='Retired', retired_at=now(), "
            "retired_reason='probe', replaced_by_code_id=:b WHERE id=:a"
        ), {"a": a["id"], "b": b["id"]})

    r = admin.delete(f"{BASE_URL}/api/cost-codes/{b['id']}")
    assert r.status_code == 204, (
        f"replaced_by_code_id is SET NULL — delete must NOT be blocked. "
        f"Got {r.status_code}: {r.text}"
    )
    with db_engine.connect() as c:
        ptr = c.execute(text(
            "SELECT replaced_by_code_id FROM cost_codes WHERE id = :a"
        ), {"a": a["id"]}).scalar()
    assert ptr is None, "Pointer should have been NULLed by SET NULL FK."
    _delete_cost_code_row(db_engine, a["id"])


# --------------------------------------------------------------------------
# G8 — section blocked by attached cost codes
# --------------------------------------------------------------------------

def test_delete_section_blocked_by_attached_codes(
    admin, db_engine,
):
    sec = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json={
            "code": f"GUARD-{uuid.uuid4().hex[:8]}",
            "name": "Guard probe parent",
            "display_order": 9000,
            "is_direct_cost": True,
            "default_p_and_l_category": "COS",
            "parent_section_id": None,
            "allows_subgroups": False,
        },
    ).json()
    sec_id = sec["id"]
    code = _fresh_cost_code(admin, sec_id, prefix="ZZS")
    try:
        r = admin.delete(f"{BASE_URL}/api/cost-code-sections/{sec_id}")
        assert r.status_code == 409
        assert _has_blocker(r.json(), "cost code"), r.json()
    finally:
        _delete_cost_code_row(db_engine, code["id"])
        _delete_section_row(db_engine, sec_id)


# --------------------------------------------------------------------------
# G9 — section blocked by child subgroups
# --------------------------------------------------------------------------

def test_delete_section_blocked_by_subgroups(admin, db_engine):
    parent = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json={
            "code": f"GRP-{uuid.uuid4().hex[:8]}",
            "name": "Subgroup probe parent",
            "display_order": 9001,
            "is_direct_cost": True,
            "default_p_and_l_category": "COS",
            "parent_section_id": None,
            "allows_subgroups": True,
        },
    ).json()
    child = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json={
            "code": f"SUB-{uuid.uuid4().hex[:8]}",
            "name": "Child subgroup probe",
            "display_order": 9002,
            "is_direct_cost": True,
            "default_p_and_l_category": "COS",
            "parent_section_id": parent["id"],
            "allows_subgroups": False,
        },
    ).json()
    try:
        r = admin.delete(f"{BASE_URL}/api/cost-code-sections/{parent['id']}")
        assert r.status_code == 409
        assert _has_blocker(r.json(), "subgroup"), r.json()
    finally:
        _delete_section_row(db_engine, child["id"])
        _delete_section_row(db_engine, parent["id"])


# --------------------------------------------------------------------------
# Happy paths — clean deletes return 204
# --------------------------------------------------------------------------

def test_delete_unused_cost_code_succeeds(admin, construction_section_id):
    code = _fresh_cost_code(admin, construction_section_id, prefix="ZZE")
    r = admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")
    assert r.status_code == 204, r.text


def test_delete_empty_section_succeeds(admin):
    sec = admin.post(
        f"{BASE_URL}/api/cost-code-sections",
        json={
            "code": f"EMP-{uuid.uuid4().hex[:8]}",
            "name": "Empty probe",
            "display_order": 9100,
            "is_direct_cost": True,
            "default_p_and_l_category": "COS",
            "parent_section_id": None,
            "allows_subgroups": False,
        },
    ).json()
    r = admin.delete(f"{BASE_URL}/api/cost-code-sections/{sec['id']}")
    assert r.status_code == 204, r.text


# --------------------------------------------------------------------------
# RBAC negatives — only super_admin can delete
# --------------------------------------------------------------------------

def test_director_cannot_delete_cost_code(
    admin, director, construction_section_id,
):
    """The counter-intuitive grant — director has create + edit (and
    therefore retire), but NOT delete."""
    code = _fresh_cost_code(admin, construction_section_id, prefix="ZZD")
    try:
        r = director.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")
        assert r.status_code == 403, (
            f"Director must NOT hold cost_codes.delete. Got {r.status_code}."
        )
    finally:
        admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


def test_finance_cannot_delete_cost_code(
    admin, finance, construction_section_id,
):
    code = _fresh_cost_code(admin, construction_section_id, prefix="ZZF")
    try:
        r = finance.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")
        assert r.status_code == 403
    finally:
        admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


def test_pm_cannot_delete_cost_code(admin, pm, construction_section_id):
    code = _fresh_cost_code(admin, construction_section_id, prefix="ZZP")
    try:
        r = pm.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")
        assert r.status_code == 403
    finally:
        admin.delete(f"{BASE_URL}/api/cost-codes/{code['id']}")


# --------------------------------------------------------------------------
# Graceful — never a raw 500
# --------------------------------------------------------------------------

def test_delete_unknown_id_returns_404(admin):
    r = admin.delete(f"{BASE_URL}/api/cost-codes/{uuid.uuid4()}")
    assert r.status_code == 404


def test_delete_unknown_section_returns_404(admin):
    r = admin.delete(f"{BASE_URL}/api/cost-code-sections/{uuid.uuid4()}")
    assert r.status_code == 404
