"""B88 Pack 3 — Gate 1 live HTTP proofs.

Executes every flow demanded by the BuildPack §8 against the running
backend, asserting status codes/payloads at each step. Prints a labelled
proof transcript suitable for the gate report.
"""
from __future__ import annotations

import json
import sys
import uuid
from decimal import Decimal

sys.path.insert(0, "/app/backend")

from sqlalchemy import create_engine, text

from tests._packages_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, FINANCE_EMAIL, PWD,
    bump_self_approval_threshold,
    make_active_budget, make_entity_and_project, make_supplier,
    wipe,
)
from tests.conftest import login_with_auto_enroll


def banner(title: str) -> None:
    print()
    print("=" * 78)
    print(f"  {title}")
    print("=" * 78)


def dump_resp(label: str, r) -> dict:
    body = r.json() if r.headers.get("content-type", "").startswith(
        "application/json"
    ) else {"_raw": r.text}
    print(f"\n[{r.status_code}] {label}")
    print(json.dumps(body, indent=2, default=str)[:2200])
    return body


def main() -> int:
    engine = create_engine(DATABASE_URL, future=True)
    print(f"BASE_URL = {BASE_URL}")
    wipe(engine)
    with engine.begin() as c:
        c.execute(text(
            "UPDATE users SET mfa_enabled=false, mfa_method=NULL, "
            "mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL, "
            "mfa_enrolled_at=NULL, failed_login_attempts=0, "
            "locked_until=NULL, lockout_level=0 "
            "WHERE email LIKE 'test-%@example.test'"
        ))

    banner("STEP 0 — sign in (admin + finance)")
    admin = login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)
    finance = login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)
    print("Both sessions established.")
    bump_self_approval_threshold(admin)

    _, project_id = make_entity_and_project(admin, name_prefix="PKG Gate1")
    budget = make_active_budget(
        admin, engine, project_id,
        line_count=2, line_amount=Decimal("100000.00"),
    )
    bl0, bl1 = budget["lines"][0]["id"], budget["lines"][1]["id"]
    print(f"project_id     = {project_id}")
    print(f"budget_id      = {budget['id']}")
    print(f"budget_lines   = [{bl0}, {bl1}]")

    banner("PROOF 1 — Create package + add 2 lines (show total_net)")
    r = admin.post(
        f"{BASE_URL}/api/v1/projects/{project_id}/packages",
        json={"budget_id": budget["id"],
              "title": "Roofing Materials — Block A",
              "kind": "materials"},
    )
    pkg = dump_resp("POST /api/v1/projects/{project_id}/packages", r)
    assert r.status_code == 201
    pkg_id = pkg["id"]

    r = admin.post(
        f"{BASE_URL}/api/v1/packages/{pkg_id}/lines",
        json={"budget_line_id": bl0},
    )
    dump_resp("POST /api/v1/packages/{id}/lines (line 1)", r)
    r = admin.post(
        f"{BASE_URL}/api/v1/packages/{pkg_id}/lines",
        json={"budget_line_id": bl1},
    )
    p = dump_resp("POST /api/v1/packages/{id}/lines (line 2)", r)
    print(f"\n  ⇒ total_net = {p['total_net']} "
          f"(expected 200000.00)")
    assert p["total_net"] == "200000.00"
    pl0 = p["lines"][0]["id"]
    pl1 = p["lines"][1]["id"]

    banner("PROOF 2 — send-to-tender + invite 2 bidders + 2 bids")
    r = admin.post(f"{BASE_URL}/api/v1/packages/{pkg_id}/send-to-tender")
    dump_resp("POST /send-to-tender", r)
    assert r.status_code == 200
    assert r.json()["status"] == "out_to_tender"

    s1 = make_supplier(admin, supplier_type="Supplier",
                       name=f"Acme Roofing {uuid.uuid4().hex[:6]}")
    s2 = make_supplier(admin, supplier_type="Supplier",
                       name=f"BetaTile Co {uuid.uuid4().hex[:6]}")

    r = admin.post(
        f"{BASE_URL}/api/v1/packages/{pkg_id}/bids",
        json={"supplier_id": s1},
    )
    iv1 = dump_resp("POST /bids (invite Acme)", r)
    r = admin.post(
        f"{BASE_URL}/api/v1/packages/{pkg_id}/bids",
        json={"supplier_id": s2},
    )
    iv2 = dump_resp("POST /bids (invite BetaTile)", r)
    bid1_id = next(b for b in iv1["bids"] if b["supplier_id"] == s1)["id"]
    bid2_id = next(b for b in iv2["bids"] if b["supplier_id"] == s2)["id"]

    # Acme: aggressive rate on line0 (£950) and line1 (£1100)
    r = admin.post(
        f"{BASE_URL}/api/v1/bids/{bid1_id}/enter",
        json={"lines": [
            {"package_line_id": pl0, "quoted_unit_rate": "950"},
            {"package_line_id": pl1, "quoted_unit_rate": "1100"},
        ]},
    )
    dump_resp("POST /bids/{id}/enter (Acme)", r)
    # BetaTile: line0 (£1050), line1 (£950) — cheaper on line1
    r = admin.post(
        f"{BASE_URL}/api/v1/bids/{bid2_id}/enter",
        json={"lines": [
            {"package_line_id": pl0, "quoted_unit_rate": "1050"},
            {"package_line_id": pl1, "quoted_unit_rate": "950"},
        ]},
    )
    pdata = dump_resp("POST /bids/{id}/enter (BetaTile)", r)

    banner("PROOF 3 — Split award within total (Acme line0, BetaTile line1)")
    award_body = {"awards": [
        {
            "supplier_id": s1, "source_bid_id": bid1_id,
            "lines": [{"package_line_id": pl0, "quantity": "100",
                       "awarded_unit_rate": "950"}],
        },
        {
            "supplier_id": s2, "source_bid_id": bid2_id,
            "lines": [{"package_line_id": pl1, "quantity": "100",
                       "awarded_unit_rate": "950"}],
        },
    ]}
    r = finance.post(
        f"{BASE_URL}/api/v1/packages/{pkg_id}/award",
        json=award_body,
    )
    aw = dump_resp("POST /packages/{id}/award (split)", r)
    assert r.status_code == 200
    print(f"\n  ⇒ package.status   = {aw['status']}")
    print(f"  ⇒ package.awarded_net = {aw['awarded_net']}")
    print(f"  ⇒ awards count = {len(aw['awards'])}")
    for i, a in enumerate(aw["awards"]):
        print(
            f"    award[{i}]: supplier={a['supplier_id']} "
            f"net={a['awarded_net']} "
            f"PO={a['created_purchase_order_id']} "
            f"SC={a['created_subcontract_id']}"
        )
    assert aw["status"] in ("awarded", "partially_awarded")
    assert len(aw["awards"]) == 2
    award_pos = [a["created_purchase_order_id"] for a in aw["awards"]]
    assert all(po is not None for po in award_pos)
    po_to_issue = award_pos[0]

    banner("PROOF 4 — Over-total award attempt rejected (no PO created)")
    # Snapshot PO count.
    with engine.connect() as c:
        po_before = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project_id}).scalar()
        award_before = c.execute(text(
            "SELECT count(*) FROM package_awards WHERE package_id=:p"
        ), {"p": pkg_id}).scalar()
    print(f"\n  Pre-attempt: purchase_orders={po_before} "
          f"package_awards={award_before}")
    # Try to fast-track ANOTHER award on the (now-fully-awarded) lines.
    s3 = make_supplier(admin, supplier_type="Supplier",
                       name=f"GammaPanel {uuid.uuid4().hex[:6]}")
    r = finance.post(
        f"{BASE_URL}/api/v1/packages/{pkg_id}/award",
        json={"awards": [{
            "supplier_id": s3, "source_bid_id": None,
            "lines": [{"package_line_id": pl0, "quantity": "100",
                       "awarded_unit_rate": "100"}],
        }]},
    )
    rejected = dump_resp("POST /award (over-total, expected 422)", r)
    assert r.status_code == 422, r.text
    with engine.connect() as c:
        po_after = c.execute(text(
            "SELECT count(*) FROM purchase_orders WHERE project_id=:p"
        ), {"p": project_id}).scalar()
        award_after = c.execute(text(
            "SELECT count(*) FROM package_awards WHERE package_id=:p"
        ), {"p": pkg_id}).scalar()
    print(f"\n  Post-attempt: purchase_orders={po_after} "
          f"package_awards={award_after}")
    assert po_after == po_before
    assert award_after == award_before

    banner(
        "PROOF 5 — Drive one PO to `issued`, show budget commitments"
    )
    print(f"  PO to issue: {po_to_issue}")
    # Look up the budget_line_id behind pl0.
    with engine.connect() as c:
        bl_for_pl0 = c.execute(text(
            "SELECT budget_line_id FROM package_lines WHERE id=:i"
        ), {"i": pl0}).scalar()
        before = c.execute(text(
            "SELECT committed_value, committed_not_invoiced "
            "FROM budget_lines WHERE id=:b"
        ), {"b": bl_for_pl0}).first()
    print(f"  budget_line_id behind pl0: {bl_for_pl0}")
    print(f"  BEFORE: committed_value={before[0]} "
          f"committed_not_invoiced={before[1]}")

    rs = admin.post(
        f"{BASE_URL}/api/v1/purchase-orders/{po_to_issue}/submit",
        json={},
    )
    dump_resp("POST /purchase-orders/{id}/submit", rs)
    assert rs.status_code == 200
    po_after_submit = rs.json()
    if po_after_submit["status"] == "pending_approval":
        ra = finance.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_to_issue}/approve",
            json={"notes": "Gate 1 live proof"},
        )
        dump_resp("POST /purchase-orders/{id}/approve", ra)
        assert ra.status_code == 200
    if po_after_submit["status"] != "issued":
        ri = admin.post(
            f"{BASE_URL}/api/v1/purchase-orders/{po_to_issue}/issue"
        )
        dump_resp("POST /purchase-orders/{id}/issue", ri)
        assert ri.status_code == 200

    with engine.connect() as c:
        after = c.execute(text(
            "SELECT committed_value, committed_not_invoiced "
            "FROM budget_lines WHERE id=:b"
        ), {"b": bl_for_pl0}).first()
    print(f"\n  AFTER:  committed_value={after[0]} "
          f"committed_not_invoiced={after[1]}")
    assert Decimal(str(after[0])) >= Decimal("95000.00")
    assert Decimal(str(after[1])) >= Decimal("95000.00")

    banner("PROOF 6 — OpenAPI: new /api/v1 package paths")
    r = admin.get(f"{BASE_URL}/openapi.json")
    paths = r.json()["paths"]
    pkg_paths = sorted(
        p for p in paths
        if "/packages" in p or "/awards/" in p or "/bids/" in p
    )
    for p in pkg_paths:
        methods = sorted(
            m.upper() for m in paths[p]
            if m in ("get", "post", "patch", "delete", "put")
        )
        print(f"  {' '.join(methods):20s}  {p}")
    method_combos = sum(
        len([m for m in paths[p] if m in ("get", "post", "patch", "delete", "put")])
        for p in pkg_paths
    )
    print(f"\n  Total package paths exposed: {len(pkg_paths)}")
    print(f"  Total method×path combos:     {method_combos}")
    assert len(pkg_paths) >= 13, f"Expected ≥13 paths, found {len(pkg_paths)}"
    assert method_combos >= 18, f"Expected ≥18 method combos, found {method_combos}"

    banner("ALL PROOFS OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
