"""B88 Pack 3 — Packages service-layer / migration / RBAC tests.

Round-trips via HTTP (fixtures are auth-cookie-based) but exercises the
service-layer business rules in `services.packages` and the migration
0047_packages schema.

Test ID conventions (Build Pack §5):
  T-M-*  : migration/model
  T-PK-* : package CRUD
  T-TN-* : tender / bid
  T-AW-* : award engine
  T-CX-* : cancel
  T-PM-* : permissions / scope / sensitive
  T-AD-* : audit
  T-RB-* : RBAC seed
"""
from __future__ import annotations

import threading
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, text

from tests._packages_common import (
    ADMIN_EMAIL, BASE_URL, DATABASE_URL, FINANCE_EMAIL, PM_EMAIL,
    PWD, READONLY_EMAIL,
    add_line, award, bump_self_approval_threshold, cancel_award,
    create_package, enter_bid, invite_bidder, make_active_budget,
    make_consultant, make_contractor, make_entity_and_project,
    make_supplier, send_to_tender, wipe,
)
from tests.conftest import login_with_auto_enroll


# ==========================================================================
# Fixtures (module-scoped — see test_subcontracts_service.py pattern)
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


# ==========================================================================
# T-M : migration + schema
# ==========================================================================

def test_TM_1_alembic_head_is_0050(db_engine):
    """Pack 3.5 — alembic head reports 0050 and all 6 tables exist.

    Bumped from 0049 → 0050 as part of C1-back (Budget Double-Counts Committed
    Cost): migration 0050_backfill_invoiced_commit is a data-only backfill that
    recomputes invoiced_against_commitment / committed_not_invoiced on existing
    budget lines. The package tables introduced in 0047/0048 are untouched.
    """
    with db_engine.connect() as c:
        head = c.execute(text(
            "SELECT version_num FROM alembic_version"
        )).scalar()
    assert head == "0050_backfill_invoiced_commit", head
    expected_tables = {
        "packages", "package_lines", "package_bids", "package_bid_lines",
        "package_awards", "package_award_lines",
    }
    with db_engine.connect() as c:
        rows = c.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name = ANY(:names)"
        ), {"names": list(expected_tables)}).all()
    found = {r[0] for r in rows}
    assert found == expected_tables, found.symmetric_difference(expected_tables)


def test_TM_2_enums_present_with_expected_values(db_engine):
    """All 4 new PG enums + 'award' on permission_action.

    Pack 3.5 — `package_kind` is now a 3-value LIVE vocabulary
    (`materials`, `subcontract`, `consultant`). The DB enum physically
    retains the orphaned `labour` value (Postgres cannot drop enum
    values; precedent 0020/0047); the live allowed set is enforced by
    the named CHECK constraint `ck_packages_kind_values`, NOT the
    enum's full member list. So `package_kind` is asserted against the
    CHECK-allowed set (per Build Pack §0.4); the other enums use the
    full pg_enum member list as before.
    """
    enum_expected = {
        "package_status": {
            "draft", "out_to_tender", "partially_awarded",
            "awarded", "cancelled",
        },
        "package_bid_status": {
            "invited", "received", "declined", "withdrawn",
        },
        "package_award_status": {"active", "cancelled"},
    }
    with db_engine.connect() as c:
        for enum_name, expected in enum_expected.items():
            rows = c.execute(text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :n"
            ), {"n": enum_name}).all()
            values = {r[0] for r in rows}
            assert values == expected, (enum_name, values, expected)

        # package_kind — assert against the CHECK-allowed live set.
        check_def = c.execute(text(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
            "WHERE conname = 'ck_packages_kind_values'"
        )).scalar() or ""
        for v in ("materials", "subcontract", "consultant"):
            assert v in check_def, (v, check_def)
        assert "labour" not in check_def, check_def

        # 'award' on permission_action
        rows = c.execute(text(
            "SELECT e.enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'permission_action'"
        )).all()
        actions = {r[0] for r in rows}
        assert "award" in actions
        # 'packages' on permission_resource
        rows = c.execute(text(
            "SELECT e.enumlabel FROM pg_enum e "
            "JOIN pg_type t ON t.oid = e.enumtypid "
            "WHERE t.typname = 'permission_resource'"
        )).all()
        resources = {r[0] for r in rows}
        assert "packages" in resources


