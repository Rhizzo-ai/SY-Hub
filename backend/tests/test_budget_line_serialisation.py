"""Build Pack 2.6-FIX (Chat 39) §R5 — B-CONTINGENCY / B-DATA serialisation tests.

Pins ``_serialise_line`` to expose ``is_contingency`` (so the
ContingencyDrawdown source-line validator in the dialog sees a real
boolean) and ``cost_code_id`` (so the BCR detail can resolve the code
client-side via ``useCostCodes``).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from app.routers.budgets import _serialise_line


class _StubLine:
    """Minimal duck-type stand-in for BudgetLine — only the columns
    ``_serialise_line`` reads. Keeps the test off the DB."""

    def __init__(self, **overrides):
        defaults = dict(
            id=uuid.uuid4(),
            budget_id=uuid.uuid4(),
            cost_code_id=uuid.uuid4(),
            cost_code_subcategory_id=None,
            entity_id=uuid.uuid4(),
            line_description="Test line",
            original_budget=Decimal("100.00"),
            approved_changes=Decimal("0"),
            current_budget=Decimal("100.00"),
            ftc_method="Manual",
            forecast_to_complete=Decimal("100.00"),
            percentage_complete=None,
            linked_programme_task_id=None,
            is_locked=False,
            requires_attention=False,
            display_order=1,
            notes=None,
            variance_status="Green",
            is_contingency=False,
            created_at=None,
            updated_at=None,
            actuals_to_date=Decimal("0"),
            committed_value=Decimal("0"),
            invoiced_against_commitment=Decimal("0"),
            committed_not_invoiced=Decimal("0"),
            forecast_final_cost=Decimal("100.00"),
            variance_value=Decimal("0"),
            variance_pct=Decimal("0"),
            actuals_this_period=Decimal("0"),
            items=[],
        )
        defaults.update(overrides)
        for k, v in defaults.items():
            setattr(self, k, v)


# ---------------------------------------------------------------------------
# Test #11 — is_contingency present (B-CONTINGENCY)
# ---------------------------------------------------------------------------

def test_serialise_line_includes_is_contingency():
    """B-CONTINGENCY #11 — ``is_contingency`` must be a real boolean
    in the serialised payload for both contingency and non-contingency
    lines (was previously `undefined` → frontend `!undefined === true`
    blocked every contingency drawdown).
    """
    non_cont = _StubLine(is_contingency=False)
    cont = _StubLine(is_contingency=True)

    d_non = _serialise_line(non_cont, include_sensitive=False)
    d_yes = _serialise_line(cont, include_sensitive=False)

    assert "is_contingency" in d_non
    assert "is_contingency" in d_yes
    assert d_non["is_contingency"] is False
    assert d_yes["is_contingency"] is True
    # Typed: not a string, not None, not a number.
    assert isinstance(d_non["is_contingency"], bool)
    assert isinstance(d_yes["is_contingency"], bool)


# ---------------------------------------------------------------------------
# Test #12 — cost_code_id present (B-DATA regression pin)
# ---------------------------------------------------------------------------

def test_serialise_line_cost_code_id_present():
    """B-DATA #12 — ``cost_code_id`` must be serialised so the BCR
    detail page can resolve the code via ``useCostCodes`` (mirrors the
    grid's BudgetGridColumns.jsx:99 lookup).

    This is a regression pin: deleting the cost_code_id from
    ``_serialise_line`` would re-break the BCR detail flash from
    Chat 39.
    """
    line = _StubLine()
    d = _serialise_line(line, include_sensitive=False)
    assert "cost_code_id" in d
    assert d["cost_code_id"] == str(line.cost_code_id)
    # And on the sensitive variant too.
    d_sens = _serialise_line(line, include_sensitive=True)
    assert d_sens["cost_code_id"] == str(line.cost_code_id)
