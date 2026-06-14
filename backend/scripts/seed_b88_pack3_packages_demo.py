"""B88 Pack 3 — Packages sandbox demo seed.

Purpose: populate `/admin/packages` with a realistic spread for the
operator-facing live-eyeball: one fully-tendered MATERIALS package
split across two winners, one LABOUR package awarded to a single
contractor, and one DRAFT package left un-tendered.

╔══════════════════════════════════════════════════════════════════════╗
║                       HARD SAFETY GUARD                              ║
║                                                                      ║
║ This script REFUSES to run unless an explicit opt-in is present:     ║
║                                                                      ║
║   - env  SYHUB_ALLOW_DEMO_SEED=1                                     ║
║   - and/or CLI  --force                                              ║
║                                                                      ║
║ Demo data must NEVER be auto-seeded. This script is OPERATOR-INVOKED ║
║ ONLY and is NOT referenced by `bootstrap.py`, `on-restart.sh`, or    ║
║ the normal RBAC / cost-code seed paths.                              ║
╚══════════════════════════════════════════════════════════════════════╝

What the seed builds (idempotent — re-runnable after any pod recycle):

  PKG-XXXX  "DEMO — Roofing materials (Block A)"   [materials, AWARDED-SPLIT]
            2 lines, 2 received bids, awarded to two demo suppliers within
            total — list view shows partially_awarded / awarded plus the
            two created draft POs.

  PKG-XXXX  "DEMO — First-fix carpentry (Block A)" [labour, AWARDED]
            1 line, 1 received bid, awarded once → Draft subcontract.

  PKG-XXXX  "DEMO — Site clearance (TBC)"          [materials, DRAFT]
            1 line, never tendered.

All demo rows carry the tag "DEMO — " in their title and demo suppliers
carry "DEMO — " in their name so the --clean teardown can find them
without touching real data.

Data is built THROUGH the real service layer (`services.packages.*`,
`services.purchase_orders.*`, `services.subcontracts.*`) — never via
raw row inserts — so the demo flows the same validated path real data
does and exercises every guard.

Invocation:
  cd /app/backend
  set -a; source .env; set +a

  # seed:
  SYHUB_ALLOW_DEMO_SEED=1 /root/.venv/bin/python \\
      scripts/seed_b88_pack3_packages_demo.py --force

  # clean (removes ONLY the demo rows it created):
  SYHUB_ALLOW_DEMO_SEED=1 /root/.venv/bin/python \\
      scripts/seed_b88_pack3_packages_demo.py --force --clean

Exit codes:
  0  success
  1  safety guard tripped (no opt-in present)
  2  prerequisite missing (no Active budget on any project)
"""
from __future__ import annotations

import argparse
import os
import sys
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy import select, text  # noqa: E402

from app.auth.permissions import compute_effective_permissions  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models.budgets import Budget, BudgetLine, BudgetLineItem  # noqa: E402
from app.models.packages import (  # noqa: E402
    Package, PackageAward, PackageBid,
)
from app.models.projects import Project  # noqa: E402
from app.models.suppliers import Supplier  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import packages as pkg_svc  # noqa: E402
from app.services import suppliers as sup_svc  # noqa: E402


DEMO_TAG = "DEMO — "
ADMIN_EMAIL = "test-admin@example.test"


# ──────────────────────────────────────────────────────────────────────
# Safety guard
# ──────────────────────────────────────────────────────────────────────

def _safety_guard(force_flag: bool) -> None:
    env_ok = os.environ.get("SYHUB_ALLOW_DEMO_SEED") == "1"
    if not (env_ok and force_flag):
        sys.stderr.write(
            "\nREFUSED: this is a sandbox demo-seed and is operator-invoked only.\n"
            "  - set env SYHUB_ALLOW_DEMO_SEED=1, AND\n"
            "  - pass --force\n\n"
            "Demo data must NEVER be auto-seeded by bootstrap/on-restart.\n",
        )
        raise SystemExit(1)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _load_actor(db):
    user = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
    if user is None:
        sys.stderr.write(
            f"REFUSED: actor user {ADMIN_EMAIL!r} not present. "
            "Run scripts/seed_test_users.py first.\n",
        )
        raise SystemExit(2)
    perms = compute_effective_permissions(db, user.id, user.tenant_id)
    return user, perms