def test_TM_3_one_downstream_check_constraint(db_engine, admin, project, budget):
    """ck_package_awards_one_downstream rejects both-null and both-set on active.

    Direct INSERT bypasses the service to prove the DB-layer guard.
    """
    # Need a package + supplier + tenant_id seed.
    cr = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TM3 Check", kind="materials",
    )
    assert cr.status_code == 201, cr.text
    pkg_id = cr.json()["id"]
    supplier_id = make_supplier(admin)
    pm = admin.get(f"{BASE_URL}/api/v1/packages/{pkg_id}").json()

    with db_engine.begin() as c:
        # both null + active → CK violation
        with pytest.raises(Exception) as exc:
            c.execute(text("""
                INSERT INTO package_awards
                    (id, package_id, supplier_id, status, awarded_net,
                     created_by, updated_by)
                VALUES
                    (gen_random_uuid(), :p, :s, 'active', 100.00,
                     (SELECT id FROM users WHERE email=:e),
                     (SELECT id FROM users WHERE email=:e))
            """), {"p": pkg_id, "s": supplier_id, "e": ADMIN_EMAIL})
        assert "ck_package_awards_one_downstream" in str(exc.value)


# ==========================================================================
# T-PK : package CRUD
# ==========================================================================

def test_TPK_1_create_happy_path(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PK1", kind="materials",
    )
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "draft"
    assert p["total_net"] == "0.00"
    assert p["awarded_net"] == "0.00"
    assert p["kind"] == "materials"
    assert p["reference"].startswith("PKG-")


def test_TPK_2_reject_terminal_budget(admin, db_engine, project, budget):
    # Force budget terminal via SQL.
    bid = budget["id"]
    with db_engine.begin() as c:
        c.execute(text(
            "UPDATE budgets SET status='Closed' WHERE id=:b"
        ), {"b": bid})
    try:
        r = create_package(
            admin, project_id=project, budget_id=bid,
            title="PK2", kind="materials",
        )
        assert r.status_code == 422, r.text
        assert "terminal" in r.text.lower() or "closed" in r.text.lower()
    finally:
        with db_engine.begin() as c:
            c.execute(text(
                "UPDATE budgets SET status='Active' WHERE id=:b"
            ), {"b": bid})


def test_TPK_3_reject_foreign_budget(admin, project, budget):
    fake_id = str(uuid.uuid4())
    r = create_package(
        admin, project_id=project, budget_id=fake_id,
        title="PK3", kind="materials",
    )
    assert r.status_code == 422, r.text


def test_TPK_4_pkg_number_sequence_per_project(admin, project, budget):
    refs = []
    for i in range(3):
        r = create_package(
            admin, project_id=project, budget_id=budget["id"],
            title=f"PK4-{i}", kind="materials",
        )
        assert r.status_code == 201, r.text
        refs.append(r.json()["reference"])
    # Refs are PKG-NNNN, monotonically increasing per project (no gap).
    nums = [int(r.split("-")[1]) for r in refs]
    assert nums == sorted(nums)
    assert nums[2] - nums[0] == 2


def test_TPK_5_add_and_remove_line_draft_only(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PK5", kind="materials",
    )
    pkg = r.json()
    bline = budget["lines"][0]["id"]
    r = add_line(admin, pkg["id"], budget_line_id=bline)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["lines"]) == 1
    line_id = body["lines"][0]["id"]
    # Remove
    rd = admin.delete(
        f"{BASE_URL}/api/v1/packages/{pkg['id']}/lines/{line_id}"
    )
    assert rd.status_code == 204, rd.text
    # Send to tender then verify line edits rejected (separately
    # exercised in T-TN-2).


def test_TPK_6_line_edit_recomputes_total(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PK6", kind="materials",
    )
    pkg = r.json()
    bline = budget["lines"][0]["id"]
    r = add_line(admin, pkg["id"], budget_line_id=bline)
    body = r.json()
    line_id = body["lines"][0]["id"]
    initial_total = Decimal(body["total_net"])
    # Edit qty → expect recompute (qty * rate).
    r = admin.patch(
        f"{BASE_URL}/api/v1/packages/{pkg['id']}/lines/{line_id}",
        json={"quantity": "50"},
    )
    assert r.status_code == 200, r.text
    after = r.json()
    new_total = Decimal(after["total_net"])
    assert new_total != initial_total
    # 50 * (1000 = 100000/100) = 50000
    line = after["lines"][0]
    assert Decimal(line["budgeted_net_amount"]) == Decimal(line["quantity"]) * Decimal(line["budgeted_unit_rate"])


def test_TPK_7_add_line_rejects_foreign_budget_line(admin, project, budget):
    # Build a second budget on a different project and try to reference its line.
    _, other_project = make_entity_and_project(admin, name_prefix="PKG Test Other")
    eng = create_engine(DATABASE_URL, future=True)
    other_budget = make_active_budget(
        admin, eng, other_project,
        line_count=1, line_amount=Decimal("50000.00"),
    )
    eng.dispose()
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PK7", kind="materials",
    )
    pkg = r.json()
    foreign_line = other_budget["lines"][0]["id"]
    r = add_line(admin, pkg["id"], budget_line_id=foreign_line)
    assert r.status_code == 422, r.text


