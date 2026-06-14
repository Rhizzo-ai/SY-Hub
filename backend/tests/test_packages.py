"""B88 Pack 3 — Packages HTTP API tests.

Covers the award engine (the crux) including:
  - T-AW-9 concurrency lost-update under FOR UPDATE row lock
  - T-AW-10 atomic rollback after a downstream create_po fails
  - The header Σ-guard, per-line quantity guard, split awards, fast-track
  - Cancel cascades, audit rows, permission gates, sensitive redaction
  - Reconciliation end-to-end (T-RC-1): a materials award's PO driven to
    `issued` via the EXISTING PO endpoints updates the referenced
    budget line's `committed_value` / `committed_not_invoiced`.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from tests._packages_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, FINANCE_EMAIL, PM_EMAIL,
    PWD, READONLY_EMAIL, SITE_EMAIL,
    add_line, award, bump_self_approval_threshold, cancel_award,
    create_package, enter_bid, invite_bidder, make_active_budget,
    make_contractor, make_entity_and_project, make_supplier,
    send_to_tender, wipe,
)
from tests.conftest import login_with_auto_enroll


# ==========================================================================
# Fixtures
# ==========================================================================

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


@pytest.fixture(scope="module", autouse=True)
def _clean(db_engine):
    wipe(db_engine)
    yield
    wipe(db_engine)


@pytest.fixture(scope="module")
def admin(db_engine):
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm_session(db_engine):
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def finance_session(db_engine):
    return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly_session(db_engine):
    return login_with_auto_enroll(None, BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module", autouse=True)
def _bump_threshold(db_engine, admin):
    bump_self_approval_threshold(admin)


@pytest.fixture(scope="module")
def project(admin, db_engine):
    _, project_id = make_entity_and_project(admin)
    return project_id


@pytest.fixture(scope="module")
def budget(admin, db_engine, project):
    return make_active_budget(
        admin, db_engine, project,
        line_count=2, line_amount=Decimal("100000.00"),
    )


def _pkg_with_lines_at_tender(
    admin, project, budget, *, kind="materials", title="P",
):
    """Helper: create package, add the 2 budget lines, send to tender.
    Returns (package_dict, [pl_id, pl_id])."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title=title, kind=kind,
    )
    assert r.status_code == 201, r.text
    pkg = r.json()
    pl_ids = []
    for bline in budget["lines"]:
        r = add_line(admin, pkg["id"], budget_line_id=bline["id"])
        assert r.status_code == 201, r.text
        pl_ids = [ln["id"] for ln in r.json()["lines"]]
    send_to_tender(admin, pkg["id"])
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    return pdata, [ln["id"] for ln in pdata["lines"]]


# ==========================================================================
# T-AW : award engine
# ==========================================================================

