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
