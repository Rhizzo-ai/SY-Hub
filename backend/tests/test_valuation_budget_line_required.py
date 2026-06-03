"""Build Pack 2.6-FIX (Chat 39) §R5 — A4 tests.

``certify_valuation`` must REQUIRE an explicit ``budget_line_id``; the
silent ``LIMIT 1`` first-line guess in
``_pick_budget_line_for_subcontract`` has been removed.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, text

from tests._sc_valuations_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, PWD,
    certify_valuation, create_valuation, make_active_subcontract,
    make_subcontractor, seed_budget_for_project, set_cis_status_for_supplier,
    submit_valuation, wipe_2_8b,
)
from tests._subcontracts_common import make_entity_and_project
from tests.conftest import login_with_auto_enroll


@pytest.fixture(scope="module")
def db_engine():
    eng = create_engine(DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture(scope="module", autouse=True)
def _wipe_module(db_engine):
    wipe_2_8b(db_engine)
    yield
    wipe_2_8b(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_threshold(db_engine, admin):
    """Lift self-approval threshold above test sums so admin can both
    create AND activate the seed budget (mirrors
    test_subcontract_valuations_api.py's fixture)."""
    from app.services import system_config as sc_svc
    key = sc_svc.BUDGET_SELF_APPROVAL_THRESHOLD_KEY
    admin.put(
        f"{BASE_URL}/api/v1/system-config/{key}",
        json={"value": "999999999.00"},
    )


@pytest.fixture(scope="module")
def project_id(admin):
    _, pid = make_entity_and_project(admin, name_prefix="A4 BLID")
    return pid


@pytest.fixture(scope="module")
def budget_line_id(admin, project_id):
    """Seed the budget so we have a real line id to pass."""
    return seed_budget_for_project(admin, project_id)


@pytest.fixture(scope="module")
def sub_id(admin):
    sid = make_subcontractor(admin)
    set_cis_status_for_supplier(sid, "Net")
    return sid


@pytest.fixture
def submitted_val(admin, project_id, budget_line_id, sub_id):
    """Fresh Submitted valuation per test (certify consumes it)."""
    sc = make_active_subcontract(
        admin, project_id=project_id, subcontractor_id=sub_id,
        original_contract_sum="100000.00", retention_pct="5.00",
    )
    r = create_valuation(
        admin, subcontract_id=sc["id"],
        gross_applied_to_date="1000.00",
        labour_portion="1000.00", materials_portion="0.00",
    )
    assert r.status_code == 201, r.text
    val_id = r.json()["id"]
    submit_valuation(admin, val_id)
    return val_id


# ---------------------------------------------------------------------------
# Test #8 — 422 when budget_line_id omitted
# ---------------------------------------------------------------------------

def test_certify_without_budget_line_id_returns_422(admin, submitted_val):
    """A4 #8 — omit ``budget_line_id`` → 422 with a helpful message.

    Pydantic now declares the field required; FastAPI returns 422
    automatically. We assert both the status and that the response
    body identifies the missing field so a caller can self-diagnose.
    """
    r = admin.post(
        f"{BASE_URL}/api/v1/subcontract-valuations/{submitted_val}/certify",
        json={},  # no budget_line_id, no description, no transaction_date
    )
    assert r.status_code == 422, r.text
    body = r.json()
    # FastAPI's default 422 body is `{detail: [{loc, msg, type, ...}]}`.
    blob = str(body).lower()
    assert "budget_line_id" in blob, (
        f"422 should call out the missing budget_line_id field; got {body!r}"
    )


# ---------------------------------------------------------------------------
# Test #9 — explicit budget_line_id is honoured (no arbitrary picking)
# ---------------------------------------------------------------------------

def test_certify_with_explicit_budget_line_posts_to_that_line(
    admin, submitted_val, budget_line_id, db_engine,
):
    """A4 #9 — when the caller passes a real ``budget_line_id``, the
    posted actual lands on THAT line (not an arbitrary first row).
    """
    r = admin.post(
        f"{BASE_URL}/api/v1/subcontract-valuations/{submitted_val}/certify",
        json={"budget_line_id": budget_line_id},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    posted_actual_id = body.get("posted_actual_id")
    assert posted_actual_id, f"certify response missing posted_actual_id: {body!r}"

    # Verify the actual was posted to the requested budget line.
    with db_engine.connect() as c:
        bl_id = c.execute(text(
            "SELECT budget_line_id FROM actuals WHERE id=:a"
        ), {"a": posted_actual_id}).scalar()
    assert str(bl_id) == str(budget_line_id), (
        f"Actual landed on line {bl_id} but caller asked for {budget_line_id}"
    )


# ---------------------------------------------------------------------------
# Test #10 — silent LIMIT-1 guess path is removed
# ---------------------------------------------------------------------------

def test_pick_budget_line_guess_path_removed():
    """A4 #10 — ``_pick_budget_line_for_subcontract`` must no longer
    silently return any line; calling it directly raises
    ``ValuationStateError`` (defensive shim so accidental
    reintroduction surfaces immediately).
    """
    from app.services.subcontract_valuations import (
        _pick_budget_line_for_subcontract, ValuationStateError,
    )
    # No real subcontract / session needed — the shim raises before any
    # DB read happens.
    with pytest.raises(ValuationStateError) as exc:
        _pick_budget_line_for_subcontract(db=None, sc=None)  # type: ignore[arg-type]
    assert "budget_line_id is required" in str(exc.value).lower()
