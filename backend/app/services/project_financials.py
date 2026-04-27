"""Cached financials refresh — STUB (Prompt 1.5 Section H).

Returns zeros and stamps `financials_refreshed_at=now()`. The real rollup
logic lands as its data sources arrive:
  - Build cost actuals: Prompt 2.5 (actuals / commitments)
  - Cash flow + margin: Prompt 2.7
  - GDV + units: Phase 5 (sales / plots)

Until then, this stub exists so the /financials/refresh endpoint is
callable (keeps the frontend stale-indicator + refresh button wired) and
so callers don't NPE on a missing field set.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app.models.projects import Project


ZERO = Decimal("0")


def refresh_financials(db: Session, project: Project) -> dict:
    project.gdv_actual = ZERO
    project.build_cost_actual = ZERO
    project.all_in_cost_actual = ZERO
    project.profit_actual = ZERO
    project.margin_actual_pct = ZERO
    project.financials_refreshed_at = datetime.now(timezone.utc)
    return {
        "gdv_actual": 0,
        "build_cost_actual": 0,
        "all_in_cost_actual": 0,
        "profit_actual": 0,
        "margin_actual_pct": 0,
        "financials_refreshed_at": project.financials_refreshed_at.isoformat(),
    }
