"""SDLT category classification for appraisals — Prompt 2.2.

Chooses the correct SDLT category from the appraisal header inputs.
Returns one of the four categories seeded in `sdlt_rate_bands`:
- Residential_Standard
- Residential_Surcharge
- Non_Residential
- Corporate_Flat_Rate
"""
from __future__ import annotations

from decimal import Decimal


CORPORATE_FLAT_THRESHOLD = Decimal("500000")


def classify(
    *,
    land_purchase_price: Decimal,
    sdlt_category: str,
    developer_relief: bool,
) -> str:
    """Resolve the effective SDLT category for the appraisal.

    Business rules:
    - If the user explicitly picked a category other than Residential_Standard
      or Residential_Surcharge, honour it (Non_Residential / Corporate_Flat_Rate).
    - If the user picked Residential_Surcharge and `developer_relief` is
      True, downgrade to Residential_Standard — SDLT developer relief.
    - If price exceeds the £500k corporate threshold AND developer_relief
      is False AND category is Residential_Surcharge, use Corporate_Flat_Rate.
    """
    price = Decimal(land_purchase_price)
    cat = sdlt_category or "Residential_Standard"

    if cat == "Residential_Surcharge":
        if developer_relief:
            return "Residential_Standard"
        if price > CORPORATE_FLAT_THRESHOLD:
            # Companies buying dwellings above £500k with no relief → flat 17%.
            return "Corporate_Flat_Rate"
        return "Residential_Surcharge"

    # Residential_Standard / Non_Residential / Corporate_Flat_Rate pass-through
    return cat