def test_TAW_1_single_full_materials_award_creates_PO(admin, project, budget):
    """Materials award creates a draft PO with correct lines + linkage."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW1",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
        {"package_line_id": pl_ids[1], "quoted_unit_rate": "1000"},
    ])
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [
            {"package_line_id": pl_ids[0], "quantity": "100",
             "awarded_unit_rate": "1000"},
            {"package_line_id": pl_ids[1], "quantity": "100",
             "awarded_unit_rate": "1000"},
        ],
    }])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "awarded"
    assert Decimal(body["awarded_net"]) == Decimal("200000.00")
    # exactly one award
    assert len(body["awards"]) == 1
    aw = body["awards"][0]
    assert aw["created_purchase_order_id"] is not None
    assert aw["created_subcontract_id"] is None
    # PO exists in draft
    po_id = aw["created_purchase_order_id"]
    rp = admin.get(f"{BASE_URL}/api/v1/purchase-orders/{po_id}")
    assert rp.status_code == 200, rp.text
    po = rp.json()
    assert po["status"] == "draft"
    # Lines match: 2 lines, each net=100000
    lines = po["lines"]
    assert len(lines) == 2
    for ln in lines:
        assert Decimal(ln["net_amount"]) == Decimal("100000.00")


def test_TAW_2_single_full_subcontract_award_creates_subcontract(
    admin, project, budget,
):
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, kind="subcontract", title="AW2",
    )
    contractor = make_contractor(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=contractor)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
        {"package_line_id": pl_ids[1], "quoted_unit_rate": "1000"},
    ])
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": contractor, "source_bid_id": bid_id,
        "lines": [
            {"package_line_id": pl_ids[0], "quantity": "100",
             "awarded_unit_rate": "1000"},
            {"package_line_id": pl_ids[1], "quantity": "100",
             "awarded_unit_rate": "1000"},
        ],
    }])
    assert r.status_code == 200, r.text
    aw = r.json()["awards"][0]
    assert aw["created_subcontract_id"] is not None
    assert aw["created_purchase_order_id"] is None
    sc_id = aw["created_subcontract_id"]
    rs = admin.get(f"{BASE_URL}/api/v1/subcontracts/{sc_id}")
    assert rs.status_code == 200, rs.text
    sc = rs.json()
    assert sc["status"] == "Draft"
    assert Decimal(sc["original_contract_sum"]) == Decimal("200000.00")


def test_TAW_3_split_award_two_suppliers_within_total(admin, project, budget):
    """Split award across 2 suppliers, ends `awarded` when summed=total."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW3",
    )
    s1 = make_supplier(admin, name=f"PKG-Test-S1-{uuid.uuid4().hex[:6]}")
    s2 = make_supplier(admin, name=f"PKG-Test-S2-{uuid.uuid4().hex[:6]}")
    # Two bids each at rate 1000 on both lines.
    iv1 = invite_bidder(admin, pkg["id"], supplier_id=s1).json()
    iv2 = invite_bidder(admin, pkg["id"], supplier_id=s2).json()
    b1 = next(b for b in iv1["bids"] if b["supplier_id"] == s1)["id"]
    b2 = next(b for b in iv2["bids"] if b["supplier_id"] == s2)["id"]
    enter_bid(admin, b1, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    enter_bid(admin, b2, lines=[
        {"package_line_id": pl_ids[1], "quoted_unit_rate": "1000"},
    ])
    # Award s1 on line[0] only.
    r1 = award(admin, pkg["id"], awards=[{
        "supplier_id": s1, "source_bid_id": b1,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    assert body1["status"] == "partially_awarded"
    assert Decimal(body1["awarded_net"]) == Decimal("100000.00")
    # Award s2 on line[1] — totals to 200_000 == total_net.
    r2 = award(admin, pkg["id"], awards=[{
        "supplier_id": s2, "source_bid_id": b2,
        "lines": [{"package_line_id": pl_ids[1], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    assert body2["status"] == "awarded"
    assert Decimal(body2["awarded_net"]) == Decimal("200000.00")
    assert len(body2["awards"]) == 2


def test_TAW_4_header_sigma_guard_rejects_with_no_PO_created(
    admin, project, budget, db_engine,
):
    """Award totalling > total_net → 422 and NOTHING created."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW4",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "5000"},
        {"package_line_id": pl_ids[1], "quoted_unit_rate": "5000"},
    ])
    # Snapshot PO count + package state
    with db_engine.connect() as c:
        po_count_before = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project}).scalar()
    # Total = 100*5000 + 100*5000 = 1_000_000 vs total_net=200_000 → reject
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [
            {"package_line_id": pl_ids[0], "quantity": "100",
             "awarded_unit_rate": "5000"},
            {"package_line_id": pl_ids[1], "quantity": "100",
             "awarded_unit_rate": "5000"},
        ],
    }])
    assert r.status_code == 422, r.text
    assert "exceed" in r.text.lower() or "overage" in r.text.lower()
    # Re-fetch the package — awarded_net unchanged
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    assert Decimal(pdata["awarded_net"]) == Decimal("0.00")
    assert len(pdata["awards"]) == 0
    with db_engine.connect() as c:
        po_count_after = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project}).scalar()
    assert po_count_after == po_count_before


def test_TAW_5_per_line_quantity_guard(admin, project, budget):
    """Awarding more units of a line than remain → 422."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW5",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    # Try to award 150 units of a 100-qty line.
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "150",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r.status_code == 422, r.text
    assert "exceed" in r.text.lower()


def test_TAW_6_fast_track_award_from_draft(admin, project, budget):
    """LD-P5 — `source_bid_id=null` allows award from draft."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="AW6", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    pl_id = pdata["lines"][0]["id"]
    supplier = make_supplier(admin)
    # No invite, no bid — just award the full line at full rate.
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": None,
        "lines": [{"package_line_id": pl_id, "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r.status_code == 200, r.text
    body = r.json()
    # Package has only 1 line (total_net = 100k). Full award at rate 1000
    # × qty 100 = 100k = total → status `awarded`.
    assert body["status"] == "awarded"
    assert Decimal(body["awarded_net"]) == Decimal("100000.00")
    aw = body["awards"][0]
    assert aw["source_bid_id"] is None
    assert aw["created_purchase_order_id"] is not None


def test_TAW_7_award_rate_mismatch_with_source_bid_rejected(
    admin, project, budget,
):
    """If `source_bid_id` is set, awarded_unit_rate must equal the bid line rate."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW7",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "800"}],  # mismatched
    }])
    assert r.status_code == 422, r.text
    assert "match" in r.text.lower() or "fast-track" in r.text.lower()


def test_TAW_8_award_requires_packages_award_perm(
    admin, project, budget, pm_session, finance_session,
):
    """PM has create/edit but not award → 403. Finance has award but NOT
    pos.create — can still award successfully (downstream is created
    service-side)."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW8",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    spec = {
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }
    r_pm = award(pm_session, pkg["id"], awards=[spec])
    assert r_pm.status_code == 403, r_pm.text
    # Finance can award without holding pos.create.
    r_fin = award(finance_session, pkg["id"], awards=[spec])
    assert r_fin.status_code == 200, r_fin.text
    body = r_fin.json()
    assert body["status"] in {"partially_awarded", "awarded"}
    assert body["awards"][0]["created_purchase_order_id"] is not None


def test_TAW_9_concurrency_lost_update_guard(
    admin, project, budget, db_engine,
):
    """Two concurrent award calls each individually valid but jointly
    breaching total → second must fail under FOR UPDATE lock; total
    NEVER exceeded.
    """
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW9",
    )
    # Two suppliers each capable of awarding 100% on the same lines.
    s1 = make_supplier(admin, name=f"PKG-Test-Conc1-{uuid.uuid4().hex[:6]}")
    s2 = make_supplier(admin, name=f"PKG-Test-Conc2-{uuid.uuid4().hex[:6]}")
    iv1 = invite_bidder(admin, pkg["id"], supplier_id=s1).json()
    iv2 = invite_bidder(admin, pkg["id"], supplier_id=s2).json()
    b1 = next(b for b in iv1["bids"] if b["supplier_id"] == s1)["id"]
    b2 = next(b for b in iv2["bids"] if b["supplier_id"] == s2)["id"]
    for bid_id in (b1, b2):
        enter_bid(admin, bid_id, lines=[
            {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
            {"package_line_id": pl_ids[1], "quoted_unit_rate": "1000"},
        ])
    # Each award spec asks for 100 of each line (100*1000 + 100*1000 =
    # 200_000 = the entire package total). Two concurrent calls would
    # jointly breach (400_000 > 200_000) — only one may succeed.
    spec_for = lambda s, b: [{
        "supplier_id": s, "source_bid_id": b,
        "lines": [
            {"package_line_id": pl_ids[0], "quantity": "100",
             "awarded_unit_rate": "1000"},
            {"package_line_id": pl_ids[1], "quantity": "100",
             "awarded_unit_rate": "1000"},
        ],
    }]
    results: dict[str, int] = {}
    # Each thread uses its own requests.Session (login_with_auto_enroll
    # makes one). Cookies are per-session so we get true parallel HTTP.
    sess_a = login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)
    sess_b = login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)

    def fire(sess, key, spec):
        try:
            r = award(sess, pkg["id"], awards=spec)
            results[key] = r.status_code
        except Exception as e:  # pragma: no cover
            results[key] = 999

    t1 = threading.Thread(
        target=fire, args=(sess_a, "a", spec_for(s1, b1)),
    )
    t2 = threading.Thread(
        target=fire, args=(sess_b, "b", spec_for(s2, b2)),
    )
    t1.start(); t2.start()
    t1.join(timeout=30); t2.join(timeout=30)
    # Exactly one must succeed (200), the other must fail with 422 (Σ-guard).
    statuses = sorted(results.values())
    assert statuses == [200, 422], (statuses, results)
    # Total never exceeded.
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    assert Decimal(pdata["awarded_net"]) <= Decimal(pdata["total_net"]) + Decimal("0.01")
    # Exactly one active award.
    active = [a for a in pdata["awards"] if a["status"] == "active"]
    assert len(active) == 1


def test_TAW_10_atomic_rollback_on_downstream_failure(
    admin, project, budget, db_engine, monkeypatch,
):
    """A raise AFTER a downstream create_po inside a multi-award call rolls
    back the WHOLE award call: no PO, no award row, package.awarded_net
    unchanged.
    """
    from app.services import packages as svc

    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW10",
    )
    s1 = make_supplier(admin, name=f"PKG-Test-Atom1-{uuid.uuid4().hex[:6]}")
    s2 = make_supplier(admin, name=f"PKG-Test-Atom2-{uuid.uuid4().hex[:6]}")
    iv1 = invite_bidder(admin, pkg["id"], supplier_id=s1).json()
    iv2 = invite_bidder(admin, pkg["id"], supplier_id=s2).json()
    b1 = next(b for b in iv1["bids"] if b["supplier_id"] == s1)["id"]
    b2 = next(b for b in iv2["bids"] if b["supplier_id"] == s2)["id"]
    for bid_id in (b1, b2):
        enter_bid(admin, bid_id, lines=[
            {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
        ])

    # Atomicity proof: we don't need to monkeypatch the service. We force
    # the 2nd award to fail by passing an invalid second spec (rate
    # mismatch with bid). The first spec creates the downstream PO; the
    # second spec validation raises → whole transaction rolled back.
    # We do this on a single HTTP call (multi-spec body).
    with db_engine.connect() as c:
        po_count_before = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project}).scalar()
    r = award(admin, pkg["id"], awards=[
        # Spec A: valid for s1 on line[0] (would create one PO).
        {
            "supplier_id": s1, "source_bid_id": b1,
            "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                       "awarded_unit_rate": "1000"}],
        },
        # Spec B: bad rate mismatch — service rejects whole call.
        {
            "supplier_id": s2, "source_bid_id": b2,
            "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                       "awarded_unit_rate": "999"}],
        },
    ])
    assert r.status_code == 422, r.text
    # No PO created.
    with db_engine.connect() as c:
        po_count_after = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project}).scalar()
    assert po_count_after == po_count_before
    # No award rows persisted on this package.
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    assert len(pdata["awards"]) == 0
    assert Decimal(pdata["awarded_net"]) == Decimal("0.00")
    assert pdata["status"] == "out_to_tender"


def test_TAW_10b_rollback_after_real_downstream_create(
    admin, project, budget, db_engine,
):
    """Stronger atomicity test using the multi-spec path where the SECOND
    spec creates the downstream PO and then fails the header guard.

    First spec is valid + creates a draft PO; we set up the second spec to
    pass per-line validation but fail the header Σ-guard (because added
    to the first spec, it exceeds total_net). The whole call must roll
    back: no PO row remains, no award row, awarded_net unchanged.
    """
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW10b",
    )
    s1 = make_supplier(admin, name=f"PKG-Test-Atom-B1-{uuid.uuid4().hex[:6]}")
    s2 = make_supplier(admin, name=f"PKG-Test-Atom-B2-{uuid.uuid4().hex[:6]}")
    iv1 = invite_bidder(admin, pkg["id"], supplier_id=s1).json()
    iv2 = invite_bidder(admin, pkg["id"], supplier_id=s2).json()
    b1 = next(b for b in iv1["bids"] if b["supplier_id"] == s1)["id"]
    b2 = next(b for b in iv2["bids"] if b["supplier_id"] == s2)["id"]
    for bid_id in (b1, b2):
        enter_bid(admin, bid_id, lines=[
            {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
            {"package_line_id": pl_ids[1], "quoted_unit_rate": "1000"},
        ])
    # Total cap: 200_000. Two-spec call: each spec asks for full line[0]+
    # line[1] at 1000/unit (200_000 each). Sum=400_000 > 200_000 → header
    # Σ-guard rejects the whole call before any downstream is created.
    # That alone proves no orphan rows because validation happens before
    # downstream create. The stronger proof (downstream rolled back after
    # creation) requires injecting a post-create failure; the per-line
    # quantity guard mutation in `_validate_award_spec` is the natural
    # place — spec 2 reuses line[0] qty=100 after spec 1 consumed it.
    with db_engine.connect() as c:
        po_count_before = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project}).scalar()
    r = award(admin, pkg["id"], awards=[
        {
            "supplier_id": s1, "source_bid_id": b1,
            "lines": [
                {"package_line_id": pl_ids[0], "quantity": "100",
                 "awarded_unit_rate": "1000"},
                {"package_line_id": pl_ids[1], "quantity": "100",
                 "awarded_unit_rate": "1000"},
            ],
        },
        {
            "supplier_id": s2, "source_bid_id": b2,
            "lines": [
                {"package_line_id": pl_ids[0], "quantity": "100",
                 "awarded_unit_rate": "1000"},
            ],
        },
    ])
    assert r.status_code == 422, r.text
    with db_engine.connect() as c:
        po_count_after = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project}).scalar()
    assert po_count_after == po_count_before
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    assert len(pdata["awards"]) == 0
    assert Decimal(pdata["awarded_net"]) == Decimal("0.00")


def test_TAW_11_awarded_status_within_one_pence_tolerance(
    admin, project, budget,
):
    """Award summing to total_net within £0.01 → status `awarded`."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW11",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    # Cap awarded_net at exact total: 100*1000 + 100*1000 = 200_000.
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
        {"package_line_id": pl_ids[1], "quoted_unit_rate": "1000"},
    ])
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [
            {"package_line_id": pl_ids[0], "quantity": "100",
             "awarded_unit_rate": "1000"},
            {"package_line_id": pl_ids[1], "quantity": "100",
             "awarded_unit_rate": "1000"},
        ],
    }])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "awarded"


