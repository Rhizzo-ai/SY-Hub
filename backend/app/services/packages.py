"""Packages service — B88 Pack 3 (Chat 53, the tendering spine).

The award engine in §3.3 is the money-integrity crux: ONE DB transaction,
all-or-nothing, package row LOCKED FOR UPDATE for the whole operation.
Two guards are enforced server-side:

  Header Σ-guard (LD-P3):
      Σ(active awards' awarded_net) ≤ package.total_net + £0.01

  Per-line quantity guard:
      Σ(award_line.quantity) for a package_line, across active awards,
      ≤ package_line.quantity

Server computes every `net = round(qty × rate, 2)`. Client nets are
NEVER trusted (LD-P4 — bidders compete on rate, not measurement).

Downstream creates are delegated to the EXISTING services on the SAME
session/transaction (Pack 3.5 — 3-value vocabulary):
  materials   → services.purchase_orders.create_po
  subcontract → services.subcontracts.create_subcontract
  consultant  → services.purchase_orders.create_po  (CIS-clean PO)

A raise at any step rolls back the whole award call (T-AW-10).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Any, Iterable, Optional

from fastapi import Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.auth.permissions import UserPermissions
from app.models.budgets import (
    Budget, BudgetLine, BudgetLineItem,
    TERMINAL_BUDGET_STATUSES,
)
from app.models.packages import (
    Package, PackageLine, PackageBid, PackageBidLine,
    PackageAward, PackageAwardLine,
    PACKAGE_KINDS,
)
from app.models.projects import Project
from app.models.purchase_orders import PurchaseOrder
from app.models.rbac import UserRole, user_role_projects
from app.models.subcontracts import Subcontract
from app.models.suppliers import Supplier
from app.models.user import User
from app.services import purchase_orders as po_svc
from app.services import subcontracts as sc_svc
from app.services import budget_lines as bl_svc
from app.services.audit import field_diff, record_audit
from app.services.budget_errors import (
    BudgetLineRaceError,
    BudgetNotFoundError,
    BudgetStateError,
    BudgetValidationError,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PackageNotFoundError(Exception):
    """Raised when a package cannot be found OR is out-of-tenant scope."""


class PackageStateError(Exception):
    """Raised on illegal state transition or workflow violation."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_AUDIT_COLS: tuple[str, ...] = (
    "project_id", "budget_id", "reference", "title", "kind",
    "status", "description", "total_net", "awarded_net",
    "out_to_tender_at", "out_to_tender_by",
    "awarded_at", "awarded_by",
    "cancelled_at", "cancelled_by", "cancelled_reason",
)


def _snapshot(p: Package) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for col in _AUDIT_COLS:
        v = getattr(p, col)
        if isinstance(v, Decimal):
            v = str(v)
        out[col] = v
    return out


