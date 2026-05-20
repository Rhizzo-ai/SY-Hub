"""Chat 24 §R4 (Prompt 2.5) — PO Receipts unit tests.

Pure service-layer logic (no HTTP). Validates:
  - _normalise_qty rejects zero/negative/garbage and quantises to 4dp
  - _check_cumulative_within_ordered surfaces remaining capacity
  - _validate_received_date: future rejected, backdated >30d needs pos.edit_issued
  - ELIGIBLE_RECEIPT_STATUSES is exactly {issued, partially_receipted}
  - Audit action 'Receipt' is in AUDIT_ACTIONS tuple
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.models.audit import AUDIT_ACTIONS
from app.services import po_receipts as svc
from app.services.po_receipts import ReceiptError


class _Perms:
    def __init__(self, codes: set[str]) -> None:
        self._codes = codes

    def has(self, code: str) -> bool:
        return code in self._codes


class TestNormaliseQty:
    def test_quantises_to_4dp(self):
        assert svc._normalise_qty("3.123456") == Decimal("3.1235")

    def test_zero_rejected(self):
        with pytest.raises(ReceiptError) as ei:
            svc._normalise_qty(0)
        assert ei.value.code == "po/receipt-bad-quantity"

    def test_negative_rejected(self):
        with pytest.raises(ReceiptError):
            svc._normalise_qty(-1)

    def test_garbage_rejected(self):
        with pytest.raises(ReceiptError):
            svc._normalise_qty("not-a-number")


class _FakeLine:
    def __init__(self, quantity, receipted, line_number=1):
        self.quantity = Decimal(str(quantity))
        self.receipted_quantity = Decimal(str(receipted))
        self.line_number = line_number


class TestCumulativeGuard:
    def test_within_remaining_passes(self):
        line = _FakeLine(10, 4)
        svc._check_cumulative_within_ordered(line, Decimal("6"))  # exactly remaining

    def test_exceeds_remaining_raises(self):
        line = _FakeLine(10, 4)
        with pytest.raises(ReceiptError) as ei:
            svc._check_cumulative_within_ordered(line, Decimal("7"))
        assert ei.value.code == "po/receipt-exceeds-ordered"


class TestReceivedDateValidation:
    def test_future_rejected(self):
        future = (datetime.now(timezone.utc).date() + timedelta(days=1))
        with pytest.raises(ReceiptError) as ei:
            svc._validate_received_date(future, perms=_Perms({"pos.edit_issued"}))
        assert ei.value.code == "po/receipt-future-date"

    def test_today_accepted(self):
        today = datetime.now(timezone.utc).date()
        svc._validate_received_date(today, perms=_Perms(set()))

    def test_recent_backdate_accepted_without_edit_issued(self):
        d = datetime.now(timezone.utc).date() - timedelta(days=20)
        svc._validate_received_date(d, perms=_Perms(set()))

    def test_31_days_back_requires_edit_issued(self):
        d = datetime.now(timezone.utc).date() - timedelta(days=31)
        with pytest.raises(ReceiptError) as ei:
            svc._validate_received_date(d, perms=_Perms({"pos.view"}))
        assert ei.value.code == "po/receipt-backdate-forbidden"

    def test_31_days_back_allowed_with_edit_issued(self):
        d = datetime.now(timezone.utc).date() - timedelta(days=31)
        svc._validate_received_date(d, perms=_Perms({"pos.edit_issued"}))


class TestConstants:
    def test_eligible_statuses_are_exact(self):
        assert svc.ELIGIBLE_RECEIPT_STATUSES == frozenset({
            "issued", "partially_receipted",
        })

    def test_backdate_grace_is_30(self):
        assert svc.BACKDATE_GRACE_DAYS == 30

    def test_receipt_audit_action_registered(self):
        assert "Receipt" in AUDIT_ACTIONS
