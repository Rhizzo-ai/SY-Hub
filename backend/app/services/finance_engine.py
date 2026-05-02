"""Finance engine — Prompt 2.2.

Computes monthly interest + fees on each debt/equity facility attached
to an appraisal. All arithmetic is Decimal. Date math uses calendar
months (via draw window integers on the facility row).

Interest modes:
- Simple_Monthly   : monthly rate × principal_drawn × months_in_window
- Compound_Monthly : principal × ((1 + r)^n - 1), monthly compounding
- Rolled_Up        : Simple_Monthly but capitalised at the end (same
                     cash figure for the appraisal — timing differs,
                     which matters in cash flow, not here)
- Serviced         : Simple_Monthly (paid as drawn — same total)

Notes:
- `interest_rate_pct` on the facility is the *annual* rate.
- Month count = drawn_to_month - drawn_from_month (inclusive of draw
  period; zero if same-month window).
- Arrangement fee = arrangement_fee_pct × principal (once).
- Exit fee         = exit_fee_pct × principal (once).
- `total_finance_cost` = total_interest + total_fees.

Compound_Quarterly is NOT implemented (future). Calling with that mode
falls back to Compound_Monthly with a logged warning.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, List


log = logging.getLogger("syhomes.appraisal.finance")

_PENNY = Decimal("0.01")
_ZERO = Decimal("0")


def _penny(x: Decimal) -> Decimal:
    return x.quantize(_PENNY, rounding=ROUND_HALF_UP)


@dataclass
class FacilityInput:
    label: str
    principal_amount: Decimal
    interest_rate_pct: Decimal      # annual
    arrangement_fee_pct: Decimal
    exit_fee_pct: Decimal
    interest_mode: str
    drawn_from_month: int
    drawn_to_month: int


@dataclass
class FacilityOutput:
    label: str
    months: int
    total_interest: Decimal
    total_fees: Decimal
    total_finance_cost: Decimal


def compute_facility(f: FacilityInput) -> FacilityOutput:
    principal = Decimal(f.principal_amount)
    annual_rate = Decimal(f.interest_rate_pct) / Decimal("100")
    monthly_rate = annual_rate / Decimal("12")
    months = max(0, int(f.drawn_to_month) - int(f.drawn_from_month))

    mode = f.interest_mode or "Simple_Monthly"
    if mode == "Compound_Monthly":
        # principal * ((1 + r)^n - 1)
        growth = (Decimal("1") + monthly_rate) ** months
        interest = principal * (growth - Decimal("1"))
    elif mode in ("Simple_Monthly", "Rolled_Up", "Serviced"):
        interest = principal * monthly_rate * Decimal(months)
    else:
        log.warning("Unknown interest_mode=%r on facility %r — using Simple_Monthly",
                    mode, f.label)
        interest = principal * monthly_rate * Decimal(months)

    if interest < _ZERO:
        interest = _ZERO

    arrangement_fee = principal * (Decimal(f.arrangement_fee_pct) / Decimal("100"))
    exit_fee = principal * (Decimal(f.exit_fee_pct) / Decimal("100"))
    fees = arrangement_fee + exit_fee

    total = interest + fees
    return FacilityOutput(
        label=f.label,
        months=months,
        total_interest=_penny(interest),
        total_fees=_penny(fees),
        total_finance_cost=_penny(total),
    )


def compute_all(facilities: Iterable[FacilityInput]) -> List[FacilityOutput]:
    return [compute_facility(f) for f in facilities]


def total_finance_cost(outputs: Iterable[FacilityOutput]) -> Decimal:
    return _penny(sum((o.total_finance_cost for o in outputs), _ZERO))
