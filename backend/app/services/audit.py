"""Audit logging service — Prompt 1.4.

The forensic spine of SY Homes Operations. Every significant application-
level write records an `audit_log` row via `record_audit(...)`. Read paths
(GET) are not audited; only writes that change state or grant access.

RETENTION (informational; actual purge is in audit_retention.py):
- Financial / contractual writes (actuals, budget_changes, invoices,
  contracts, valuations): INDEFINITE.
- Authentication events (Login, Logout, Permission_Change): 2+ years
  minimum.
- All other writes: 7+ years minimum (UK statute of limitations baseline).

APPEND-ONLY:
The DB enforces append-only via `audit_log_no_modify()` trigger. The
application MUST NOT attempt UPDATE/DELETE against `audit_log`. The
scheduled purge job (retention module) is the only path that bypasses
the trigger, and it does so by setting `session_replication_role='replica'`
within its transaction — scoped to one connection.

APPROVALS (Track 2+ discipline):
When recording action=Approve / action=Reject, callers MUST pass the
original record's submitted_by_user_id through `stamp_self_approval()`
before building the metadata dict, so self-approval is surfaced as
`metadata.self_approval = True` when the acting user is the same as the
record author.

IMPERSONATION:
When the current session row carries `impersonator_user_id`, every audit
write within that session MUST include it on the resulting row:
- actor_user_id = the impersonated user (what they "did")
- impersonator_user_id = the super_admin behind the wheel
The auth dependency reads the session and stashes the value on
`request.state.impersonator_user_id`; `record_audit` honours that.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import Request
from sqlalchemy.orm import Session

from app.models.audit import AuditLog, AUDIT_ACTIONS


log = logging.getLogger("syhomes.audit")


# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

SENSITIVE_FIELDS: frozenset[str] = frozenset({
    "password_hash",
    "password_history",
    "password_reset_token_hash",
    "mfa_secret_encrypted",
    "mfa_backup_codes_encrypted",
    "access_token_hash",
    "access_token_jti",
    "refresh_token_hash",
    "previous_refresh_token_hash",
    "invitation_token_hash",
    "key_hash",
    "access_token_encrypted",
    "refresh_token_encrypted",
    # Banking PII (Patch #2, 2026-04-23). bank_account_number_masked is
    # already truncated to ****1234 at write time, but redacting here too
    # keeps the rule simple and prevents partial-leak via diff timing.
    "bank_name",
    "bank_account_name",
    "bank_account_number_masked",
    # UK tax identifier — sensitive PII for sole traders / partnerships.
    # Surfaced as a residual during Patch #2 schema sweep.
    "utr",
    # Chat 24 §R1 (Prompt 2.5) — supplier banking PII. Audit-trail diffs
    # for these fields are redacted to [REDACTED] regardless of who reads
    # the audit_log. `vat_number` / `company_number` are gated at the
    # serialisation layer (suppliers.view_sensitive) but are NOT redacted
    # in audit diffs — they're business identifiers, not PII.
    "bank_account_no",
    "bank_sort_code",
})

REDACTED = "[REDACTED]"


# --------------------------------------------------------------------------
# Utilities
# --------------------------------------------------------------------------

def _json_safe(value: Any) -> Any:
    """Best-effort conversion so the JSONB column accepts whatever callers
    pass. UUIDs → str, datetimes → iso, Decimals via str fallback, sets →
    sorted lists. Anything truly opaque becomes its repr().
    """
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        return sorted(_json_safe(v) for v in value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    try:
        # Decimals, most custom scalar types
        return str(value)
    except Exception:  # pragma: no cover
        return repr(value)


def field_diff(before: dict, after: dict) -> list[dict]:
    """Produce an ordered [{field, old, new}] list of changed fields only.

    Keys present only in `after` are treated as new (old=None). Keys present
    only in `before` are treated as removed (new=None). Unchanged values are
    elided. The output list is sorted by field name for deterministic tests.
    """
    keys = sorted(set(before or {}) | set(after or {}))
    out: list[dict] = []
    for k in keys:
        old_v = (before or {}).get(k)
        new_v = (after or {}).get(k)
        if old_v == new_v:
            continue
        out.append({
            "field": k,
            "old": _json_safe(old_v),
            "new": _json_safe(new_v),
        })
    return out


def _redact(changes: list[dict]) -> list[dict]:
    """Return a copy of `changes` with sensitive fields' old/new set to [REDACTED]."""
    out = []
    for c in changes or []:
        if c.get("field") in SENSITIVE_FIELDS:
            out.append({"field": c["field"], "old": REDACTED, "new": REDACTED})
        else:
            out.append(c)
    return out


