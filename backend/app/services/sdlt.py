"""SDLT calculator — Prompt 2.1.

Progressive-band stamp-duty calculation. Selects the active band set for
a given (category, reference_date) and runs progressive calc over the
consideration amount.

Consumer (Prompt 2.2) will call `calculate(...)` with the appraisal's
`created_at.date()` as the reference date so the "no retroactive mutation"
guarantee is satisfied at read time.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.reference_data import SdltRateBand


_PENNY = Decimal("0.01")


def _round_penny(x: Decimal) -> Decimal:
    return x.quantize(_PENNY, rounding=ROUND_HALF_UP)


def get_active_bands(
    db: Session, *, category: str, reference_date: Optional[date] = None,
) -> list[SdltRateBand]:
    """Return bands for `category` active on `reference_date`
    (defaults to today), ordered by band_lower ascending."""
    if reference_date is None:
        reference_date = date.today()

    q = select(SdltRateBand).where(
        SdltRateBand.category == category,
        SdltRateBand.effective_from <= reference_date,
        or_(
            SdltRateBand.effective_to.is_(None),
            SdltRateBand.effective_to >= reference_date,
        ),
    ).order_by(SdltRateBand.band_lower.asc())
    return list(db.scalars(q).all())


def calculate(
    db: Session,
    *,
    consideration: Decimal,
    category: str,
    reference_date: Optional[date] = None,
) -> Decimal:
    """Return the progressive SDLT on `consideration` using the bands for
    (`category`, `reference_date`). Result rounded to whole pennies.

    Progressive: each band charges `rate_pct` on the portion of
    consideration that falls within (band_lower, band_upper].

    Corporate_Flat_Rate is NOT progressive. It is a single-band FLAT charge:
    when the consideration exceeds the band threshold (£500k in the seed),
    the flat rate (17%) applies to the ENTIRE consideration — not just the
    slice above the threshold. At or below the threshold the charge is £0.
    This category is handled by a dedicated branch below, before the
    progressive loop, so every other category is computed exactly as before.
    """
    if consideration < 0:
        raise ValueError("consideration must be >= 0")
    bands = get_active_bands(db, category=category, reference_date=reference_date)
    if not bands:
        raise LookupError(
            f"No active SDLT bands for category={category!r} on {reference_date}"
        )

    amount = Decimal(consideration)

    # Corporate_Flat_Rate is a single-band FLAT charge — NOT progressive.
    # Companies buying dwellings above the threshold pay the flat rate on the
    # ENTIRE consideration, not just the slice above the threshold. Intercept
    # it here, before the progressive loop, so no other category is affected.
    if category == "Corporate_Flat_Rate":
        band = bands[0]
        threshold = Decimal(band.band_lower)
        if amount <= threshold:
            return Decimal("0.00")
        return _round_penny(amount * (Decimal(band.rate_pct) / Decimal("100")))

    total = Decimal("0")

    for b in bands:
        lo = Decimal(b.band_lower)
        hi = Decimal(b.band_upper) if b.band_upper is not None else amount
        if amount <= lo:
            break
        taxable = min(amount, hi) - lo
        if taxable <= 0:
            continue
        total += taxable * (Decimal(b.rate_pct) / Decimal("100"))
    return _round_penny(total)