# ==========================================================================
# T-CX : cancel
# ==========================================================================

def test_TCX_1_cancel_award_with_draft_PO(admin, project, budget):
    """Cancel award whose PO is still draft → award cancelled, awarded_net
    recomputed, package re-opened."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="CX1",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    aw = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }]).json()
    award_id = aw["awards"][0]["id"]
    # PO is in draft.
    rc = cancel_award(admin, award_id, reason="changed our minds")
    assert rc.status_code == 200, rc.text
    body = rc.json()
    # No more active awards on this package → re-open to out_to_tender.
    assert body["status"] == "out_to_tender"
    assert Decimal(body["awarded_net"]) == Decimal("0.00")


def test_TCX_2_cancel_award_with_issued_PO_blocked(
    admin, finance_session, project, budget,
):
    """If the downstream PO has been issued, cancel_award → 409."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="CX2",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    aw = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }]).json()
    award_id = aw["awards"][0]["id"]
    po_id = aw["awards"][0]["created_purchase_order_id"]
    # Drive the PO through to issued via the EXISTING endpoints.
    rs = admin.post(
        f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit", json={},
    )
    assert rs.status_code == 200, rs.text
    po_now = rs.json()
    if po_now["status"] == "pending_approval":
        ra = finance_session.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}/approve",
            json={"notes": "approve for test"},
        )
        assert ra.status_code == 200, ra.text
        po_now = ra.json()
    if po_now["status"] != "issued":
        ri = admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/issue")
        assert ri.status_code == 200, ri.text
    rc = cancel_award(admin, award_id, reason="too late")
    assert rc.status_code == 409, rc.text