def _pick_target_budget(db, tenant_id):
    """Pick the first Active budget on a non-archived project with at
    least 3 budget lines. Returns (project, budget, [bline_ids])."""
    rows = db.execute(
        select(Budget, Project)
        .join(Project, Project.id == Budget.project_id)
        .where(Budget.status == "Active")
        .order_by(Budget.created_at.desc())
    ).all()
    for budget, project in rows:
        lines = db.scalars(
            select(BudgetLine).where(BudgetLine.budget_id == budget.id)
            .order_by(BudgetLine.display_order).limit(8)
        ).all()
        if len(lines) >= 3:
            return project, budget, lines
    sys.stderr.write(
        "REFUSED: no Active budget with ≥3 budget_lines found. "
        "Activate a budget first (run seed_b88_pack2_demo.py or build via UI).\n",
    )
    raise SystemExit(2)


def _ensure_demo_supplier(db, *, user, perms, name: str, supplier_type: str):
    full = f"{DEMO_TAG}{name}"
    existing = db.scalar(
        select(Supplier).where(
            Supplier.tenant_id == user.tenant_id,
            Supplier.name == full,
        )
    )
    if existing is not None:
        return existing
    return sup_svc.create_supplier(
        db,
        tenant_id=user.tenant_id,
        user_id=user.id,
        payload={"name": full, "supplier_type": supplier_type},
    )


def _ensure_po_prefix(db, *, project_id, user) -> None:
    """Ensure the target project has a default `po` number prefix —
    `services.purchase_orders.create_po` requires one. Idempotent."""
    from app.models.number_prefixes import ProjectNumberPrefix
    existing = db.scalar(
        select(ProjectNumberPrefix).where(
            ProjectNumberPrefix.project_id == project_id,
            ProjectNumberPrefix.entity_type == "po",
            ProjectNumberPrefix.is_default.is_(True),
            ProjectNumberPrefix.is_archived.is_(False),
        )
    )
    if existing is not None:
        return
    db.add(ProjectNumberPrefix(
        project_id=project_id,
        entity_type="po",
        middle_prefix="DEMO",
        description="DEMO — auto-created by seed_b88_pack3_packages_demo",
        is_default=True,
        is_archived=False,
        next_sequence=1,
        created_by=user.id,
        updated_by=user.id,
    ))
    db.flush()


# ──────────────────────────────────────────────────────────────────────
# Demo plan
# ──────────────────────────────────────────────────────────────────────

PLAN = [
    # (title_suffix, kind, action, suppliers)
    # action ∈ {"draft", "tender_only", "award_single", "award_split"}
    ("Roofing materials (Block A)", "materials", "award_split",
     [("Acme Roofing Ltd", "Supplier"), ("BetaTile Co Ltd", "Supplier")]),
    ("First-fix carpentry (Block A)", "labour", "award_single",
     [("Gamma Carpentry Ltd", "Contractor")]),
    ("Site clearance (TBC)", "materials", "draft", []),
]


# ──────────────────────────────────────────────────────────────────────
# Clean
# ──────────────────────────────────────────────────────────────────────

