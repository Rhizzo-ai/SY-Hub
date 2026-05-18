"""Chat 23 Build Pack A — R1.1 fence-post tests for the new variance bands.

Design Q2 / R1.1 flipped the bands from 5/15 to 0/10:
  - variance_pct <= 0     -> Green
  - 0 < variance_pct < 10 -> Amber
  - variance_pct >= 10    -> Red

These tests pin the fence-posts so any future drift surfaces immediately.
Pure unit tests against _classify_variance — no DB session required.
"""
from __future__ import annotations

from decimal import Decimal

from app.services.budgets import _classify_variance


class TestVarianceBandFencePosts:
    def test_negative_under_budget_is_green(self):
        # Under budget always stays Green.
        assert _classify_variance(Decimal("-5")) == "Green"

    def test_exactly_zero_is_green(self):
        # The "on budget" fence-post — strict `>` for Amber lower bound
        # keeps zero in Green.
        assert _classify_variance(Decimal("0")) == "Green"

    def test_just_above_zero_is_amber(self):
        # First positive infinitesimal — any over-budget at all is Amber.
        assert _classify_variance(Decimal("0.001")) == "Amber"

    def test_just_below_ten_is_amber(self):
        # Last sub-10% value still in Amber.
        assert _classify_variance(Decimal("9.999")) == "Amber"

    def test_exactly_ten_is_red(self):
        # The Red fence-post — `>=` for Red upper bound puts exactly 10 in
        # Red, not Amber.
        assert _classify_variance(Decimal("10.000")) == "Red"

    def test_well_above_ten_is_red(self):
        assert _classify_variance(Decimal("25.000")) == "Red"
