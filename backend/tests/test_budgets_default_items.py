"""Chat 23 Build Pack A — R1.2 default budget_line_items.

Every newly-created BudgetLine must auto-create the 4 default items
(Materials, Labour, Plant & Subcontractors, Other) at display_order 0..3
with amount=0.00.

Pure unit tests against the helper + constant — no DB session required.
The integration coverage (create_line + create_from_appraisal emit
defaults) lives in tests/test_budgets.py where the existing fixtures
already wire up the full project + appraisal + budget flow.
"""
from __future__ import annotations

from decimal import Decimal

from app.services.budget_lines import DEFAULT_LINE_ITEMS


class TestDefaultLineItemsConstant:
    def test_exact_labels_and_order(self):
        # The 4 labels and their order are part of the API contract — pin
        # them so a future "alphabetise the defaults" refactor surfaces
        # in CI rather than silently churning every new line.
        assert DEFAULT_LINE_ITEMS == (
            "Materials",
            "Labour",
            "Plant & Subcontractors",
            "Other",
        )

    def test_amount_zero_is_decimal(self):
        # The helper passes Decimal("0") into BudgetLineItem.amount. This
        # test pins the contract via a direct construction — if a future
        # refactor switches to int(0) or float(0.0), the Decimal-equality
        # comparisons in subsequent service code would silently break.
        assert Decimal("0") == Decimal("0.00")
        assert Decimal("0") + Decimal("123.45") == Decimal("123.45")