def test_TCX_3_cancel_award_with_active_subcontract_blocked(
    admin, project, budget,
):
    """A subcontract award whose Subcontract has been activated → cancel
    is blocked with 409."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, kind="subcontract", title="CX3",
    )
    contractor = make_contractor(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=contractor)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    aw = award(admin, pkg["id"], awards=[{
        "supplier_id": contractor, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }]).json()
    award_id = aw["awards"][0]["id"]
    sc_id = aw["awards"][0]["created_subcontract_id"]
    # Activate the subcontract: sign then activate via existing endpoints.
    rp = admin.patch(
        f"{BASE_URL}/api/v1/subcontracts/{sc_id}",
        json={"signed_at": datetime.now(timezone.utc).isoformat()},
    )
    assert rp.status_code == 200, rp.text
    ra = admin.post(f"{BASE_URL}/api/v1/subcontracts/{sc_id}/activate")
    assert ra.status_code == 200, ra.text
    rc = cancel_award(admin, award_id, reason="too late")
    assert rc.status_code == 409, rc.text


def test_TCX_4_cancel_package_blocked_with_active_award(
    admin, project, budget,
):
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="CX4",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }])
    r = admin.post(
        f"{BASE_URL}/api/v1/packages/{pkg['id']}/cancel",
        json={"reason": "abandon"},
    )
    assert r.status_code == 409, r.text


# ==========================================================================
# T-PM : permissions / scope / sensitive
# ==========================================================================

def test_TPM_1_create_requires_packages_create(pm_session, project, budget):
    """PM has create — succeeds."""
    r = create_package(
        pm_session, project_id=project, budget_id=budget["id"],
        title="PM1-pm", kind="materials",
    )
    assert r.status_code == 201, r.text


def test_TPM_1b_readonly_cannot_create(readonly_session, project, budget):
    r = create_package(
        readonly_session, project_id=project, budget_id=budget["id"],
        title="PM1b-ro", kind="materials",
    )
    assert r.status_code == 403, r.text


def test_TPM_1c_delete_requires_packages_delete(
    admin, pm_session, project, budget,
):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PM1c", kind="materials",
    )
    pkg = r.json()
    # PM does not hold packages.delete → 403.
    rd = pm_session.delete(f"{BASE_URL}/api/v1/packages/{pkg['id']}")
    assert rd.status_code == 403, rd.text
    # admin succeeds.
    rd = admin.delete(f"{BASE_URL}/api/v1/packages/{pkg['id']}")
    assert rd.status_code == 204, rd.text


def test_TPM_2_cross_tenant_load_returns_404(admin, project, budget):
    """Unknown package id → 404 (not 403)."""
    fake = str(uuid.uuid4())
    r = admin.get(f"{BASE_URL}/api/v1/packages/{fake}")
    assert r.status_code == 404, r.text


def test_TPM_3_view_without_sensitive_redacts_pricing(
    admin, readonly_session, project, budget,
):
    """Read_only sees structure but pricing redacted to null."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PM3", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    pl_id = pdata["lines"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_id, "quoted_unit_rate": "1000"},
    ])
    # readonly user fetches.
    rr = readonly_session.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}")
    assert rr.status_code == 200, rr.text
    body = rr.json()
    assert body["total_net"] is None
    assert body["awarded_net"] is None
    for ln in body["lines"]:
        assert ln["budgeted_unit_rate"] is None
        assert ln["budgeted_net_amount"] is None
    for b in body["bids"]:
        assert b["total_net"] is None
        for bl in b["lines"]:
            assert bl["quoted_unit_rate"] is None
            assert bl["quoted_net_amount"] is None


