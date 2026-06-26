"""RLV (Residual Land Value) solver — Prompt 2.2 / C4 rewrite.

Bracketed bisection solver. Given a target margin (on-cost or on-gdv),
finds the land purchase price that produces that margin, holding the
rest of the appraisal constant.

profit_gap(L) is monotonically non-increasing in L (raising land raises
acquisition + SDLT and changes nothing else), so a sign change brackets
exactly one root and bisection is guaranteed to converge.

Three honest outcomes:
  - converged=True  : root found within £1 tolerance
  - converged=False + message : UNREACHABLE (target missed even at £0
    land) or DEGENERATE (no GDV to anchor)

Does NOT mutate the appraisal's land_purchase_price — the caller decides
whether to write rlv_computed_land_value back to the header.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.appraisals import Appraisal
from app.services.appraisal_calc import recompute


log = logging.getLogger("syhomes.appraisal.rlv")

_PENNY = Decimal("0.01")
_ZERO = Decimal("0")
# Safety cap only — the bracket-tolerance exit fires first in practice.
MAX_ITERATIONS = 60
# Half a penny: when the land bracket is this narrow, the penny-rounded
# answer is exact.
_BRACKET_TOL = Decimal("0.005")
# Land can never sensibly exceed this multiple of GDV; upper search bound.
_GDV_CEILING_MULT = Decimal("2")
# Profit-gap tolerance in £ (legacy behaviour: within £1 of target).
_GAP_TOL = Decimal("1.00")


@dataclass
class RlvResult:
    converged: bool
    iterations: int
    land_value: Decimal
    basis: str
    target_pct: Decimal
    achieved_pct: Decimal
    message: Optional[str] = None


def solve(
    db: Session,
    appraisal: Appraisal,
    *,
    basis: str,          # "on_cost" | "on_gdv"
    target_pct: Decimal,
) -> RlvResult:
    """Solve for the land_purchase_price that hits the target margin.

    Bracket [0, 2*GDV] then bisect. profit_gap is monotone non-increasing
    in land, so gap(0) >= 0 >= gap(ceiling) brackets the root.
    """
    if basis not in ("on_cost", "on_gdv"):
        raise ValueError(f"Unknown RLV basis: {basis!r}")

    target_pct = Decimal(target_pct)
    tgt = target_pct / Decimal("100")

    def profit_gap(land: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        """Return (gap, total_cost, total_gdv) at `land`.

        gap = total_profit(L) - required_profit_for_target(L)."""
        res = recompute(db, appraisal, override_land_price=land)
        if basis == "on_cost":
            required = res.total_cost * tgt
        else:
            required = res.total_gdv * tgt
        return (res.total_profit - required, res.total_cost, res.total_gdv)

    # --- Degenerate input: no sales value to anchor the search ----------
    gap0, cost0, gdv0 = profit_gap(_ZERO)
    iters = 1
    if gdv0 <= _ZERO:
        return RlvResult(
            False, iters, _penny(_ZERO), basis, target_pct, Decimal("0.0000"),
            message=(
                "Cannot solve RLV: appraisal has no sales value (GDV is zero). "
                "Add units with sale prices first."
            ),
        )

    ceiling = _penny(gdv0 * _GDV_CEILING_MULT)

    # --- Lower bound L=0 -------------------------------------------------
    if abs(gap0) <= _GAP_TOL:
        achieved = _achieved_pct(cost0, gdv0, gap0, tgt, basis)
        return RlvResult(True, iters, _penny(_ZERO), basis, target_pct, achieved)
    if gap0 < _ZERO:
        achieved = _achieved_pct(cost0, gdv0, gap0, tgt, basis)
        return RlvResult(
            False, iters, _penny(_ZERO), basis, target_pct, achieved,
            message=(
                "Target margin unreachable: not achievable even at £0 land price. "
                f"Best achievable margin is {achieved}% at £0 land."
            ),
        )

    # --- Upper bound L=ceiling ------------------------------------------
    gap_hi, cost_hi, gdv_hi = profit_gap(ceiling)
    iters += 1
    if gap_hi > _ZERO:
        achieved = _achieved_pct(cost_hi, gdv_hi, gap_hi, tgt, basis)
        return RlvResult(
            False, iters, _penny(ceiling), basis, target_pct, achieved,
            message=(
                "Target margin still exceeded at the maximum search land price "
                f"(£{ceiling}); appraisal structure is degenerate."
            ),
        )

    # --- Bisection: gap(0) > 0 > gap(ceiling), root bracketed -----------
    lo, hi = _ZERO, ceiling
    last_cost, last_gdv, last_gap = cost_hi, gdv_hi, gap_hi
    while iters < MAX_ITERATIONS:
        mid = (lo + hi) / Decimal("2")
        gap_mid, cost_mid, gdv_mid = profit_gap(mid)
        iters += 1
        last_cost, last_gdv, last_gap = cost_mid, gdv_mid, gap_mid

        if abs(gap_mid) <= _GAP_TOL:
            achieved = _achieved_pct(cost_mid, gdv_mid, gap_mid, tgt, basis)
            return RlvResult(True, iters, _penny(mid), basis, target_pct, achieved)

        if gap_mid > _ZERO:
            lo = mid
        else:
            hi = mid

        if (hi - lo) <= _BRACKET_TOL:
            mid = (lo + hi) / Decimal("2")
            gap_f, cost_f, gdv_f = profit_gap(mid)
            iters += 1
            achieved = _achieved_pct(cost_f, gdv_f, gap_f, tgt, basis)
            return RlvResult(True, iters, _penny(mid), basis, target_pct, achieved)

    # --- Safety stop (unreachable given the bracket math) ---------------
    achieved = _achieved_pct(last_cost, last_gdv, last_gap, tgt, basis)
    return RlvResult(
        False, iters, _penny((lo + hi) / Decimal("2")), basis, target_pct, achieved,
        message=f"RLV did not converge in {MAX_ITERATIONS} iterations (unexpected).",
    )


def _penny(x: Decimal) -> Decimal:
    return x.quantize(_PENNY, rounding=ROUND_HALF_UP)


def _achieved_pct(cost: Decimal, gdv: Decimal, gap: Decimal,
                  tgt: Decimal, basis: str) -> Decimal:
    """Convert the gap + base figures back into an achieved %."""
    if basis == "on_cost":
        if cost <= _ZERO:
            return Decimal("0.0000")
        # achieved = (required + gap) / cost * 100 where required = cost * tgt
        profit = cost * tgt + gap
        return (profit / cost * Decimal("100")).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP,
        )
    if gdv <= _ZERO:
        return Decimal("0.0000")
    profit = gdv * tgt + gap
    return (profit / gdv * Decimal("100")).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_UP,
    )
