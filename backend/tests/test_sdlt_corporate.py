"""C3 — Corporate_Flat_Rate SDLT undercharge fix regression tests.

Audit 2026-06-19, finding C3 (CONFIRMED, Critical).

The Corporate_Flat_Rate category is a single-band FLAT charge: above the
£500k threshold the 17% rate applies to the ENTIRE consideration, not just
the slice above the threshold. The old progressive loop charged only on the
slice above £500k — a material undercharge (e.g. £85,000 on a £600k purchase).

Money gate: these assertions run against the LIVE seeded Postgres database
via `app.db.SessionLocal`. All assertions compare Decimal values.
"""
from __future__ import annotations

from decimal import Decimal

import pytest


# =============================================================================
# Headline Corporate_Flat_Rate cases (the C3 fix)
# =============================================================================

class TestCorporateFlatRate:
    def test_600k_corporate_flat_is_102000(self):
        """£600k → 17% flat on the WHOLE amount = £102,000.00."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("600000"),
                          category="Corporate_Flat_Rate")
            assert v == Decimal("102000.00")
        finally:
            db.close()

    def test_500k_corporate_flat_is_zero(self):
        """At the threshold (£500k) the charge is £0 — flat rate only bites
        ABOVE the threshold."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("500000"),
                          category="Corporate_Flat_Rate")
            assert v == Decimal("0.00")
        finally:
            db.close()

    def test_500001_corporate_flat_is_85000_17(self):
        """£500,001 → 17% on the whole amount = £85,000.17 (ROUND_HALF_UP)."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("500001"),
                          category="Corporate_Flat_Rate")
            assert v == Decimal("85000.17")
        finally:
            db.close()

    def test_400k_corporate_flat_is_zero(self):
        """Below the threshold → £0."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("400000"),
                          category="Corporate_Flat_Rate")
            assert v == Decimal("0.00")
        finally:
            db.close()

    def test_flat_is_not_slice_regression(self):
        """The whole point of C3: the £600k result must be the FLAT figure
        (£102,000), NOT the old progressive 'slice above £500k' figure
        (£17,000)."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("600000"),
                          category="Corporate_Flat_Rate")
            assert v == Decimal("102000.00")
            assert v != Decimal("17000.00")  # the buggy slice figure
        finally:
            db.close()

    def test_negative_consideration_raises(self):
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            with pytest.raises(ValueError):
                calculate(db, consideration=Decimal("-1"),
                          category="Corporate_Flat_Rate")
        finally:
            db.close()


# =============================================================================
# Regression: every OTHER category must compute exactly as before the fix
# =============================================================================

class TestOtherCategoriesUnchanged:
    def test_residential_standard_500k_unchanged(self):
        """0..125k→0, 125..250k→2% (£2,500), 250..500k→5% (£12,500) = £15,000."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("500000"),
                          category="Residential_Standard")
            assert v == Decimal("15000.00")
        finally:
            db.close()

    def test_residential_surcharge_500k_unchanged(self):
        """Surcharge progressive: 5% on 125k (£6,250) + 7% on 125k (£8,750)
        + 10% on 250k (£25,000) = £40,000."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("500000"),
                          category="Residential_Surcharge")
            assert v == Decimal("40000.00")
        finally:
            db.close()

    def test_non_residential_250k_unchanged(self):
        """0..150k→0, 150..250k→2% on 100k = £2,000."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("250000"),
                          category="Non_Residential")
            assert v == Decimal("2000.00")
        finally:
            db.close()

    def test_non_residential_600k_unchanged(self):
        """Cross-check a £600k Non_Residential stays progressive (NOT flat):
        0..150k→0, 150..250k→2% (£2,000), 250k+→5% on 350k (£17,500) = £19,500."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("600000"),
                          category="Non_Residential")
            assert v == Decimal("19500.00")
        finally:
            db.close()

    def test_residential_standard_600k_still_progressive(self):
        """£600k Residential_Standard: 125..250k→2% (£2,500),
        250..600k→5% on 350k (£17,500) = £20,000 — proves the fix did not
        leak into the progressive path."""
        from app.db import SessionLocal
        from app.services.sdlt import calculate
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("600000"),
                          category="Residential_Standard")
            assert v == Decimal("20000.00")
        finally:
            db.close()


# =============================================================================
# Classification still routes correctly into Corporate_Flat_Rate
# =============================================================================

class TestClassificationRouting:
    def test_company_dwelling_above_threshold_routes_corporate(self):
        from app.services.appraisal_classification import classify
        assert classify(
            land_purchase_price=Decimal("600000"),
            sdlt_category="Residential_Surcharge",
            developer_relief=False,
        ) == "Corporate_Flat_Rate"

    def test_at_threshold_stays_surcharge(self):
        """price > £500k is the gate — exactly £500k stays Surcharge."""
        from app.services.appraisal_classification import classify
        assert classify(
            land_purchase_price=Decimal("500000"),
            sdlt_category="Residential_Surcharge",
            developer_relief=False,
        ) == "Residential_Surcharge"

    def test_developer_relief_downgrades_to_standard(self):
        from app.services.appraisal_classification import classify
        assert classify(
            land_purchase_price=Decimal("600000"),
            sdlt_category="Residential_Surcharge",
            developer_relief=True,
        ) == "Residential_Standard"

    def test_explicit_non_residential_passthrough(self):
        from app.services.appraisal_classification import classify
        assert classify(
            land_purchase_price=Decimal("600000"),
            sdlt_category="Non_Residential",
            developer_relief=False,
        ) == "Non_Residential"

    def test_end_to_end_classify_then_calculate_600k(self):
        """The full blast-radius path: a £600k company dwelling purchase with
        no relief classifies to Corporate_Flat_Rate and is charged £102,000."""
        from app.db import SessionLocal
        from app.services.appraisal_classification import classify
        from app.services.sdlt import calculate
        category = classify(
            land_purchase_price=Decimal("600000"),
            sdlt_category="Residential_Surcharge",
            developer_relief=False,
        )
        assert category == "Corporate_Flat_Rate"
        db = SessionLocal()
        try:
            v = calculate(db, consideration=Decimal("600000"), category=category)
            assert v == Decimal("102000.00")
        finally:
            db.close()