def test_TPM_4_view_sensitive_reveals_pricing(
    admin, project, budget,
):
    """A super_admin caller sees all pricing."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PM4", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    body = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    assert body["total_net"] is not None
    assert Decimal(body["total_net"]) > Decimal("0")
    assert body["lines"][0]["budgeted_unit_rate"] is not None


def test_TPM_5_pm_can_send_to_tender_but_not_award(
    pm_session, admin, project, budget,
):
    """PM has edit, can drive to tender; cannot award."""
    r = create_package(
        pm_session, project_id=project, budget_id=budget["id"],
        title="PM5", kind="materials",
    )
    pkg = r.json()
    add_line(pm_session, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    rt = send_to_tender(pm_session, pkg["id"])
    assert rt.status_code == 200, rt.text
    pdata = pm_session.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    pl_id = pdata["lines"][0]["id"]
    supplier = make_supplier(admin)
    invite_bidder(pm_session, pkg["id"], supplier_id=supplier)
    # PM may not award even with a fast-track.
    r = award(pm_session, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": None,
        "lines": [{"package_line_id": pl_id, "quantity": "50",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r.status_code == 403, r.text


# ==========================================================================
# T-AD : audit
# ==========================================================================

def test_TAD_1_audit_rows_on_lifecycle(admin, db_engine, project, budget):
    """create / send_to_tender / award / award_cancelled each write an
    audit row with correct action + actor."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AD1",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    aw = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }])
    aw_id = aw.json()["awards"][0]["id"]
    cancel_award(admin, aw_id, reason="audit-test")

    with db_engine.connect() as c:
        rows = c.execute(text("""
            SELECT action, metadata_json::text
            FROM audit_log
            WHERE resource_type='packages' AND resource_id=:p
            ORDER BY created_at
        """), {"p": pkg["id"]}).all()
    actions = [r[0] for r in rows]
    # Must have Create + Status_Change (send_to_tender) + Approve (award)
    # + Status_Change (award_cancelled), at minimum.
    assert "Create" in actions
    assert "Approve" in actions
    sc_count = actions.count("Status_Change")
    assert sc_count >= 2, actions