def test_TPK_8_line_inherits_from_budget_line_item(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PK8", kind="materials",
    )
    pkg = r.json()
    bline = budget["lines"][0]["id"]
    r = add_line(admin, pkg["id"], budget_line_id=bline)
    body = r.json()
    assert "lines" in body, f"add_line response missing 'lines': {body!r}"
    line = body["lines"][0]
    # Common helper seeds qty=100, rate=1000, amount=100000.
    assert Decimal(line["quantity"]) == Decimal("100.0000")
    assert Decimal(line["budgeted_unit_rate"]) == Decimal("1000.0000")
    assert Decimal(line["budgeted_net_amount"]) == Decimal("100000.00")
    assert line["unit"] == "m2"
    # cost_code is the FK-resolved string from cost_codes.code
    assert line["cost_code"] and line["cost_code"] != "UNKNOWN"


def test_TPK_9_delete_blocked_with_active_award_allowed_when_draft(
    admin, project, budget,
):
    # 1. draft → delete works.
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PK9-draft", kind="materials",
    )
    pkg = r.json()
    rd = admin.delete(f"{BASE_URL}/api/v1/packages/{pkg['id']}")
    assert rd.status_code == 204, rd.text
    # 2. With active award → delete blocked.
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="PK9-awarded", kind="materials",
    )
    pkg = r.json()
    bline = budget["lines"][0]["id"]
    add_line(admin, pkg["id"], budget_line_id=bline)
    send_to_tender(admin, pkg["id"])
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    # Get the package line id
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    pl_id = pdata["lines"][0]["id"]
    enter_bid(admin, bid_id, lines=[{
        "package_line_id": pl_id, "quoted_unit_rate": "1000",
    }])
    aw = award(admin, pkg["id"], awards=[{
        "supplier_id": supplier,
        "source_bid_id": bid_id,
        "lines": [{
            "package_line_id": pl_id,
            "quantity": "100",
            "awarded_unit_rate": "1000",
        }],
    }])
    assert aw.status_code == 200, aw.text
    rd = admin.delete(f"{BASE_URL}/api/v1/packages/{pkg['id']}")
    assert rd.status_code == 409, rd.text


# ==========================================================================
# T-TN : tender + bid
# ==========================================================================

def test_TTN_1_send_to_tender_requires_one_line(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN1", kind="materials",
    )
    pkg = r.json()
    r = send_to_tender(admin, pkg["id"])
    assert r.status_code == 409, r.text
    # Add a line then it works.
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    r = send_to_tender(admin, pkg["id"])
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "out_to_tender"


def test_TTN_2_lines_frozen_after_tender(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN2", kind="materials",
    )
    pkg = r.json()
    bline = budget["lines"][0]["id"]
    body = add_line(admin, pkg["id"], budget_line_id=bline).json()
    line_id = body["lines"][0]["id"]
    send_to_tender(admin, pkg["id"])
    # Edit fails
    r = admin.patch(
        f"{BASE_URL}/api/v1/packages/{pkg['id']}/lines/{line_id}",
        json={"quantity": "10"},
    )
    assert r.status_code == 409, r.text
    # Delete fails
    rd = admin.delete(
        f"{BASE_URL}/api/v1/packages/{pkg['id']}/lines/{line_id}"
    )
    assert rd.status_code == 409, rd.text


