"""Shared exceptions for the Budgets service layer.

Per alpha-9 lock (Chat 16 / Prompt 2.4A): split BudgetNotFoundError(404) from
BudgetStateError(409) up-front so route mapping is unambiguous.

BudgetCreationError covers source-data violations (B5) — also 4xx, surfaces as
400 from /from-appraisal.
"""
from __future__ import annotations


class BudgetError(Exception):
    """Base for all budget service exceptions."""


class BudgetNotFoundError(BudgetError):
    """Budget/line/item not visible to the caller (or doesn't exist).

    Always 404 at the route layer. Per the cross-tenant 404 contract, callers
    must never receive a 403 that would leak existence of the resource.
    """


class BudgetStateError(BudgetError):
    """State-machine or invariant violation (e.g. activate from Locked,
    edit a line on a Closed budget, lock when locked).

    Always 409 at the route layer.
    """


class BudgetSealedError(BudgetStateError):
    """Acknowledgement (clear_unbudgeted) attempted on a terminally-sealed
    budget (Superseded / Closed).

    B-variant (C2, Chat 63): Locked is a soft freeze and clear_unbudgeted is
    still permitted there; Superseded/Closed are terminal and sealed — late
    unbudgeted spend must go onto a NEW budget version, never a quiet edit to
    sealed history.

    Subclasses BudgetStateError so any existing broad
    `except BudgetStateError` still catches it, but the clear-unbudgeted route
    maps it specifically to 409 (sealed-state violation) rather than 422
    (not-an-unbudgeted-line). Always 409 at the route layer.
    """


class BudgetCreationError(BudgetError):
    """Bad source data when creating a budget from an appraisal (B5 guards).

    400 at the route layer.
    """


class BudgetValidationError(BudgetError):
    """Caller-side payload validation failure (e.g. reorder list missing
    or duplicate ids). Distinct from BudgetCreationError so the audit
    trail stays clean: 'B5 source data' vs 'caller validation'.

    400 at the route layer.
    """


class BudgetSelfApprovalError(BudgetError):
    """Segregation-of-duties refusal (Build Pack 2.4C R2.3).

    Raised when a budget's `created_by_user_id` equals the activator's
    user id AND the budget total is at or above the configurable
    `budget.self_approval_threshold_gbp`. This is an *authorisation*
    refusal — the caller may have `budgets.edit` but the business rule
    forbids self-approval at/above the threshold. Therefore this maps
    to HTTP 403 at the router (NOT 409 — that's reserved for
    state-machine violations via BudgetStateError).

    Always 403 at the route layer.
    """


class UnbudgetedAckRequiredError(BudgetError):
    """B105/B106 Gate A — director sign-off required on at least one
    un-cleared unbudgeted line.

    Raised inside `submit_po_with_budget_gate` / `issue_po` immediately
    after `recompute_for_po`, when one or more unbudgeted lines have
    committed_not_invoiced >= the configured floor
    (`budget.unbudgeted_ack_floor_gbp`). The PO MUST stay Draft (or
    fail to issue) until a director clears the line(s) via the
    existing `POST /budget-lines/{line_id}/clear-unbudgeted` action
    (permission `budgets.clear_unbudgeted`).

    Carries the blocking-line summary the router renders as the 409
    response body. Always 409 at the route layer.
    """

    def __init__(self, blocking: list[dict]):
        self.blocking = list(blocking or [])
        super().__init__(
            f"Director sign-off required on {len(self.blocking)} "
            f"unbudgeted line(s)"
        )


class POLineIncompleteError(BudgetError):
    """B105/B106 §3.8 — PO submit refused because one or more lines
    are incomplete.

    A PO line is complete when it has a resolved `budget_line_id`,
    `cost_code` (non-empty), `quantity > 0`, `unit_rate >= 0`,
    `vat_rate` present (0..100), and a non-empty `description`.
    Drafts may persist incomplete (so AI/manual fill can fill them
    progressively); submit applies this gate before any transition or
    money path runs. Always 422 at the route layer.
    """

    def __init__(self, line_numbers: list[int]):
        self.line_numbers = sorted(int(n) for n in (line_numbers or []))
        super().__init__(
            f"PO submit refused: incomplete line(s) "
            f"{self.line_numbers}"
        )


class BudgetLineRaceError(BudgetError):
    """B105/B106 §3.9 — concurrency race on resolve-or-mint.

    Raised when two requests resolve-then-mint the same
    (budget_id, cost_code_id, cost_code_subcategory_id) triple
    concurrently. The first writer wins; the second hits
    `uq_budget_lines_budget_cost_subcat` on flush, raising
    SQLAlchemy's `IntegrityError`. `create_po` / `add_package_line`
    translate that into this error so the router emits a clean 409
    instead of a raw 500. The client may retry — on retry, the
    resolve pass finds the winning row and allocates into it.

    Always 409 at the route layer.
    """

    def __init__(self, cost_code_id, cost_code_subcategory_id=None):
        self.cost_code_id = str(cost_code_id) if cost_code_id else None
        self.cost_code_subcategory_id = (
            str(cost_code_subcategory_id)
            if cost_code_subcategory_id else None
        )
        super().__init__(
            f"A budget line for cost_code_id={self.cost_code_id} "
            f"was just created concurrently; retry the request."
        )