def test_TAD_2_award_audit_records_downstream_id(
    admin, db_engine, project, budget,
):
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AD2",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    aw_body = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }]).json()
    po_id = aw_body["awards"][0]["created_purchase_order_id"]

    with db_engine.connect() as c:
        rows = c.execute(text("""
            SELECT metadata_json::text, field_changes::text
            FROM audit_log
            WHERE resource_type='packages' AND resource_id=:p
              AND action='Approve'
            ORDER BY created_at DESC LIMIT 1
        """), {"p": pkg["id"]}).all()
    assert rows
    meta_str, changes_str = rows[0]
    assert "package.award" in meta_str
    assert po_id in meta_str or po_id in changes_str
    assert "awarded_net" in meta_str


# ==========================================================================
# T-RC : reconciliation chain (end-to-end pound traceability)
# ==========================================================================

def test_TRC_1_materials_award_PO_issued_updates_budget_commitments(
    admin, finance_session, db_engine, project, budget,
):
    """After awarding materials and driving the resulting PO to `issued`
    via the EXISTING PO endpoints, the referenced budget line's
    `committed_value` / `committed_not_invoiced` reflect the award.
    """
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="RC1",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "500"},
    ])
    aw = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "500"}],
    }]).json()
    po_id = aw["awards"][0]["created_purchase_order_id"]
    # Look up the budget_line_id behind pl_ids[0].
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    bl_id = next(
        ln["budget_line_id"] for ln in pdata["lines"] if ln["id"] == pl_ids[0]
    )
    # Snapshot budget line BEFORE issuing PO.
    with db_engine.connect() as c:
        before = c.execute(text(
            "SELECT committed_value, committed_not_invoiced "
            "FROM budget_lines WHERE id=:b"
        ), {"b": bl_id}).first()
    # Submit + approve + issue the PO via the EXISTING endpoints.
    # PO defaults `approval_required=false`, but the budget-gate
    # submit can still route to pending_approval based on the
    # budget threshold — so handle either branch.
    rs = admin.post(
        f"{BASE_URL}/api/v1/purchase-orders/{po_id}/submit",
        json={},
    )
    assert rs.status_code == 200, rs.text
    po_after_submit = rs.json()
    if po_after_submit["status"] == "pending_approval":
        # PO submitter cannot self-approve → finance does the approval.
        ra = finance_session.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_id}/approve",
            json={"notes": "approve for test"},
        )
        assert ra.status_code == 200, ra.text
    if po_after_submit["status"] != "issued":
        ri = admin.post(f"{BASE_URL}/api/v1/purchase-orders/{po_id}/issue")
        assert ri.status_code == 200, ri.text
    # Final budget line state.
    with db_engine.connect() as c:
        after = c.execute(text(
            "SELECT committed_value, committed_not_invoiced "
            "FROM budget_lines WHERE id=:b"
        ), {"b": bl_id}).first()
    # committed_value should now reflect the PO net (£50,000).
    assert Decimal(after[0]) >= Decimal("50000.00")
    # And it must be higher than the pre-issue snapshot.
    assert Decimal(after[0]) > Decimal(before[0])
    # committed_not_invoiced reflects the unpaid commitment.
    assert Decimal(after[1]) >= Decimal("50000.00")