def stamp_self_approval(
    metadata: dict,
    actor_user_id: uuid.UUID,
    submitted_by_user_id: Optional[uuid.UUID],
) -> dict:
    """Helper for Track 2+ approval flows (budgets, appraisals, etc.).

    Adds `metadata["self_approval"] = True` iff the actor is the same user
    that originally submitted the record. Pass-through otherwise.
    Never mutates the input dict.
    """
    if submitted_by_user_id is None:
        return dict(metadata or {})
    out = dict(metadata or {})
    if actor_user_id == submitted_by_user_id:
        out["self_approval"] = True
    return out


# --------------------------------------------------------------------------
# Request extraction helpers
# --------------------------------------------------------------------------

def _client_ip(req: Request) -> Optional[str]:
    xff = req.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return req.client.host if req.client else None


def _ua(req: Request) -> Optional[str]:
    return req.headers.get("user-agent")


def _from_request_state(req: Request, key: str) -> Any:
    """Safely pull an optional attribute from request.state.

    Using getattr-with-default because starlette's State raises on unknown
    attribute access.
    """
    try:
        return getattr(req.state, key, None)
    except Exception:
        return None


# --------------------------------------------------------------------------
# Primary entrypoint
# --------------------------------------------------------------------------

def record_audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: uuid.UUID,
    actor_user_id: Optional[uuid.UUID],
    impersonator_user_id: Optional[uuid.UUID] = None,
    entity_id: Optional[uuid.UUID] = None,
    project_id: Optional[uuid.UUID] = None,
    field_changes: Optional[list[dict]] = None,
    metadata: Optional[dict] = None,
    request: Optional[Request] = None,
    session_id: Optional[uuid.UUID] = None,
) -> Optional[AuditLog]:
    """Insert an audit_log row. Never raises on bad input.

    An audit-write failure MUST NEVER block the business write. Callers
    should call this AFTER the primary mutation's db.flush() so they hold
    the real resource_id. Errors are logged and swallowed.
    """
    if action not in AUDIT_ACTIONS:
        log.error("record_audit: invalid action %r — dropping row", action)
        return None

    ip = None
    ua = None
    if request is not None:
        ip = _client_ip(request)
        ua = _ua(request)
        if session_id is None:
            session_id = _from_request_state(request, "current_session_id")
        if impersonator_user_id is None:
            impersonator_user_id = _from_request_state(request, "impersonator_user_id")

    changes = _redact(list(field_changes or []))
    # Defensive JSON safety pass — JSONB will refuse datetimes/UUIDs raw.
    changes = [
        {"field": c["field"], "old": _json_safe(c.get("old")), "new": _json_safe(c.get("new"))}
        for c in changes
    ]
    meta = _json_safe(metadata or {})
    if not isinstance(meta, dict):
        meta = {"value": meta}

    try:
        row = AuditLog(
            actor_user_id=actor_user_id,
            impersonator_user_id=impersonator_user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            entity_id=entity_id,
            project_id=project_id,
            field_changes=changes,
            metadata_json=meta,
            ip_address=ip,
            user_agent=ua,
            session_id=session_id,
        )
        db.add(row)
        db.flush()
        return row
    except Exception:
        log.exception(
            "record_audit: insert failed (action=%s resource=%s id=%s). "
            "Business write NOT rolled back.",
            action, resource_type, resource_id,
        )
        return None