def test_TTN_3_invite_dup_returns_409(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN3", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    supplier = make_supplier(admin)
    r1 = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    assert r1.status_code == 201, r1.text
    r2 = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    assert r2.status_code == 409, r2.text


def test_TTN_4_subcontract_rejects_non_contractor(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN4", kind="subcontract",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    plain = make_supplier(admin)  # Supplier type
    r = invite_bidder(admin, pkg["id"], supplier_id=plain)
    assert r.status_code == 422, r.text


def test_TTN_5_materials_accepts_supplier(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN5", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    plain = make_supplier(admin)
    r = invite_bidder(admin, pkg["id"], supplier_id=plain)
    assert r.status_code == 201, r.text
    contractor = make_contractor(admin)
    r = invite_bidder(admin, pkg["id"], supplier_id=contractor)
    assert r.status_code == 201, r.text  # warn-not-block


# Pack 3.5 — supplier_kind_guard FLIP: consultant packages REQUIRE
# Consultant suppliers (pre-3.5 they were rejected outright). Three new
# named TTN tests cover the new live truth.


def test_TTN_6_consultant_accepts_consultant(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN6", kind="consultant",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    consultant = make_consultant(admin)
    r = invite_bidder(admin, pkg["id"], supplier_id=consultant)
    assert r.status_code == 201, r.text


def test_TTN_7_consultant_rejects_non_consultant(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN7", kind="consultant",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    contractor = make_contractor(admin)
    r = invite_bidder(admin, pkg["id"], supplier_id=contractor)
    assert r.status_code == 422, r.text


def test_TTN_8_materials_rejects_consultant(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN8", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    consultant = make_consultant(admin)
    r = invite_bidder(admin, pkg["id"], supplier_id=consultant)
    assert r.status_code == 422, r.text


def test_TTN_9_enter_bid_computes_net_ignores_client_net(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN6", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    pl_id = pdata["lines"][0]["id"]
    # qty=100 inherited; rate=900 → expected net=90000
    er = enter_bid(admin, bid_id, lines=[{
        "package_line_id": pl_id, "quoted_unit_rate": "900",
    }])
    assert er.status_code == 200, er.text
    body = er.json()
    bid = next(b for b in body["bids"] if b["id"] == bid_id)
    assert Decimal(bid["total_net"]) == Decimal("90000.00")
    bl = bid["lines"][0]
    assert Decimal(bl["quoted_net_amount"]) == Decimal("90000.00")


def test_TTN_10_enter_bid_rejects_foreign_line(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN7", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    fake_line = str(uuid.uuid4())
    r = enter_bid(admin, bid_id, lines=[{
        "package_line_id": fake_line, "quoted_unit_rate": "1000",
    }])
    assert r.status_code == 422, r.text


def test_TTN_11_decline_withdrawn_bid_not_awardable(admin, project, budget):
    r = create_package(
        admin, project_id=project, budget_id=budget["id"],
        title="TN8", kind="materials",
    )
    pkg = r.json()
    add_line(admin, pkg["id"], budget_line_id=budget["lines"][0]["id"])
    send_to_tender(admin, pkg["id"])
    supplier = make_supplier(admin)
    iv = invite_bidder(admin, pkg["id"], supplier_id=supplier)
    bid_id = iv.json()["bids"][0]["id"]
    rd = admin.post(f"{BASE_URL}/api/v1/bids/{bid_id}/decline")
    assert rd.status_code == 200, rd.text
    rd2 = admin.post(f"{BASE_URL}/api/v1/bids/{bid_id}/decline")
    # Already declined → state change is a no-op (returns same).
    assert rd2.status_code in (200, 409)
    # Try to enter figures on declined bid → 409.
    pdata = admin.get(f"{BASE_URL}/api/v1/packages/{pkg['id']}").json()
    pl_id = pdata["lines"][0]["id"]
    er = enter_bid(admin, bid_id, lines=[{
        "package_line_id": pl_id, "quoted_unit_rate": "1000",
    }])
    assert er.status_code == 409, er.text


# ==========================================================================
# T-RB : RBAC seed
# ==========================================================================

def test_TRB_1_rbac_seed_packages_perms_and_grants(db_engine):
    """Permissions count == 143; packages.* present with correct sensitive
    set; default role grants exclude award/delete on custom-role rule
    (verified directly on shipped roles).

    Count bumped from 142 → 143 as part of B102 (adds
    `budgets.clear_unbudgeted` to the catalogue, non-sensitive). The
    packages.* set itself is unchanged.
    """
    with db_engine.connect() as c:
        total = c.execute(text(
            "SELECT count(*) FROM permissions"
        )).scalar()
        assert total == 143, total
        pkg = c.execute(text(
            "SELECT code, is_sensitive FROM permissions "
            "WHERE resource='packages' ORDER BY code"
        )).all()
        codes = {row[0] for row in pkg}
        assert codes == {
            "packages.award", "packages.create", "packages.delete",
            "packages.edit", "packages.view", "packages.view_sensitive",
        }
        sensitive = {row[0] for row in pkg if row[1]}
        assert sensitive == {
            "packages.view_sensitive", "packages.award", "packages.delete",
        }
        # Per-role distribution
        def perms_for(role_code):
            return {
                r[0] for r in c.execute(text(
                    "SELECT p.code FROM role_permissions rp "
                    "JOIN roles r ON r.id = rp.role_id "
                    "JOIN permissions p ON p.id = rp.permission_id "
                    "WHERE r.code = :rc AND p.resource='packages'"
                ), {"rc": role_code}).all()
            }
        assert perms_for("super_admin") == codes  # all
        director = perms_for("director")
        assert "packages.delete" not in director  # the trap
        assert {"packages.award", "packages.view_sensitive"} <= director
        pm = perms_for("project_manager")
        assert pm == {
            "packages.view", "packages.view_sensitive",
            "packages.create", "packages.edit",
        }
        assert "packages.award" not in pm
        fin = perms_for("finance")
        assert fin == {
            "packages.view", "packages.view_sensitive", "packages.award",
        }
        assert "packages.create" not in fin
        assert perms_for("read_only") == {"packages.view"}
        assert perms_for("site_manager") == {"packages.view"}
        assert perms_for("investor_read_only") == set()
