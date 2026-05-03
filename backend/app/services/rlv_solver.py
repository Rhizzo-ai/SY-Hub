"""RLV (Residual Land Value) solver — Prompt 2.2.

Iterative Decimal-only solver. Given a target margin (on-cost or on-gdv),
finds the land purchase price that would produce that margin, holding
the rest of the appraisal constant.

Fails gracefully: returns converged=False after 50 iterations.

Does NOT mutate the appraisal's land_purchase_price — caller decides
whether to write `rlv_computed_land_value` back to the header.
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
MAX_ITERATIONS = 50
# Converge when projected profit is within £1 of target.
TOLERANCE = Decimal("1.00")


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

    Strategy: secant-like iteration. Start with two guesses and walk
    toward the root of `f(L) = profit_at(L) - target_profit(L)`.
    """
    if basis not in ("on_cost", "on_gdv"):
        raise ValueError(f"Unknown RLV basis: {basis!r}")

    target_pct = Decimal(target_pct)
    tgt = target_pct / Decimal("100")

    def profit_gap(land: Decimal) -> tuple[Decimal, Decimal, Decimal]:
        """Return (gap, total_cost, total_gdv) at `land`.

        gap = total_profit(L) - required_profit_for_target(L)
        where required_profit depends on basis."""
        res = recompute(db, appraisal, override_land_price=land)
        if basis == "on_cost":
            required = res.total_cost * tgt
        else:
            required = res.total_gdv * tgt
        return (res.total_profit - required, res.total_cost, res.total_gdv)

    # Seed guesses. Use current land and 80% of current land.
    current = Decimal(appraisal.land_purchase_price or 0)
    if current <= _ZERO:
        # Use 10% of total_gdv as a starter — anchored to output.
        seed_gdv = Decimal(appraisal.gdv_total or 0)
        current = seed_gdv * Decimal("0.10") if seed_gdv > _ZERO else Decimal("100000")

    L0 = current
    L1 = current * Decimal("0.80") if current > _ZERO else Decimal("80000")
    if L1 == L0:
        L1 = L0 + Decimal("1000")

    gap0, _, _ = profit_gap(L0)
    if abs(gap0) <= TOLERANCE:
        # Already on target — record result at current land.
        _, cost_now, gdv_now = profit_gap(L0)
        achieved = _achieved_pct(cost_now, gdv_now, gap0, tgt, basis)
        return RlvResult(True, 1, _penny(L0), basis, target_pct, achieved)

    gap1, _, _ = profit_gap(L1)

    iters = 2
    last_gap = gap1
    last_cost = _ZERO
    last_gdv = _ZERO

    while iters < MAX_ITERATIONS:
        denom = gap1 - gap0
        if denom == _ZERO:
            # Nudge.
            L2 = L1 * Decimal("1.05") + Decimal("1")
        else:
            # Secant: L2 = L1 - gap1 * (L1 - L0) / (gap1 - gap0)
            L2 = L1 - gap1 * (L1 - L0) / denom

        if L2 < _ZERO:
            # Land value can't be negative — clamp and record non-convergence.
            log.info("RLV solver: negative land_value projected (%s); clamping", L2)
            L2 = _ZERO
            gap2, last_cost, last_gdv = profit_gap(L2)
            achieved = _achieved_pct(last_cost, last_gdv, gap2, tgt, basis)
            return RlvResult(
                False, iters, _penny(L2), basis, target_pct, achieved,
                message="Target margin unreachable: required land value negative.",
            )

        gap2, last_cost, last_gdv = profit_gap(L2)
        last_gap = gap2
        if abs(gap2) <= TOLERANCE:
            achieved = _achieved_pct(last_cost, last_gdv, gap2, tgt, basis)
            return RlvResult(True, iters + 1, _penny(L2), basis, target_pct, achieved)

        L0, gap0 = L1, gap1
        L1, gap1 = L2, gap2
        iters += 1

    # Non-convergence.
    achieved = _achieved_pct(last_cost, last_gdv, last_gap, tgt, basis)
    return RlvResult(
        False, iters, _penny(L1), basis, target_pct, achieved,
        message=f"RLV did not converge in {MAX_ITERATIONS} iterations.",
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