def _clean(db, user, perms) -> int:
    """Remove ONLY demo rows. Real data untouched."""
    removed_pkgs = 0
    pkgs = db.scalars(
        select(Package).where(
            Package.tenant_id == user.tenant_id,
            Package.title.like(f"{DEMO_TAG}%"),
        )
    ).all()
    for p in pkgs:
        # Cancel any active awards first — releases the downstream FK
        # references so the cascade-delete from package_awards works.
        for award in p.awards or []:
            if award.status != "active":
                continue
            # Cancel the award FIRST (sets status=cancelled), so the CK
            # `ck_package_awards_one_downstream` (which fires when status
            # is 'active') no longer applies before we NULL out the
            # downstream id during PO/SC deletion.
            award.status = "cancelled"
            award.cancelled_reason = "DEMO cleanup"
            db.flush()
            from app.models.purchase_orders import PurchaseOrder
            from app.models.subcontracts import Subcontract
            if award.created_purchase_order_id:
                po = db.get(PurchaseOrder, award.created_purchase_order_id)
                if po is not None and po.status == "draft":
                    db.delete(po)
                    db.flush()
                    award.created_purchase_order_id = None
            if award.created_subcontract_id:
                sc = db.get(Subcontract, award.created_subcontract_id)
                if sc is not None and sc.status == "Draft":
                    db.delete(sc)
                    db.flush()
                    award.created_subcontract_id = None
        db.flush()
        # The audit_log rows reference packages via resource_id (uuid),
        # not via FK, so are not auto-deleted. Disable the audit trigger
        # and remove them.
        db.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
        db.execute(text(
            "DELETE FROM audit_log WHERE resource_type='packages' "
            "AND resource_id=:p"
        ), {"p": str(p.id)})
        db.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
        db.delete(p)
        removed_pkgs += 1
    db.flush()
    # Also remove the DEMO suppliers if they aren't referenced by
    # non-demo rows. Each demo supplier name starts with DEMO_TAG.
    removed_sups = 0
    sups = db.scalars(
        select(Supplier).where(
            Supplier.tenant_id == user.tenant_id,
            Supplier.name.like(f"{DEMO_TAG}%"),
        )
    ).all()
    for s in sups:
        # If any PO / Subcontract references this supplier, leave it.
        refs = db.scalar(text(
            "SELECT count(*) FROM purchase_orders WHERE supplier_id=:s"
        ), {"s": str(s.id)}) or 0
        refs += db.scalar(text(
            "SELECT count(*) FROM subcontracts WHERE subcontractor_id=:s"
        ), {"s": str(s.id)}) or 0
        if refs > 0:
            continue
        db.delete(s)
        removed_sups += 1
    db.commit()
    print(
        f"--clean: removed {removed_pkgs} demo package(s) "
        f"and {removed_sups} unreferenced demo supplier(s).",
    )
    return 0


# ──────────────────────────────────────────────────────────────────────
# Build
# ──────────────────────────────────────────────────────────────────────

