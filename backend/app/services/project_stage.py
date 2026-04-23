"""Project stage machine — Prompt 1.5 Section D.

DELIBERATE SPEC DEVIATION: the prompt spec says "non-sequential stage
changes allowed but flagged in audit metadata." Rhys chose a constrained
hard-coded forward-only model with an explicit super_admin override,
because property development is genuinely linear and stray stage clicks
make forensic work painful.

Revisit in the Polish Pass (post-1.7): consider moving FORWARD_TRANSITIONS
into system_config so stages can be edited without a deploy.
"""
from __future__ import annotations

from typing import Optional


# Forward-only graph. 'Dead' is an allowed target from any active stage.
FORWARD_TRANSITIONS: dict[str, list[str]] = {
    "Lead":            ["Appraisal", "Dead"],
    "Appraisal":       ["Deal_Pipeline", "Dead"],
    "Deal_Pipeline":   ["Planning", "Dead"],
    "Planning":        ["Pre_Con", "Dead"],
    "Pre_Con":         ["Construction", "Dead"],
    "Construction":    ["Sales", "Post_Completion", "Dead"],
    "Sales":           ["Post_Completion", "Dead"],
    "Post_Completion": ["Closed", "Dead"],
    "Closed":          [],
    "Dead":            [],
}


def is_allowed_forward(current: str, new: str) -> bool:
    return new in FORWARD_TRANSITIONS.get(current, [])


def derived_status(new_stage: str, current_status: str) -> str:
    """Apply the status-sync rules from spec D4."""
    if new_stage == "Dead":
        return "Dead"
    if new_stage == "Closed":
        return "Complete"
    # Leaving Dead/Closed (override path) → reset to Active.
    if current_status in ("Dead", "Complete"):
        return "Active"
    return current_status