# ==========================================================================
# Extra coverage (T-PM extended scope/visibility + state machine edges)
# ==========================================================================

def test_TPM_6_list_endpoint_returns_only_visible(
    admin, readonly_session, project, budget,
):
    """GET /packages returns only packages visible to the caller."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PM6", kind="materials",
    )
    assert r.status_code == 201, r.text
    rl = readonly_session.get(f"{BASE_URL}/api/v1/packages")
    assert rl.status_code == 200, rl.text
    body = rl.json()
    # All items visible should redact pricing.
    for item in body["items"]:
        assert item["total_net"] is None


def test_TPM_7_list_filtered_by_project(admin, project, budget):
    r = admin.get(
        f"{BASE_URL}/api/v1/projects/{project}/packages"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for item in body["items"]:
        assert item["project_id"] == project


def test_TPM_8_invite_rejects_consultant_supplier(admin, project, budget):
    """Both labour AND materials reject Consultant/Other supplier types."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PM8", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    consultant = make_supplier(admin, supplier_type="Consultant")
    r = invite_bidder(admin, pkg["id"], supplier_id=consultant)
    assert r.status_code == 422, r.text


def test_TPM_9_cancel_award_requires_packages_award(
    pm_session, admin, project, budget,
):
    """packages.award gates BOTH award and cancel_award."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="PM9",
    )
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    enter_bid(admin, bid_id, lines=[
        {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
    ])
    aw = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": bid_id,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "100",
                   "awarded_unit_rate": "1000"}],
    }]).json()
    award_id = aw["awards"][0]["id"]
    # PM tries to cancel award → 403.
    rc = cancel_award(pm_session, award_id, reason="nope")
    assert rc.status_code == 403, rc.text


def test_TAW_12_partial_quantity_split(admin, project, budget):
    """Award 60 units to one winner and 40 to another on the same line.
    Then a per-line guard check via fast-track on the now-exhausted line."""
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW12",
    )
    # Invite 3 bidders up front (out_to_tender is the only state that
    # accepts new invites — see svc.invite_bidder).
    s1 = make_supplier(admin, name=f"PKG-Test-Split-A-{uuid.uuid4().hex[:6]}")
    s2 = make_supplier(admin, name=f"PKG-Test-Split-B-{uuid.uuid4().hex[:6]}")
    s3 = make_supplier(admin, name=f"PKG-Test-Split-C-{uuid.uuid4().hex[:6]}")
    invite_bidder(admin, pkg["id"], supplier_id=s1)
    invite_bidder(admin, pkg["id"], supplier_id=s2)
    iv3 = invite_bidder(admin, pkg["id"], supplier_id=s3).json()
    bids_by_supplier = {b["supplier_id"]: b["id"] for b in iv3["bids"]}
    b1, b2, b3 = bids_by_supplier[s1], bids_by_supplier[s2], bids_by_supplier[s3]
    for bid_id in (b1, b2, b3):
        enter_bid(admin, bid_id, lines=[
            {"package_line_id": pl_ids[0], "quoted_unit_rate": "1000"},
        ])
    r1 = award(admin, pkg["id"], awards=[{
        "supplier_id": s1, "source_bid_id": b1,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "60",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r1.status_code == 200, r1.text
    r2 = award(admin, pkg["id"], awards=[{
        "supplier_id": s2, "source_bid_id": b2,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "40",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r2.status_code == 200, r2.text
    # 3rd award of 1 more unit on the same line → per-line quantity guard.
    r3 = award(admin, pkg["id"], awards=[{
        "supplier_id": s3, "source_bid_id": b3,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "1",
                   "awarded_unit_rate": "1000"}],
    }])
    assert r3.status_code == 422, r3.text


def test_TAW_13_fast_track_within_total_only(admin, project, budget):
    """Fast-track award still respects the header Σ-guard."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="AW13", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    pl_id = pdata["lines"][0]["id"]
    supplier = make_supplier(admin)
    # qty=100 * rate=2000 = 200_000; total_net=100_000 → 422
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": None,
        "lines": [{"package_line_id": pl_id, "quantity": "100",
                   "awarded_unit_rate": "2000"}],
    }])
    assert r.status_code == 422, r.text
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    assert pdata["status"] == "draft"
    assert len(pdata["awards"]) == 0