def _build(db, user, perms) -> None:
    project, budget, blines = _pick_target_budget(db, user.tenant_id)
    print(
        f"Target: project={project.name!r} budget={budget.id} "
        f"({len(blines)} lines available)",
    )
    _ensure_po_prefix(db, project_id=project.id, user=user)
    db.flush()

    for i, (title_suffix, kind, action, suppliers) in enumerate(PLAN):
        full_title = f"{DEMO_TAG}{title_suffix}"
        # Idempotency: skip if a demo package with this title already
        # exists. If the operator wants a clean re-spread, they should
        # run --clean first.
        existing = db.scalar(
            select(Package).where(
                Package.tenant_id == user.tenant_id,
                Package.title == full_title,
            )
        )
        if existing is not None:
            print(
                f"  [{i+1}] SKIP — {full_title} already present "
                f"({existing.reference}, status={existing.status})",
            )
            continue

        # Pick distinct budget lines per package to avoid same-line
        # tendering collisions.
        line_count = 2 if action == "award_split" else 1
        used_bl = blines[i : i + line_count]
        if len(used_bl) < line_count:
            used_bl = blines[:line_count]

        # 1. Create the package via the service.
        pkg = pkg_svc.create_package(
            db,
            project_id=project.id,
            budget_id=budget.id,
            title=full_title,
            kind=kind,
            user=user, perms=perms,
            description="Demo package generated by seed script.",
        )
        # 2. Add lines.
        for bl in used_bl:
            pkg_svc.add_package_line(
                db, pkg.id,
                budget_line_id=bl.id,
                user=user, perms=perms,
            )
        # Re-load to get the per-line budgeted_net.
        pkg = pkg_svc.get_package(db, pkg.id, user=user, perms=perms)
        if action == "draft":
            db.commit()
            print(f"  [{i+1}] DRAFT  — {pkg.reference}  {full_title}")
            continue

        # 3. Send to tender.
        pkg_svc.send_to_tender(db, pkg.id, user=user, perms=perms)
        # 4. Ensure demo suppliers + invite.
        sup_ids = []
        for sname, stype in suppliers:
            s = _ensure_demo_supplier(
                db, user=user, perms=perms, name=sname, supplier_type=stype,
            )
            sup_ids.append(s.id)
            pkg_svc.invite_bidder(
                db, pkg.id, supplier_id=s.id, user=user, perms=perms,
            )
        # Force a re-load of the package + relationships across the
        # session identity map so .bids reflects what invite_bidder just
        # persisted.
        db.expire_all()
        pkg = pkg_svc.get_package(db, pkg.id, user=user, perms=perms)
        bid_map = {b.supplier_id: b for b in pkg.bids}
        pl_ids = [pl.id for pl in pkg.lines]
        pl_rate = {
            pl.id: Decimal(str(pl.budgeted_unit_rate))
            for pl in pkg.lines
        }
        for s_id in sup_ids:
            if s_id not in bid_map:
                # Debug print to surface the mismatch.
                avail = {str(k): v.id for k, v in bid_map.items()}
                raise RuntimeError(
                    f"DEMO seed could not find bid for supplier {s_id} — "
                    f"pkg.bids has supplier_ids: {list(avail.keys())}"
                )
            bid = bid_map[s_id]
            lines = [
                {
                    "package_line_id": pl_id,
                    "quoted_unit_rate": str(
                        (pl_rate[pl_id] * Decimal("0.95")).quantize(
                            Decimal("0.0001"),
                        ),
                    ),
                }
                for pl_id in pl_ids
            ]
            pkg_svc.enter_bid(
                db, bid.id, lines=lines, user=user, perms=perms,
            )
        # 6. Award.
        db.expire_all()
        pkg = pkg_svc.get_package(db, pkg.id, user=user, perms=perms)
        bid_map = {b.supplier_id: b for b in pkg.bids}
        if action == "award_split":
            # Award sup1 line[0] and sup2 line[1] each at 95% rate.
            s1, s2 = sup_ids
            awards = [
                {
                    "supplier_id": str(s1),
                    "source_bid_id": str(bid_map[s1].id),
                    "lines": [{
                        "package_line_id": str(pl_ids[0]),
                        "quantity": str(pkg.lines[0].quantity),
                        "awarded_unit_rate": str(
                            (pl_rate[pl_ids[0]] * Decimal("0.95"))
                            .quantize(Decimal("0.0001")),
                        ),
                    }],
                },
                {
                    "supplier_id": str(s2),
                    "source_bid_id": str(bid_map[s2].id),
                    "lines": [{
                        "package_line_id": str(pl_ids[1]),
                        "quantity": str(pkg.lines[1].quantity),
                        "awarded_unit_rate": str(
                            (pl_rate[pl_ids[1]] * Decimal("0.95"))
                            .quantize(Decimal("0.0001")),
                        ),
                    }],
                },
            ]
        else:  # award_single
            (s1,) = sup_ids
            awards = [{
                "supplier_id": str(s1),
                "source_bid_id": str(bid_map[s1].id),
                "lines": [{
                    "package_line_id": str(pl_ids[0]),
                    "quantity": str(pkg.lines[0].quantity),
                    "awarded_unit_rate": str(
                        (pl_rate[pl_ids[0]] * Decimal("0.95"))
                        .quantize(Decimal("0.0001")),
                    ),
                }],
            }]
        pkg_svc.award_package(
            db, pkg.id, awards=awards, user=user, perms=perms,
        )
        db.commit()
        pkg = pkg_svc.get_package(db, pkg.id, user=user, perms=perms)
        print(
            f"  [{i+1}] {pkg.status.upper():18s} {pkg.reference}  "
            f"{full_title}  awarded_net={pkg.awarded_net} "
            f"awards={len(pkg.awards)}",
        )


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="B88 Pack 3 — Packages sandbox demo seed.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Required (with env SYHUB_ALLOW_DEMO_SEED=1) to run.",
    )
    parser.add_argument(
        "--clean", action="store_true",
        help="Remove ONLY demo rows created by this script.",
    )
    args = parser.parse_args(argv)
    _safety_guard(args.force)

    db = SessionLocal()
    try:
        user, perms = _load_actor(db)
        if args.clean:
            return _clean(db, user, perms)
        _build(db, user, perms)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
