"""Canonical appraisal recompute pipeline — Prompt 2.2.

Eight-step order (enforced):
  1. Units          → total_gdv from unit mix; build cost roll-up.
  2. Cost pass 1    → resolve Manual + Percentage_Of_Land lines first,
                      and the unit-derived Construction base lines.
  3. GDV header     → set appraisal.total_gdv + unit build aggregate.
  4. SDLT engine    → Acquisition/SDLT_Engine lines computed from
                      land_purchase_price via sdlt.calculate.
  5. Cost pass 2    → Percentage_Of_GDV / Percentage_Of_Build_Cost lines
                      (must run AFTER pass 1 + GDV + SDLT are final).
  6. Finance engine → per-facility interest + fees; roll up to header.
  7. Header recompute → category totals + profit + margins.
  8. updated_at / is_stale flag cleared.

The pipeline never persists partial state — the caller owns commit/rollback.
All money is Decimal. No floats.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.appraisals import (
    Appraisal, AppraisalCostLine, AppraisalFinanceFacility, AppraisalUnit,
)
from app.services import sdlt as sdlt_svc
from app.services.appraisal_classification import classify as classify_sdlt
from app.services.finance_engine import FacilityInput, compute_facility


log = logging.getLogger("syhomes.appraisal.calc")

_PENNY = Decimal("0.01")
_RATE = Decimal("0.0001")
_ZERO = Decimal("0")


def _penny(x: Decimal) -> Decimal:
    return x.quantize(_PENNY, rounding=ROUND_HALF_UP)


def _rate(x: Decimal) -> Decimal:
    return x.quantize(_RATE, rounding=ROUND_HALF_UP)


@dataclass
class RecomputeResult:
    total_gdv: Decimal
    total_unit_build_cost: Decimal
    total_acquisition_cost: Decimal
    total_build_cost: Decimal
    total_professional_fees: Decimal
    total_statutory_cost: Decimal
    total_finance_cost: Decimal
    total_contingency: Decimal
    total_sales_cost: Decimal
    total_other_cost: Decimal
    total_cost: Decimal
    total_profit: Decimal
    profit_on_cost_pct: Decimal
    profit_on_gdv_pct: Decimal
    sdlt_amount: Decimal
    metadata: dict = field(default_factory=dict)


def _cat_totals(
    lines: list[AppraisalCostLine],
) -> dict[str, Decimal]:
    totals = {
        "Acquisition": _ZERO,
        "Construction": _ZERO,
        "Professional_Fees": _ZERO,
        "Statutory": _ZERO,
        "Finance": _ZERO,
        "Contingency": _ZERO,
        "Sales": _ZERO,
        "Other": _ZERO,
    }
    for line in lines:
        cat = line.category
        totals[cat] = totals.get(cat, _ZERO) + Decimal(line.amount or 0)
    return totals


def recompute(
    db: Session,
    appraisal: Appraisal,
    *,
    override_land_price: Optional[Decimal] = None,
) -> RecomputeResult:
    """Run the 8-step recompute pipeline on the given appraisal row.

    Mutates in-place: appraisal cached KPIs, cost-line amounts (for
    auto_source != Manual), and facility cached outputs. Does NOT commit.

    If `override_land_price` is passed, it is used instead of the
    header's `land_purchase_price` for THIS recompute only — used by
    the RLV solver's iteration. The header value is left untouched.
    """
    # Flip ORM lists to plain Python lists so we can order/iterate safely.
    units: list[AppraisalUnit] = list(appraisal.units or [])
    lines: list[AppraisalCostLine] = list(appraisal.cost_lines or [])
    facilities: list[AppraisalFinanceFacility] = list(
        appraisal.finance_facilities or []
    )
    land_price = Decimal(
        override_land_price if override_land_price is not None
        else appraisal.land_purchase_price
    )
    meta: dict = {}

    # ---------- 1. Units ------------------------------------------------
    total_gdv = _ZERO
    total_unit_build = _ZERO
    for u in units:
        q = Decimal(u.quantity or 0)
        total_gdv += q * Decimal(u.price_per_unit or 0)
        total_unit_build += q * Decimal(u.build_cost_per_unit or 0)
    total_gdv = _penny(total_gdv)
    total_unit_build = _penny(total_unit_build)

    # ---------- 2. Cost pass 1 -----------------------------------------
    # Resolve Manual + Percentage_Of_Land here.
    # Percentage_Of_Build_Cost / Percentage_Of_GDV are deferred to pass 2.
    # Also write the land_purchase_price into a line whose auto_source ==
    # Percentage_Of_Land with percentage = 100 (convention).
    for line in lines:
        src = line.auto_source
        if src == "Manual":
            # amount is already user-supplied; no-op.
            continue
        if src == "Percentage_Of_Land":
            pct = Decimal(line.percentage or 0)
            line.amount = _penny(land_price * pct / Decimal("100"))
            continue

    # Roll up the "land line" if appraisal has a dedicated ACQ-01 cost
    # line: identify by category==Acquisition AND auto_source=="Manual"
    # with `label` starting "Land" — else, the header's land_purchase_price
    # stands alone (added to acquisition total below).
    has_land_line = any(
        l.category == "Acquisition" and Decimal(l.amount or 0) == land_price
        and (l.label or "").lower().startswith("land")
        for l in lines
    )
    meta["has_land_line"] = has_land_line

    # ---------- 3. GDV header ------------------------------------------
    appraisal.gdv_total = total_gdv

    # ---------- 4. SDLT engine -----------------------------------------
    cat = classify_sdlt(
        land_purchase_price=land_price,
        sdlt_category=appraisal.sdlt_category,
        developer_relief=appraisal.developer_relief,
    )
    try:
        sdlt_amount = sdlt_svc.calculate(
            db,
            consideration=land_price,
            category=cat,
            reference_date=appraisal.reference_date,
        )
    except (LookupError, ValueError) as e:
        log.warning("SDLT calc failed: %s — defaulting to 0", e)
        sdlt_amount = _ZERO
    meta["sdlt_category"] = cat
    meta["sdlt_amount"] = str(sdlt_amount)

    # Stamp SDLT_Engine lines.
    for line in lines:
        if line.auto_source == "SDLT_Engine":
            line.amount = _penny(sdlt_amount)

    # ---------- 5. Cost pass 2 -----------------------------------------
    # Compute the build cost base BEFORE percentage-of-build lines so they
    # reference only the first-pass figure. Percentage_Of_Build_Cost is
    # based on total Construction lines from pass 1 (plus unit build roll).
    build_base = _penny(sum(
        (Decimal(l.amount or 0) for l in lines if l.category == "Construction"),
        _ZERO,
    ) + total_unit_build)
    meta["build_base_for_pct_lines"] = str(build_base)

    for line in lines:
        if line.auto_source == "Percentage_Of_Build_Cost":
            pct = Decimal(line.percentage or 0)
            line.amount = _penny(build_base * pct / Decimal("100"))
        elif line.auto_source == "Percentage_Of_GDV":
            pct = Decimal(line.percentage or 0)
            line.amount = _penny(total_gdv * pct / Decimal("100"))

    # Contingency line — if present as auto_source=Percentage_Of_Build_Cost
    # it's already handled above; if Manual, we honour the user amount.
    # Header-level contingency_pct isn't auto-applied (the spec uses the
    # line-level mechanism) — we just expose it on the row.

    # ---------- 6. Finance engine --------------------------------------
    total_finance = _ZERO
    for fac in facilities:
        out = compute_facility(FacilityInput(
            label=fac.label,
            principal_amount=Decimal(fac.principal_amount or 0),
            interest_rate_pct=Decimal(fac.interest_rate_pct or 0),
            arrangement_fee_pct=Decimal(fac.arrangement_fee_pct or 0),
            exit_fee_pct=Decimal(fac.exit_fee_pct or 0),
            interest_mode=fac.interest_mode,
            drawn_from_month=int(fac.drawn_from_month or 0),
            drawn_to_month=int(fac.drawn_to_month or 0),
        ))
        fac.total_interest = out.total_interest
        fac.total_fees = out.total_fees
        fac.total_finance_cost = out.total_finance_cost
        total_finance += out.total_finance_cost

    # Stamp Finance_Engine auto lines at the header-level total.
    for line in lines:
        if line.auto_source == "Finance_Engine":
            line.amount = _penny(total_finance)

    # ---------- 7. Header recompute ------------------------------------
    cat_tot = _cat_totals(lines)

    acq_total = cat_tot["Acquisition"]
    # If no land line, fold land_purchase_price into acquisition.
    if not has_land_line:
        acq_total += land_price
    # SDLT is already on SDLT_Engine-sourced lines (category=Acquisition
    # or Statutory depending on user setup) — don't double count.

    construction_total = cat_tot["Construction"] + total_unit_build
    prof_fees = cat_tot["Professional_Fees"]
    statutory = cat_tot["Statutory"]
    finance_tot = max(cat_tot["Finance"], _penny(total_finance))
    contingency = cat_tot["Contingency"]
    sales = cat_tot["Sales"]
    other = cat_tot["Other"]

    total_cost = _penny(
        acq_total + construction_total + prof_fees + statutory
        + finance_tot + contingency + sales + other
    )
    total_profit = _penny(total_gdv - total_cost)

    poc = _ZERO
    pog = _ZERO
    if total_cost > _ZERO:
        poc = _rate((total_profit / total_cost) * Decimal("100"))
    if total_gdv > _ZERO:
        pog = _rate((total_profit / total_gdv) * Decimal("100"))

    appraisal.total_acquisition_cost = _penny(acq_total)
    appraisal.total_build_cost = _penny(construction_total)
    appraisal.total_professional_fees = _penny(prof_fees)
    appraisal.total_statutory_cost = _penny(statutory)
    appraisal.total_finance_cost = _penny(finance_tot)
    appraisal.total_contingency = _penny(contingency)
    appraisal.total_sales_cost = _penny(sales)
    appraisal.total_other_cost = _penny(other)
    appraisal.total_cost = total_cost
    appraisal.profit_total = total_profit
    appraisal.profit_on_cost_pct = poc
    appraisal.profit_on_gdv_pct = pog

    # ---------- 8. updated_at / is_stale -------------------------------
    appraisal.updated_at = datetime.now(timezone.utc)
    appraisal.is_stale = False
    prev_meta = appraisal.computation_metadata or {}
    if isinstance(prev_meta, dict):
        prev_meta.update(meta)
        prev_meta["computed_at"] = appraisal.updated_at.isoformat()
    appraisal.computation_metadata = prev_meta

    # ---------- 9. revision deltas (2.3 C2) ----------------------------
    # If this appraisal is the `to` side of a revision row, refresh its
    # delta_gdv / delta_total_cost / delta_profit. Idempotent — no-op for
    # v1-of-any-scenario rows without an inbound revision.
    _recompute_revision_deltas(db, appraisal)

    return RecomputeResult(
        total_gdv=total_gdv,
        total_unit_build_cost=total_unit_build,
        total_acquisition_cost=appraisal.total_acquisition_cost,
        total_build_cost=appraisal.total_build_cost,
        total_professional_fees=appraisal.total_professional_fees,
        total_statutory_cost=appraisal.total_statutory_cost,
        total_finance_cost=appraisal.total_finance_cost,
        total_contingency=appraisal.total_contingency,
        total_sales_cost=appraisal.total_sales_cost,
        total_other_cost=appraisal.total_other_cost,
        total_cost=total_cost,
        total_profit=total_profit,
        profit_on_cost_pct=poc,
        profit_on_gdv_pct=pog,
        sdlt_amount=sdlt_amount,
        metadata=meta,
    )



def _recompute_revision_deltas(db: Session, appraisal: Appraisal) -> None:
    """Refresh delta_gdv / delta_total_cost / delta_profit for this appraisal.

    If this appraisal is the `to` side of an appraisal_revisions row, compute
    the delta against the `from` side. Idempotent — no-op for appraisals
    without an inbound revision (e.g. v1 of any scenario).
    """
    # Lazy import to avoid a circular dependency at module load time.
    from app.models.appraisal_governance import AppraisalRevision
    from sqlalchemy import select

    rev = db.execute(
        select(AppraisalRevision).where(
            AppraisalRevision.appraisal_id_to == appraisal.id,
        )
    ).scalar_one_or_none()
    if rev is None:
        return
    src = db.get(Appraisal, rev.appraisal_id_from)
    if src is None:
        return
    rev.delta_gdv = _penny(
        Decimal(appraisal.gdv_total or 0) - Decimal(src.gdv_total or 0)
    )
    rev.delta_total_cost = _penny(
        Decimal(appraisal.total_cost or 0) - Decimal(src.total_cost or 0)
    )
    rev.delta_profit = _penny(
        Decimal(appraisal.profit_total or 0) - Decimal(src.profit_total or 0)
    )
    db.flush()