def _q(v: Any, *, field: str) -> Decimal:
    if v is None:
        raise ValueError(f"{field} is required")
    if isinstance(v, Decimal):
        return v
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError, TypeError) as e:
        raise ValueError(f"{field} not numeric: {v!r}") from e


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _q4(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


# Header money tolerance (LD-P3): Σ(awards) ≤ total_net + £0.01.
_HEADER_TOLERANCE = Decimal("0.01")


# ---------------------------------------------------------------------------
# Tenant / project scoping (Pattern α replica)
# ---------------------------------------------------------------------------

def _visible_project_ids(
    db: Session, user_id: uuid.UUID, tenant_id: uuid.UUID,
) -> Optional[set[uuid.UUID]]:
    now = datetime.now(timezone.utc)
    roles = db.scalars(
        select(UserRole).where(
            UserRole.user_id == user_id,
            UserRole.status == "Active",
            or_(UserRole.expires_at.is_(None), UserRole.expires_at > now),
        )
    ).all()
    ids: set[uuid.UUID] = set()
    has_all = False
    for ur in roles:
        if ur.project_scope == "All":
            has_all = True
        elif ur.project_scope == "Specific":
            rows = db.execute(
                select(user_role_projects.c.project_id).where(
                    user_role_projects.c.user_role_id == ur.id
                )
            ).all()
            ids.update(r[0] for r in rows)
    if has_all:
        return None
    return ids


def _scope_check_project(
    db: Session, project: Project, user: User, perms: UserPermissions,
) -> None:
    """Raise PackageNotFoundError if `project` is not visible."""
    if hasattr(project, "tenant_id") and project.tenant_id != user.tenant_id:
        raise PackageNotFoundError("Package not found")
    if not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None and project.id not in allowed:
            raise PackageNotFoundError("Package not found")


# ---------------------------------------------------------------------------
# Load helpers
# ---------------------------------------------------------------------------

def _load_for_read(
    db: Session, pkg_id: uuid.UUID, user: User, perms: UserPermissions,
) -> Package:
    p = db.scalar(
        select(Package).where(Package.id == pkg_id).options(
            selectinload(Package.lines),
            selectinload(Package.bids).selectinload(PackageBid.bid_lines),
            selectinload(Package.awards).selectinload(
                PackageAward.award_lines
            ),
        )
    )
    if p is None:
        raise PackageNotFoundError("Package not found")
    project = db.get(Project, p.project_id)
    if project is None:
        raise PackageNotFoundError("Package not found")
    _scope_check_project(db, project, user, perms)
    if p.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise PackageNotFoundError("Package not found")
    return p


def _load_for_write(
    db: Session, pkg_id: uuid.UUID, user: User, perms: UserPermissions,
    *, lock_for_update: bool = True,
) -> Package:
    p = db.get(Package, pkg_id)
    if p is None:
        raise PackageNotFoundError("Package not found")
    project = db.get(Project, p.project_id)
    if project is None:
        raise PackageNotFoundError("Package not found")
    _scope_check_project(db, project, user, perms)
    if p.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise PackageNotFoundError("Package not found")
    if lock_for_update:
        p = db.scalar(
            select(Package).where(Package.id == pkg_id).with_for_update()
        )
        if p is None:
            raise PackageNotFoundError("Package not found")
    return p


# ---------------------------------------------------------------------------
# Reference allocator — race-safe under project row lock (subcontracts pattern)
# ---------------------------------------------------------------------------

def _next_reference(db: Session, project_id: uuid.UUID) -> str:
    count = db.scalar(
        select(func.count(Package.id)).where(Package.project_id == project_id)
    ) or 0
    return f"PKG-{count + 1:04d}"


# ---------------------------------------------------------------------------
# Recompute helpers (service is single-writer of cached totals)
# ---------------------------------------------------------------------------

def _recompute_total_net(db: Session, package: Package) -> None:
    """Σ package_lines.budgeted_net_amount."""
    total = db.scalar(
        select(func.coalesce(func.sum(PackageLine.budgeted_net_amount), 0))
        .where(PackageLine.package_id == package.id)
    ) or 0
    package.total_net = _q2(Decimal(total))


def _recompute_bid_total(db: Session, bid: PackageBid) -> None:
    total = db.scalar(
        select(func.coalesce(func.sum(PackageBidLine.quoted_net_amount), 0))
        .where(PackageBidLine.package_bid_id == bid.id)
    ) or 0
    bid.total_net = _q2(Decimal(total))


def _recompute_award_totals(db: Session, package: Package) -> None:
    """Σ awarded_net across ACTIVE awards. Also updates package status."""
    total = db.scalar(
        select(func.coalesce(func.sum(PackageAward.awarded_net), 0))
        .where(
            PackageAward.package_id == package.id,
            PackageAward.status == "active",
        )
    ) or 0
    package.awarded_net = _q2(Decimal(total))

    # Status transition based on awarded_net vs total_net.
    if package.status == "cancelled":
        return
    awarded = package.awarded_net
    total_net = package.total_net
    if awarded == Decimal("0"):
        # No active awards — re-open to out_to_tender (unless still draft).
        if package.status in {"partially_awarded", "awarded"}:
            package.status = "out_to_tender"
    elif awarded + _HEADER_TOLERANCE >= total_net:
        package.status = "awarded"
    else:
        package.status = "partially_awarded"


# ---------------------------------------------------------------------------
# Budget-line inheritance (LD-P4)
# ---------------------------------------------------------------------------

def _cost_code_for_budget_line(db: Session, bline: BudgetLine) -> str:
    """Resolve cost_code string for a BudgetLine via its FK."""
    from app.models.cost_codes import CostCode
    cc = db.get(CostCode, bline.cost_code_id)
    code = (getattr(cc, "code", None) or "")[:20]
    return code or "UNKNOWN"


def _inherit_from_budget_line(
    db: Session, bline: BudgetLine,
) -> tuple[Decimal, Optional[str], Decimal, Decimal, Optional[str]]:
    """Return (quantity, unit, budgeted_unit_rate, budgeted_net_amount, notes).

    Inheritance rule (LD-P4):
      - If the budget line has EXACTLY ONE item with qty + rate: inherit them.
      - Otherwise: default qty=1, rate=current_budget, net=current_budget,
        and flag in notes that detail should be confirmed (NEVER silently
        fabricate quantities).
    """
    items = db.scalars(
        select(BudgetLineItem).where(BudgetLineItem.budget_line_id == bline.id)
    ).all()
    if (
        len(items) == 1
        and items[0].quantity is not None
        and items[0].rate is not None
    ):
        it = items[0]
        qty = _q4(Decimal(str(it.quantity)))
        rate = _q4(Decimal(str(it.rate)))
        net = _q2(qty * rate)
        return qty, it.unit, rate, net, None
    current_budget = _q2(Decimal(str(bline.current_budget or 0)))
    note = (
        "Confirm quantity/unit/rate — inherited budget figure as a "
        "single-quantity lump because the source budget line has "
        f"{len(items)} item(s) with detail."
    )
    return Decimal("1.0000"), None, current_budget, current_budget, note


# ---------------------------------------------------------------------------
# CRUD — Package
# ---------------------------------------------------------------------------

def create_package(
    db: Session, *,
    project_id: uuid.UUID,
    budget_id: uuid.UUID,
    title: str,
    kind: str,
    user: User,
    perms: UserPermissions,
    description: Optional[str] = None,
    request: Optional[Request] = None,
) -> Package:
    if not title or not title.strip():
        raise ValueError("title is required")
    if kind not in PACKAGE_KINDS:
        raise ValueError(f"kind must be one of {PACKAGE_KINDS}; got {kind!r}")

    project = db.get(Project, project_id)
    if project is None:
        raise PackageNotFoundError("Project not found")
    _scope_check_project(db, project, user, perms)

    budget = db.get(Budget, budget_id)
    if budget is None or budget.project_id != project_id:
        raise ValueError(
            f"Budget {budget_id} not found for project {project_id}"
        )
    if budget.status in TERMINAL_BUDGET_STATUSES:
        raise ValueError(
            f"Cannot tender against a {budget.status} budget — "
            f"only non-terminal budgets accept packages"
        )

    # Lock project row to serialise PKG-NNNN allocation.
    db.execute(
        select(Project).where(Project.id == project_id).with_for_update()
    )
    reference = _next_reference(db, project_id)

    p = Package(
        tenant_id=user.tenant_id,
        project_id=project_id,
        budget_id=budget.id,
        reference=reference,
        title=title.strip(),
        kind=kind,
        status="draft",
        description=(description.strip() if description else None),
        total_net=Decimal("0.00"),
        awarded_net=Decimal("0.00"),
        created_by=user.id,
        updated_by=user.id,
    )
    db.add(p)
    db.flush()

    record_audit(
        db, action="Create", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=project_id,
        field_changes=field_diff({}, _snapshot(p)),
        metadata={
            "reference": p.reference,
            "kind": p.kind,
            "budget_id": str(p.budget_id),
        },
        request=request,
    )
    return p


def update_package(
    db: Session, package_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    payload: dict[str, Any], request: Optional[Request] = None,
) -> Package:
    p = _load_for_write(db, package_id, user, perms)
    if p.status == "cancelled":
        raise PackageStateError("Cannot edit a cancelled package")

    allowed = {"title", "description"}
    bad = set(payload.keys()) - allowed
    if bad:
        raise PackageStateError(
            f"Fields not editable via PATCH: {sorted(bad)}"
        )

    before = _snapshot(p)
    if "title" in payload:
        t = payload["title"]
        if not isinstance(t, str) or not t.strip():
            raise ValueError("title is required")
        p.title = t.strip()[:200]
    if "description" in payload:
        v = payload["description"]
        p.description = v.strip() if isinstance(v, str) and v.strip() else None

    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()
    changes = field_diff(before, _snapshot(p))
    if changes:
        record_audit(
            db, action="Update", resource_type="packages",
            resource_id=p.id, actor_user_id=user.id,
            project_id=p.project_id,
            field_changes=changes,
            metadata={"reference": p.reference},
            request=request,
        )
    return p


def delete_package(
    db: Session, package_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> None:
    p = _load_for_write(db, package_id, user, perms)
    if p.status not in {"draft", "cancelled"}:
        raise PackageStateError(
            f"Only draft or cancelled packages may be deleted; "
            f"current={p.status}"
        )
    # No active awards allowed even if status is cancelled (defensive —
    # shouldn't happen since cancel blocks on active awards).
    active = db.scalar(
        select(func.count(PackageAward.id)).where(
            PackageAward.package_id == p.id,
            PackageAward.status == "active",
        )
    ) or 0
    if active > 0:
        raise PackageStateError(
            "Cannot delete a package with active awards"
        )
    before = _snapshot(p)
    record_audit(
        db, action="Delete", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=field_diff(before, {}),
        metadata={"reference": p.reference},
        request=request,
    )
    db.delete(p)
    db.flush()


# ---------------------------------------------------------------------------
# CRUD — PackageLine (draft-only mutations)
# ---------------------------------------------------------------------------

def add_package_line(
    db: Session, package_id: uuid.UUID,
    *, cost_code_id: Optional[uuid.UUID] = None,
    cost_code_subcategory_id: Optional[uuid.UUID] = None,
    budget_line_id: Optional[uuid.UUID] = None,
    user: User, perms: UserPermissions,
    unbudgeted: bool = False,
    unbudgeted_cost_code_id: Optional[uuid.UUID] = None,
    unbudgeted_subcategory_id: Optional[uuid.UUID] = None,
    unbudgeted_reason: Optional[str] = None,
    description: Optional[str] = None,
    quantity: Optional[Any] = None,
    unit: Optional[str] = None,
    budgeted_unit_rate: Optional[Any] = None,
    notes: Optional[str] = None,
    request: Optional[Request] = None,
) -> PackageLine:
    p = _load_for_write(db, package_id, user, perms)
    if p.status != "draft":
        raise PackageStateError(
            f"Lines can be added only in draft status; current={p.status}"
        )

    # ── B105/B106 — RESOLVE-OR-MINT (replaces the B102 unbudgeted branch) ──
    # Determine the cost code (priority: cost_code_id > derived from
    # supplied budget_line_id > deprecated unbudgeted_cost_code_id),
    # resolve via find_line_for_code; mint if absent with neutral
    # markers (force_flag=False, source="package"). Back-compat alias
    # `budget_line_id`, if supplied alongside `cost_code_id`, must
    # agree with the resolved line — mismatch → 422.
    cc_raw = cost_code_id
    sub_raw = cost_code_subcategory_id
    if cc_raw is None and unbudgeted_cost_code_id is not None:
        # Deprecated cluster fallback (B105/B106 §3.10).
        import logging as _logging
        _logging.getLogger("syhomes.deprecation").warning(
            "Package line uses deprecated unbudgeted_* fields "
            "(unbudgeted_cost_code_id / unbudgeted_subcategory_id "
            "/ unbudgeted_reason); switch to cost_code_id + "
            "cost_code_subcategory_id. Cluster will be removed next "
            "release."
        )
        cc_raw = unbudgeted_cost_code_id
        if sub_raw is None:
            sub_raw = unbudgeted_subcategory_id

    if cc_raw is None and budget_line_id is not None:
        # Back-compat alias-only path: derive code from supplied line.
        bl = db.get(BudgetLine, budget_line_id)
        if bl is None or bl.budget_id != p.budget_id:
            raise ValueError(
                f"budget_line_id {budget_line_id} does not belong to "
                f"budget {p.budget_id}"
            )
        cc_raw = bl.cost_code_id
        sub_raw = bl.cost_code_subcategory_id

    if cc_raw is None:
        raise ValueError("cost_code_id is required")

    try:
        cc_id = uuid.UUID(str(cc_raw))
    except (TypeError, ValueError) as e:
        raise ValueError(f"cost_code_id is not a valid UUID: {e}") from e
    sub_id: Optional[uuid.UUID] = None
    if sub_raw is not None:
        try:
            sub_id = uuid.UUID(str(sub_raw))
        except (TypeError, ValueError) as e:
            raise ValueError(
                f"cost_code_subcategory_id is not a valid UUID: {e}"
            ) from e

    existing = bl_svc.find_line_for_code(
        db, budget_id=p.budget_id,
        cost_code_id=cc_id, cost_code_subcategory_id=sub_id,
    )
    if existing is not None:
        bline = existing
    else:
        raw_reason = unbudgeted_reason
        reason = (str(raw_reason).strip() if raw_reason else "") \
            or "Auto-created: order raised against an unbudgeted cost code"
        # B105/B106 §3.9 race handling — wrap in SAVEPOINT so a
        # concurrent mint on the same triple surfaces as 409
        # (`BudgetLineRaceError`) rather than 500. See create_po for
        # the matching pattern; the package transaction stays intact
        # so any earlier lines on this package are not lost.
        try:
            with db.begin_nested():
                bline = bl_svc.create_unbudgeted_line(
                    db, budget_id=p.budget_id, user=user, perms=perms,
                    cost_code_id=cc_id, cost_code_subcategory_id=sub_id,
                    entity_id=None,
                    reason=reason, source="package",
                    force_flag=False,
                )
        except IntegrityError as e:
            _msg = str(e.orig) + str(e)
            if ("uq_budget_lines_budget_cost_subcat" in _msg
                    or "uq_budget_lines_no_subcat_unique" in _msg):
                raise BudgetLineRaceError(
                    cost_code_id=cc_id,
                    cost_code_subcategory_id=sub_id,
                ) from e
            raise
        except (BudgetStateError, BudgetNotFoundError,
                BudgetValidationError) as e:
            raise ValueError(str(e)) from e

    # Alias agreement check (back-compat): mismatch → 422.
    if budget_line_id is not None and budget_line_id != bline.id:
        raise ValueError(
            "budget_line_id does not match the resolved cost-code line"
        )

    # B105/B106 — guard the package_lines unique constraint
    # `uq_package_lines_package_budget_line (package_id, budget_line_id)`.
    # Under resolve-or-mint a caller can resolve to the SAME budget_line
    # twice on the same package (e.g. two PO line payloads naming the
    # same code); for packages the DB constraint legitimately rejects
    # the duplicate. Catch the conflict cleanly and 409 it at the
    # router rather than letting the IntegrityError bubble to 500.
    _existing_pl = db.scalar(
        select(PackageLine).where(
            PackageLine.package_id == p.id,
            PackageLine.budget_line_id == bline.id,
        )
    )
    if _existing_pl is not None:
        raise PackageStateError(
            f"Package {p.reference} already has a line for this "
            f"cost code (package_line_id={_existing_pl.id}); update "
            f"that line via PATCH instead of adding a duplicate."
        )
    # Inherit defaults from budget line + items (LD-P4).
    qty_inh, unit_inh, rate_inh, net_inh, notes_inh = (
        _inherit_from_budget_line(db, bline)
    )
    qty = _q4(_q(quantity, field="quantity")) if quantity is not None else qty_inh
    if qty <= 0:
        raise ValueError("quantity must be > 0")
    rate = (
        _q4(_q(budgeted_unit_rate, field="budgeted_unit_rate"))
        if budgeted_unit_rate is not None else rate_inh
    )
    if rate < 0:
        raise ValueError("budgeted_unit_rate must be >= 0")
    if quantity is not None or budgeted_unit_rate is not None:
        net = _q2(qty * rate)
    else:
        net = net_inh

    # Next line number under package.
    max_n = db.scalar(
        select(func.coalesce(func.max(PackageLine.line_number), 0))
        .where(PackageLine.package_id == p.id)
    ) or 0
    cost_code = _cost_code_for_budget_line(db, bline)

    pl = PackageLine(
        package_id=p.id,
        budget_line_id=bline.id,
        cost_code=cost_code,
        line_number=int(max_n) + 1,
        description=(
            description.strip()
            if isinstance(description, str) and description.strip()
            else bline.line_description
        ),
        quantity=qty,
        unit=unit if unit is not None else unit_inh,
        budgeted_unit_rate=rate,
        budgeted_net_amount=net,
        notes=(
            notes.strip() if isinstance(notes, str) and notes.strip()
            else notes_inh
        ),
    )
    db.add(pl)
    db.flush()

    _recompute_total_net(db, p)
    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()

    record_audit(
        db, action="Update", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=[{
            "field": "lines",
            "old": None,
            "new": {
                "package_line_id": str(pl.id),
                "budget_line_id": str(pl.budget_line_id),
                "line_number": pl.line_number,
                "budgeted_net_amount": str(pl.budgeted_net_amount),
            },
        }],
        metadata={"reference": p.reference, "event": "package.line_added"},
        request=request,
    )
    return pl


def update_package_line(
    db: Session, package_id: uuid.UUID, line_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    payload: dict[str, Any], request: Optional[Request] = None,
) -> PackageLine:
    p = _load_for_write(db, package_id, user, perms)
    if p.status != "draft":
        raise PackageStateError(
            f"Lines can be edited only in draft status; current={p.status}"
        )
    pl = db.get(PackageLine, line_id)
    if pl is None or pl.package_id != p.id:
        raise PackageNotFoundError("Package line not found")

    allowed = {"description", "quantity", "unit", "budgeted_unit_rate", "notes"}
    bad = set(payload.keys()) - allowed
    if bad:
        raise PackageStateError(
            f"Fields not editable on a package line: {sorted(bad)}"
        )
    if "description" in payload:
        v = payload["description"]
        if v is None or (isinstance(v, str) and not v.strip()):
            raise ValueError("description cannot be empty")
        pl.description = v.strip()
    if "unit" in payload:
        v = payload["unit"]
        pl.unit = v if v else None
    if "notes" in payload:
        v = payload["notes"]
        pl.notes = v.strip() if isinstance(v, str) and v.strip() else None

    qty_changed = "quantity" in payload
    rate_changed = "budgeted_unit_rate" in payload
    if qty_changed:
        qty = _q4(_q(payload["quantity"], field="quantity"))
        if qty <= 0:
            raise ValueError("quantity must be > 0")
        pl.quantity = qty
    if rate_changed:
        rate = _q4(_q(payload["budgeted_unit_rate"], field="budgeted_unit_rate"))
        if rate < 0:
            raise ValueError("budgeted_unit_rate must be >= 0")
        pl.budgeted_unit_rate = rate
    if qty_changed or rate_changed:
        pl.budgeted_net_amount = _q2(pl.quantity * pl.budgeted_unit_rate)

    db.flush()
    _recompute_total_net(db, p)
    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()
    return pl


def remove_package_line(
    db: Session, package_id: uuid.UUID, line_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> None:
    p = _load_for_write(db, package_id, user, perms)
    if p.status != "draft":
        raise PackageStateError(
            f"Lines can be removed only in draft status; current={p.status}"
        )
    pl = db.get(PackageLine, line_id)
    if pl is None or pl.package_id != p.id:
        raise PackageNotFoundError("Package line not found")
    db.delete(pl)
    db.flush()
    _recompute_total_net(db, p)
    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()


# ---------------------------------------------------------------------------
# Tender round
# ---------------------------------------------------------------------------

def send_to_tender(
    db: Session, package_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> Package:
    p = _load_for_write(db, package_id, user, perms)
    if p.status != "draft":
        raise PackageStateError(
            f"send_to_tender requires draft; current={p.status}"
        )
    line_count = db.scalar(
        select(func.count(PackageLine.id)).where(
            PackageLine.package_id == p.id
        )
    ) or 0
    if line_count < 1:
        raise PackageStateError(
            "send_to_tender requires at least one package line"
        )
    old_status = p.status
    p.status = "out_to_tender"
    p.out_to_tender_at = datetime.now(timezone.utc)
    p.out_to_tender_by = user.id
    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=[{
            "field": "status", "old": old_status, "new": p.status,
        }],
        metadata={
            "reference": p.reference,
            "event": "package.send_to_tender",
        },
        request=request,
    )
    return p


def cancel_package(
    db: Session, package_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    reason: Optional[str] = None,
    request: Optional[Request] = None,
) -> Package:
    p = _load_for_write(db, package_id, user, perms)
    if p.status == "cancelled":
        raise PackageStateError("Package already cancelled")
    if p.status == "awarded":
        raise PackageStateError(
            "Cannot cancel a fully awarded package; cancel awards first"
        )
    active = db.scalar(
        select(func.count(PackageAward.id)).where(
            PackageAward.package_id == p.id,
            PackageAward.status == "active",
        )
    ) or 0
    if active > 0:
        raise PackageStateError(
            f"Cannot cancel a package with {active} active award(s); "
            f"cancel those first"
        )
    old_status = p.status
    p.status = "cancelled"
    p.cancelled_at = datetime.now(timezone.utc)
    p.cancelled_by = user.id
    p.cancelled_reason = (reason or "").strip() or None
    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=[{
            "field": "status", "old": old_status, "new": p.status,
        }],
        metadata={
            "reference": p.reference,
            "event": "package.cancelled",
            "reason": p.cancelled_reason,
        },
        request=request,
    )
    return p


def _supplier_kind_guard(supplier: Supplier, kind: str) -> None:
    """Kind/supplier-type coherence (Pack 3.5 — 3-value vocabulary).

    - materials   → bidder must be Supplier OR Contractor.
    - subcontract → bidder must be Contractor (CIS counterparty).
    - consultant  → bidder must be Consultant. (The flip — pre-3.5 the
                    guard rejected Consultant outright; consultant
                    packages now *require* it.)
    - Other       → invalid for every kind.
    """
    st = supplier.supplier_type
    if kind == "materials":
        if st not in ("Supplier", "Contractor"):
            raise ValueError(
                f"materials packages require a Supplier or Contractor "
                f"bidder; got supplier_type={st!r}"
            )
    elif kind == "subcontract":
        if st != "Contractor":
            raise ValueError(
                f"subcontract packages require a Contractor bidder "
                f"(CIS counterparty); got supplier_type={st!r}"
            )
    elif kind == "consultant":
        if st != "Consultant":
            raise ValueError(
                f"consultant packages require a Consultant bidder; "
                f"got supplier_type={st!r}"
            )
    else:  # pragma: no cover — kind constrained by enum + CHECK
        raise ValueError(f"Unknown package kind {kind!r}")


def invite_bidder(
    db: Session, package_id: uuid.UUID,
    *, supplier_id: uuid.UUID,
    user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> PackageBid:
    p = _load_for_write(db, package_id, user, perms)
    if p.status != "out_to_tender":
        raise PackageStateError(
            f"invite_bidder requires out_to_tender; current={p.status}"
        )
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ValueError("Supplier not found")
    if supplier.tenant_id != user.tenant_id and not perms.is_super_admin:
        raise ValueError("Supplier not found")
    _supplier_kind_guard(supplier, p.kind)
    # Idempotency check (DB has UNIQUE; pre-check for clear 409).
    dup = db.scalar(
        select(PackageBid).where(
            PackageBid.package_id == p.id,
            PackageBid.supplier_id == supplier.id,
        )
    )
    if dup is not None:
        raise PackageStateError(
            f"Supplier {supplier_id} already invited to this package"
        )
    bid = PackageBid(
        package_id=p.id,
        supplier_id=supplier.id,
        status="invited",
        total_net=Decimal("0.00"),
    )
    db.add(bid)
    db.flush()
    record_audit(
        db, action="Update", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=[{
            "field": "bids",
            "old": None,
            "new": {
                "bid_id": str(bid.id), "supplier_id": str(supplier.id),
            },
        }],
        metadata={
            "reference": p.reference, "event": "package.invite_bidder",
        },
        request=request,
    )
    return bid


def enter_bid(
    db: Session, bid_id: uuid.UUID,
    *, lines: list[dict[str, Any]],
    user: User, perms: UserPermissions,
    notes: Optional[str] = None,
    request: Optional[Request] = None,
) -> PackageBid:
    bid = db.get(PackageBid, bid_id)
    if bid is None:
        raise PackageNotFoundError("Bid not found")
    p = _load_for_write(db, bid.package_id, user, perms)
    if p.status != "out_to_tender" and p.status != "partially_awarded":
        raise PackageStateError(
            f"enter_bid requires out_to_tender or partially_awarded; "
            f"current={p.status}"
        )
    if bid.status in ("declined", "withdrawn"):
        raise PackageStateError(
            f"Cannot enter figures on a {bid.status} bid"
        )

    if not lines:
        raise ValueError("At least one bid line is required")

    # Validate every package_line_id belongs to the bid's package.
    pkg_lines = {
        pl.id: pl for pl in db.scalars(
            select(PackageLine).where(PackageLine.package_id == p.id)
        ).all()
    }
    by_pl: dict[uuid.UUID, Decimal] = {}
    for line_in in lines:
        pl_id = line_in.get("package_line_id")
        rate_raw = line_in.get("quoted_unit_rate")
        if pl_id is None or rate_raw is None:
            raise ValueError(
                "Each bid line requires package_line_id + quoted_unit_rate"
            )
        if isinstance(pl_id, str):
            try:
                pl_id = uuid.UUID(pl_id)
            except ValueError as e:
                raise ValueError(
                    f"package_line_id is not a valid UUID: {pl_id}"
                ) from e
        if pl_id not in pkg_lines:
            raise ValueError(
                f"package_line_id {pl_id} does not belong to this package"
            )
        rate = _q4(_q(rate_raw, field="quoted_unit_rate"))
        if rate < 0:
            raise ValueError("quoted_unit_rate must be >= 0")
        by_pl[pl_id] = rate

    # Upsert bid lines: delete existing for this bid, then re-create from
    # the validated set. Service is the single writer.
    db.execute(
        PackageBidLine.__table__.delete().where(
            PackageBidLine.package_bid_id == bid.id
        )
    )
    db.flush()
    for pl_id, rate in by_pl.items():
        pl = pkg_lines[pl_id]
        net = _q2(Decimal(str(pl.quantity)) * rate)
        bl = PackageBidLine(
            package_bid_id=bid.id,
            package_line_id=pl_id,
            quoted_unit_rate=rate,
            quoted_net_amount=net,
        )
        db.add(bl)
    db.flush()

    bid.status = "received"
    bid.received_at = datetime.now(timezone.utc)
    if notes is not None:
        bid.notes = (
            notes.strip() if isinstance(notes, str) and notes.strip() else None
        )
    _recompute_bid_total(db, bid)
    db.flush()

    record_audit(
        db, action="Update", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=[{
            "field": "bid", "old": None,
            "new": {
                "bid_id": str(bid.id),
                "total_net": str(bid.total_net),
            },
        }],
        metadata={
            "reference": p.reference,
            "event": "package.enter_bid",
            "bid_id": str(bid.id),
        },
        request=request,
    )
    return bid


def _set_bid_status(
    db: Session, bid_id: uuid.UUID, new_status: str,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> PackageBid:
    bid = db.get(PackageBid, bid_id)
    if bid is None:
        raise PackageNotFoundError("Bid not found")
    p = _load_for_write(db, bid.package_id, user, perms)
    if bid.status == new_status:
        return bid
    if bid.status in ("declined", "withdrawn") and new_status != bid.status:
        raise PackageStateError(
            f"Bid is already {bid.status}; cannot transition to {new_status}"
        )
    old = bid.status
    bid.status = new_status
    db.flush()
    record_audit(
        db, action="Status_Change", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=[{
            "field": "bid.status", "old": old, "new": new_status,
        }],
        metadata={
            "reference": p.reference,
            "event": f"package.bid_{new_status}",
            "bid_id": str(bid.id),
        },
        request=request,
    )
    return bid


def decline_bid(
    db: Session, bid_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> PackageBid:
    return _set_bid_status(
        db, bid_id, "declined", user=user, perms=perms, request=request,
    )


def withdraw_bid(
    db: Session, bid_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> PackageBid:
    return _set_bid_status(
        db, bid_id, "withdrawn", user=user, perms=perms, request=request,
    )


# ---------------------------------------------------------------------------
# Award engine — THE CRITICAL PATH (§3.3)
# ---------------------------------------------------------------------------

def _validate_award_spec(
    db: Session, package: Package, spec: dict[str, Any], pkg_lines_by_id: dict,
) -> tuple[Supplier, Optional[PackageBid], list[dict[str, Any]]]:
    """Per-spec validation; returns (supplier, source_bid_or_None,
    prepared_award_lines).

    Per-line quantity guard is enforced HERE (uses pkg_lines_by_id which
    already aggregates remaining quantity across the in-flight call).
    """
    supplier_id_raw = spec.get("supplier_id")
    if supplier_id_raw is None:
        raise ValueError("award spec missing supplier_id")
    if isinstance(supplier_id_raw, str):
        supplier_id = uuid.UUID(supplier_id_raw)
    else:
        supplier_id = supplier_id_raw
    supplier = db.get(Supplier, supplier_id)
    if supplier is None:
        raise ValueError(f"Supplier {supplier_id} not found")
    if (
        supplier.tenant_id != package.tenant_id
        and supplier.tenant_id != package.tenant_id
    ):
        # double-check is intentional: tenant cross check
        raise ValueError(f"Supplier {supplier_id} not in package tenant")
    _supplier_kind_guard(supplier, package.kind)

    src_bid_id_raw = spec.get("source_bid_id")
    src_bid: Optional[PackageBid] = None
    if src_bid_id_raw is not None:
        src_bid_id = (
            uuid.UUID(src_bid_id_raw) if isinstance(src_bid_id_raw, str)
            else src_bid_id_raw
        )
        src_bid = db.get(PackageBid, src_bid_id)
        if src_bid is None or src_bid.package_id != package.id:
            raise ValueError(
                f"source_bid_id {src_bid_id} does not belong to this package"
            )
        if src_bid.supplier_id != supplier_id:
            raise ValueError(
                "source_bid_id supplier does not match award supplier_id"
            )
        if src_bid.status != "received":
            raise ValueError(
                f"source_bid_id is {src_bid.status}, must be 'received'"
            )

    lines_in = spec.get("lines") or []
    if not lines_in:
        raise ValueError("award spec requires at least one line")

    prepared: list[dict[str, Any]] = []
    bid_rate_by_pl: dict[uuid.UUID, Decimal] = {}
    if src_bid is not None:
        for bl in db.scalars(
            select(PackageBidLine).where(
                PackageBidLine.package_bid_id == src_bid.id
            )
        ).all():
            bid_rate_by_pl[bl.package_line_id] = Decimal(str(bl.quoted_unit_rate))

    for li in lines_in:
        pl_id_raw = li.get("package_line_id")
        if pl_id_raw is None:
            raise ValueError("award line missing package_line_id")
        pl_id = uuid.UUID(pl_id_raw) if isinstance(pl_id_raw, str) else pl_id_raw
        if pl_id not in pkg_lines_by_id:
            raise ValueError(
                f"package_line_id {pl_id} does not belong to this package"
            )
        bucket = pkg_lines_by_id[pl_id]
        qty = _q4(_q(li.get("quantity"), field="quantity"))
        if qty <= 0:
            raise ValueError("award line quantity must be > 0")
        rate = _q4(_q(li.get("awarded_unit_rate"), field="awarded_unit_rate"))
        if rate < 0:
            raise ValueError("awarded_unit_rate must be >= 0")
        if src_bid is not None:
            bid_rate = bid_rate_by_pl.get(pl_id)
            if bid_rate is None:
                raise ValueError(
                    f"source bid does not cover package_line_id {pl_id}"
                )
            if _q4(bid_rate) != rate:
                raise ValueError(
                    f"awarded_unit_rate {rate} does not match bid rate "
                    f"{bid_rate} for package_line {pl_id} — use a fast-track "
                    f"award (source_bid_id=null) if you want a different rate"
                )
        # Per-line quantity guard, considering the in-flight bucket.
        remaining = bucket["remaining_qty"]
        if qty > remaining:
            raise ValueError(
                f"awarded quantity {qty} exceeds remaining {remaining} for "
                f"package_line {pl_id}"
            )
        bucket["remaining_qty"] = remaining - qty
        net = _q2(qty * rate)
        prepared.append({
            "package_line_id": pl_id,
            "quantity": qty,
            "awarded_unit_rate": rate,
            "awarded_net": net,
            "package_line": bucket["pl"],
        })
    return supplier, src_bid, prepared


def award_package(
    db: Session, package_id: uuid.UUID,
    *, awards: list[dict[str, Any]],
    user: User, perms: UserPermissions,
    request: Optional[Request] = None,
) -> Package:
    """The award engine — one DB transaction, all-or-nothing, package row
    locked FOR UPDATE for the whole operation.
    """
    if not awards:
        raise ValueError("At least one award spec is required")

    # 1. Lock the package row FOR UPDATE — serialises concurrent awards
    # (lost-update test: T-AW-9).
    p = _load_for_write(db, package_id, user, perms, lock_for_update=True)

    fast_track_only = all(
        spec.get("source_bid_id") is None for spec in awards
    )
    if p.status == "draft":
        if not fast_track_only:
            raise PackageStateError(
                "Cannot award from draft unless ALL specs are fast-track "
                "(source_bid_id=null); send_to_tender first"
            )
    elif p.status not in ("out_to_tender", "partially_awarded"):
        raise PackageStateError(
            f"Cannot award from status {p.status}"
        )

    # 2. Build per-line remaining-quantity buckets from existing active
    # awards.
    pkg_lines = db.scalars(
        select(PackageLine).where(PackageLine.package_id == p.id)
    ).all()
    if not pkg_lines:
        raise PackageStateError("Cannot award a package with no lines")

    existing_awarded_qty: dict[uuid.UUID, Decimal] = {}
    rows = db.execute(
        select(
            PackageAwardLine.package_line_id,
            func.coalesce(func.sum(PackageAwardLine.quantity), 0),
        )
        .join(PackageAward, PackageAward.id == PackageAwardLine.package_award_id)
        .where(
            PackageAward.package_id == p.id,
            PackageAward.status == "active",
        )
        .group_by(PackageAwardLine.package_line_id)
    ).all()
    for pl_id, qsum in rows:
        existing_awarded_qty[pl_id] = Decimal(str(qsum))
    pkg_lines_by_id: dict[uuid.UUID, dict[str, Any]] = {}
    for pl in pkg_lines:
        awarded_qty = existing_awarded_qty.get(pl.id, Decimal("0"))
        remaining = Decimal(str(pl.quantity)) - awarded_qty
        pkg_lines_by_id[pl.id] = {
            "pl": pl,
            "remaining_qty": _q4(remaining),
        }

    # 3. Validate each spec (per-line guard enforced via bucket mutation).
    prepared: list[tuple[Supplier, Optional[PackageBid], list[dict[str, Any]], dict[str, Any]]] = []
    for spec in awards:
        supplier, src_bid, prepared_lines = _validate_award_spec(
            db, p, spec, pkg_lines_by_id,
        )
        prepared.append((supplier, src_bid, prepared_lines, spec))

    # 4. Header Σ-guard (LD-P3).
    new_net_total = Decimal("0")
    for _supplier, _src_bid, lines_prep, _spec in prepared:
        for pl in lines_prep:
            new_net_total += pl["awarded_net"]
    existing_active_net = Decimal(str(p.awarded_net))
    total_after = _q2(existing_active_net + new_net_total)
    total_cap = _q2(Decimal(str(p.total_net)) + _HEADER_TOLERANCE)
    if total_after > total_cap:
        overage = _q2(total_after - Decimal(str(p.total_net)))
        raise ValueError(
            f"Award would exceed package total: package.total_net="
            f"{p.total_net}, existing active awards={existing_active_net}, "
            f"new awards={_q2(new_net_total)}, total after="
            f"{total_after}, overage={overage} (limit "
            f"{Decimal(str(p.total_net))} + £{_HEADER_TOLERANCE} tolerance)"
        )

    # 5. Create downstream FIRST, then award + award_lines with the
    # downstream id already populated (the CK on package_awards enforces
    # exactly-one downstream at INSERT time — Postgres doesn't allow
    # DEFERRABLE on CHECK).
    created_awards: list[PackageAward] = []
    for supplier, src_bid, lines_prep, spec in prepared:
        awarded_net_total = _q2(
            sum((pl["awarded_net"] for pl in lines_prep), Decimal("0"))
        )
        po_id: Optional[uuid.UUID] = None
        sc_id: Optional[uuid.UUID] = None
        downstream_kind: str
        if p.kind == "materials":
            po_payload: dict[str, Any] = {
                "supplier_id": str(supplier.id),
                "budget_id": str(p.budget_id),
                # Pack 3.5 — thread the package_id into the PO create
                # so the downstream PO carries its origin link.
                "package_id": str(p.id),
                "lines": [
                    {
                        "budget_line_id": str(
                            ln["package_line"].budget_line_id
                        ),
                        "cost_code": ln["package_line"].cost_code,
                        "description": ln["package_line"].description,
                        "quantity": str(ln["quantity"]),
                        "unit_rate": str(ln["awarded_unit_rate"]),
                        "unit": ln["package_line"].unit,
                    }
                    for ln in lines_prep
                ],
            }
            if spec.get("required_by_date"):
                po_payload["required_by_date"] = spec["required_by_date"]
            if spec.get("delivery_address"):
                po_payload["delivery_address"] = spec["delivery_address"]
            po = po_svc.create_po(
                db,
                user=user, perms=perms,
                project_id=p.project_id,
                payload=po_payload,
                request=request,
            )
            po_id = po.id
            downstream_kind = "purchase_order"
            downstream_id = po.id
        elif p.kind == "subcontract":
            sc_kwargs: dict[str, Any] = {
                "title": f"{p.reference} — {p.title} ({supplier.name})"[:200],
                "original_contract_sum": str(awarded_net_total),
                # Pack 3.5 — thread the package_id into the SC create
                # so the downstream subcontract carries its origin link.
                "package_id": p.id,
            }
            if spec.get("scope_description"):
                sc_kwargs["scope_description"] = spec["scope_description"]
            if spec.get("retention_pct") is not None:
                sc_kwargs["retention_pct"] = str(spec["retention_pct"])
            if spec.get("cis_applies") is not None:
                sc_kwargs["cis_applies"] = bool(spec["cis_applies"])
            sc = sc_svc.create_subcontract(
                db,
                project_id=p.project_id,
                subcontractor_id=supplier.id,
                user=user, perms=perms,
                request=request,
                **sc_kwargs,
            )
            sc_id = sc.id
            downstream_kind = "subcontract"
            downstream_id = sc.id
        elif p.kind == "consultant":
            # Pack 3.5 — consultant packages route to PO (NOT
            # subcontract). Professional fees are CIS-clean by
            # construction: the PO path applies NO CIS, and
            # `create_subcontract` would hard-reject any supplier with
            # `supplier_type != 'Contractor'` (LD2) — so a consultant
            # can never be a subcontract counterparty anyway. Identical
            # payload shape to the materials branch.
            po_payload = {
                "supplier_id": str(supplier.id),
                "budget_id": str(p.budget_id),
                "package_id": str(p.id),
                "lines": [
                    {
                        "budget_line_id": str(
                            ln["package_line"].budget_line_id
                        ),
                        "cost_code": ln["package_line"].cost_code,
                        "description": ln["package_line"].description,
                        "quantity": str(ln["quantity"]),
                        "unit_rate": str(ln["awarded_unit_rate"]),
                        "unit": ln["package_line"].unit,
                    }
                    for ln in lines_prep
                ],
            }
            if spec.get("required_by_date"):
                po_payload["required_by_date"] = spec["required_by_date"]
            if spec.get("delivery_address"):
                po_payload["delivery_address"] = spec["delivery_address"]
            po = po_svc.create_po(
                db,
                user=user, perms=perms,
                project_id=p.project_id,
                payload=po_payload,
                request=request,
            )
            po_id = po.id
            downstream_kind = "purchase_order"
            downstream_id = po.id
        else:  # pragma: no cover — kind enum constrained
            raise PackageStateError(f"Unknown package kind {p.kind!r}")

        award = PackageAward(
            package_id=p.id,
            supplier_id=supplier.id,
            source_bid_id=(src_bid.id if src_bid is not None else None),
            status="active",
            awarded_net=awarded_net_total,
            created_purchase_order_id=po_id,
            created_subcontract_id=sc_id,
            created_by=user.id,
            updated_by=user.id,
        )
        db.add(award)
        db.flush()  # need award.id for award_lines
        for ln in lines_prep:
            db.add(PackageAwardLine(
                package_award_id=award.id,
                package_line_id=ln["package_line_id"],
                quantity=ln["quantity"],
                awarded_unit_rate=ln["awarded_unit_rate"],
                awarded_net=ln["awarded_net"],
            ))
        db.flush()

        record_audit(
            db, action="Approve", resource_type="packages",
            resource_id=p.id, actor_user_id=user.id,
            project_id=p.project_id,
            field_changes=[{
                "field": "award", "old": None,
                "new": {
                    "award_id": str(award.id),
                    "supplier_id": str(supplier.id),
                    "awarded_net": str(awarded_net_total),
                    "source_bid_id": (
                        str(src_bid.id) if src_bid is not None else None
                    ),
                    f"{downstream_kind}_id": str(downstream_id),
                },
            }],
            metadata={
                "reference": p.reference,
                "event": "package.award",
                "downstream_kind": downstream_kind,
                "downstream_id": str(downstream_id),
                "awarded_net": str(awarded_net_total),
            },
            request=request,
        )
        created_awards.append(award)

    # 6. Recompute package totals + status.
    if p.awarded_at is None:
        p.awarded_at = datetime.now(timezone.utc)
        p.awarded_by = user.id
    _recompute_award_totals(db, p)
    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()
    return p


def cancel_award(
    db: Session, award_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
    reason: str,
    request: Optional[Request] = None,
) -> PackageAward:
    """Cancel an active award. Blocks if downstream PO/SC has progressed."""
    if not reason or not reason.strip():
        raise ValueError("reason is required to cancel an award")
    award = db.get(PackageAward, award_id)
    if award is None:
        raise PackageNotFoundError("Award not found")
    p = _load_for_write(db, award.package_id, user, perms)
    if award.status != "active":
        raise PackageStateError(
            f"Award is {award.status}; only active awards can be cancelled"
        )
    # Re-lock the award row (defensive — package lock serialises the
    # whole package; child rows live under it).
    award = db.scalar(
        select(PackageAward).where(PackageAward.id == award_id)
        .with_for_update()
    )

    # Block on downstream progress.
    if award.created_purchase_order_id is not None:
        po = db.get(PurchaseOrder, award.created_purchase_order_id)
        if po is not None and po.status not in ("draft", "pending_approval"):
            raise PackageStateError(
                f"award's purchase order has progressed to {po.status}; "
                f"void it in the PO module first before cancelling the award"
            )
    if award.created_subcontract_id is not None:
        sc = db.get(Subcontract, award.created_subcontract_id)
        if sc is not None and sc.status != "Draft":
            raise PackageStateError(
                f"award's subcontract is {sc.status}; terminate it in the "
                f"subcontract module first before cancelling the award"
            )

    old_status = award.status
    award.status = "cancelled"
    award.cancelled_at = datetime.now(timezone.utc)
    award.cancelled_by = user.id
    award.cancelled_reason = reason.strip()
    award.updated_by = user.id
    award.updated_at = datetime.now(timezone.utc)
    db.flush()

    _recompute_award_totals(db, p)
    p.updated_by = user.id
    p.updated_at = datetime.now(timezone.utc)
    db.flush()

    record_audit(
        db, action="Status_Change", resource_type="packages",
        resource_id=p.id, actor_user_id=user.id,
        project_id=p.project_id,
        field_changes=[{
            "field": "award.status", "old": old_status, "new": award.status,
        }],
        metadata={
            "reference": p.reference,
            "event": "package.award_cancelled",
            "award_id": str(award.id),
            "reason": award.cancelled_reason,
        },
        request=request,
    )
    return award


# ---------------------------------------------------------------------------
# Read / serialise
# ---------------------------------------------------------------------------

# Fields gated by `packages.view_sensitive`.
_HEADER_SENSITIVE = frozenset({"total_net", "awarded_net"})
_BID_SENSITIVE = frozenset({"total_net"})
_BID_LINE_SENSITIVE = frozenset({"quoted_unit_rate", "quoted_net_amount"})
_AWARD_SENSITIVE = frozenset({"awarded_net"})
_AWARD_LINE_SENSITIVE = frozenset({"awarded_unit_rate", "awarded_net"})
_PACKAGE_LINE_SENSITIVE = frozenset({
    "budgeted_unit_rate", "budgeted_net_amount",
})


def _ser_package_line(
    pl: PackageLine,
    *,
    include_sensitive: bool,
    cost_code_names: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(pl.id),
        "package_id": str(pl.package_id),
        "budget_line_id": str(pl.budget_line_id),
        "cost_code": pl.cost_code,
        # Pack 3.5 §5.1 — human-readable name for grouping headers
        # (e.g. "4.02 — Substructure"). Resolved per-package via a
        # single batched query in `serialise_package`; falls back to
        # None when `db` is not threaded through.
        "cost_code_name": (
            (cost_code_names or {}).get(pl.cost_code)
        ),
        "line_number": int(pl.line_number),
        "description": pl.description,
        "quantity": str(pl.quantity),
        "unit": pl.unit,
        "notes": pl.notes,
    }
    if include_sensitive:
        out["budgeted_unit_rate"] = str(pl.budgeted_unit_rate)
        out["budgeted_net_amount"] = str(pl.budgeted_net_amount)
    else:
        for k in _PACKAGE_LINE_SENSITIVE:
            out[k] = None
    return out


def _ser_bid(bid: PackageBid, *, include_sensitive: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(bid.id),
        "package_id": str(bid.package_id),
        "supplier_id": str(bid.supplier_id),
        "status": bid.status,
        "received_at": (
            bid.received_at.isoformat() if bid.received_at else None
        ),
        "notes": bid.notes,
    }
    if include_sensitive:
        out["total_net"] = str(bid.total_net)
        out["lines"] = [
            {
                "id": str(bl.id),
                "package_line_id": str(bl.package_line_id),
                "quoted_unit_rate": str(bl.quoted_unit_rate),
                "quoted_net_amount": str(bl.quoted_net_amount),
            }
            for bl in sorted(
                bid.bid_lines, key=lambda x: str(x.package_line_id),
            )
        ]
    else:
        out["total_net"] = None
        # Without view_sensitive: still surface package_line_id (structure
        # is not sensitive — pricing is).
        out["lines"] = [
            {
                "id": str(bl.id),
                "package_line_id": str(bl.package_line_id),
                "quoted_unit_rate": None,
                "quoted_net_amount": None,
            }
            for bl in sorted(
                bid.bid_lines, key=lambda x: str(x.package_line_id),
            )
        ]
    return out


def _ser_award(award: PackageAward, *, include_sensitive: bool) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": str(award.id),
        "package_id": str(award.package_id),
        "supplier_id": str(award.supplier_id),
        "source_bid_id": (
            str(award.source_bid_id) if award.source_bid_id else None
        ),
        "status": award.status,
        "created_purchase_order_id": (
            str(award.created_purchase_order_id)
            if award.created_purchase_order_id else None
        ),
        "created_subcontract_id": (
            str(award.created_subcontract_id)
            if award.created_subcontract_id else None
        ),
        "cancelled_at": (
            award.cancelled_at.isoformat() if award.cancelled_at else None
        ),
        "cancelled_reason": award.cancelled_reason,
    }
    if include_sensitive:
        out["awarded_net"] = str(award.awarded_net)
        out["lines"] = [
            {
                "id": str(ln.id),
                "package_line_id": str(ln.package_line_id),
                "quantity": str(ln.quantity),
                "awarded_unit_rate": str(ln.awarded_unit_rate),
                "awarded_net": str(ln.awarded_net),
            }
            for ln in sorted(
                award.award_lines, key=lambda x: str(x.package_line_id),
            )
        ]
    else:
        out["awarded_net"] = None
        out["lines"] = [
            {
                "id": str(ln.id),
                "package_line_id": str(ln.package_line_id),
                "quantity": str(ln.quantity),
                "awarded_unit_rate": None,
                "awarded_net": None,
            }
            for ln in sorted(
                award.award_lines, key=lambda x: str(x.package_line_id),
            )
        ]
    return out


def serialise_package(
    p: Package, *, with_sensitive: bool,
    db: Optional[Session] = None,
) -> dict[str, Any]:
    # Pack 3.5 §5.1 — resolve cost_code → name in ONE batched query
    # against the package's distinct codes, so the grouped UI gets a
    # human label for the header (e.g. "4.02 — Substructure"). When
    # db is not threaded, fall back silently (cost_code_name = None).
    cost_code_names: dict[str, str] = {}
    if db is not None and p.lines:
        from app.models.cost_codes import CostCode
        codes = sorted({pl.cost_code for pl in p.lines if pl.cost_code})
        if codes:
            rows = db.execute(
                select(CostCode.code, CostCode.name).where(
                    CostCode.code.in_(codes)
                )
            ).all()
            cost_code_names = {code: name for code, name in rows}
    out: dict[str, Any] = {
        "id": str(p.id),
        "tenant_id": str(p.tenant_id),
        "project_id": str(p.project_id),
        "budget_id": str(p.budget_id),
        "reference": p.reference,
        "title": p.title,
        "kind": p.kind,
        "status": p.status,
        "description": p.description,
        "out_to_tender_at": (
            p.out_to_tender_at.isoformat() if p.out_to_tender_at else None
        ),
        "out_to_tender_by": (
            str(p.out_to_tender_by) if p.out_to_tender_by else None
        ),
        "awarded_at": (p.awarded_at.isoformat() if p.awarded_at else None),
        "awarded_by": (str(p.awarded_by) if p.awarded_by else None),
        "cancelled_at": (
            p.cancelled_at.isoformat() if p.cancelled_at else None
        ),
        "cancelled_by": (str(p.cancelled_by) if p.cancelled_by else None),
        "cancelled_reason": p.cancelled_reason,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }
    if with_sensitive:
        out["total_net"] = str(p.total_net)
        out["awarded_net"] = str(p.awarded_net)
    else:
        for k in _HEADER_SENSITIVE:
            out[k] = None
    out["lines"] = [
        _ser_package_line(
            pl, include_sensitive=with_sensitive,
            cost_code_names=cost_code_names,
        )
        for pl in sorted(p.lines, key=lambda x: x.line_number)
    ]
    out["bids"] = [
        _ser_bid(b, include_sensitive=with_sensitive)
        for b in sorted(p.bids, key=lambda x: x.created_at)
    ]
    out["awards"] = [
        _ser_award(a, include_sensitive=with_sensitive)
        for a in sorted(p.awards, key=lambda x: x.created_at)
    ]
    return out


def get_package(
    db: Session, package_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
) -> Package:
    return _load_for_read(db, package_id, user, perms)


def list_packages(
    db: Session, *, user: User, perms: UserPermissions,
    project_id: Optional[uuid.UUID] = None,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 50, offset: int = 0,
) -> list[Package]:
    stmt = select(Package).where(Package.tenant_id == user.tenant_id)
    if project_id is not None:
        # Scope-check the project (cross-tenant → 404).
        project = db.get(Project, project_id)
        if project is None:
            raise PackageNotFoundError("Project not found")
        _scope_check_project(db, project, user, perms)
        stmt = stmt.where(Package.project_id == project_id)
    elif not perms.is_super_admin:
        allowed = _visible_project_ids(db, user.id, user.tenant_id)
        if allowed is not None:
            if not allowed:
                return []
            stmt = stmt.where(Package.project_id.in_(allowed))
    if status is not None:
        stmt = stmt.where(Package.status == status)
    if kind is not None:
        stmt = stmt.where(Package.kind == kind)
    stmt = stmt.options(
        selectinload(Package.lines),
        selectinload(Package.bids).selectinload(PackageBid.bid_lines),
        selectinload(Package.awards).selectinload(PackageAward.award_lines),
    ).order_by(Package.created_at.desc()).limit(limit).offset(offset)
    return list(db.scalars(stmt).all())


def list_bids_for_package(
    db: Session, package_id: uuid.UUID,
    *, user: User, perms: UserPermissions,
) -> list[PackageBid]:
    p = _load_for_read(db, package_id, user, perms)
    bids = db.scalars(
        select(PackageBid).where(PackageBid.package_id == p.id)
        .options(selectinload(PackageBid.bid_lines))
        .order_by(PackageBid.created_at)
    ).all()
    return list(bids)