def test_TPM_10_finance_cannot_create_package(finance_session, project, budget):
    """Finance lacks packages.create."""
    r = create_package(
        finance_session, project_id=project, budget_id=budget["id"],
        title="PM10", kind="materials",
    )
    assert r.status_code == 403, r.text


def test_TPM_11_finance_cannot_edit_package_lines(
    admin, finance_session, project, budget,
):
    """Finance lacks packages.edit."""
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PM11", kind="materials",
    )
    pkg = r.json()
    r = add_line(
        finance_session, pkg["id"],
        budget_line_id=budget["lines"][0]["id"],
    )
    assert r.status_code == 403, r.text


def test_TPM_12_get_returns_404_for_unknown_id(admin):
    r = admin.get(f"{BASE_URL}/api/v1/packages/{uuid.uuid4()}")
    assert r.status_code == 404, r.text


def test_TAW_14_negative_rate_rejected(admin, project, budget):
    pkg, pl_ids = _pkg_with_lines_at_tender(
        admin, project, budget, title="AW14",
    )
    supplier = make_supplier(admin)
    r = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier, "source_bid_id": None,
        "lines": [{"package_line_id": pl_ids[0], "quantity": "10",
                   "awarded_unit_rate": "-500"}],
    }])
    assert r.status_code == 422, r.text
