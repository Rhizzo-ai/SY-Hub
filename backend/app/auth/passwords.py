"""argon2id password hashing + history + complexity."""
from __future__ import annotations

import re
from typing import Iterable

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError


# OWASP-recommended argon2id parameters.
_HASHER = PasswordHasher(
    memory_cost=64 * 1024,  # 64 MiB
    time_cost=3,
    parallelism=4,
    hash_len=32,
    salt_len=16,
)

MIN_PASSWORD_LENGTH = 12
PASSWORD_HISTORY_SIZE = 5

# Complexity rules — spelled out so the UI can render the same list.
PASSWORD_RULES: list[tuple[str, str]] = [
    ("length", f"At least {MIN_PASSWORD_LENGTH} characters"),
    ("uppercase", "At least one uppercase letter (A–Z)"),
    ("lowercase", "At least one lowercase letter (a–z)"),
    ("number", "At least one number (0–9)"),
    ("symbol", "At least one symbol (e.g. ! @ # $ % ^ & *)"),
]

_UPPER_RE = re.compile(r"[A-Z]")
_LOWER_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"[0-9]")
_SYMBOL_RE = re.compile(r"[^A-Za-z0-9]")


class PasswordPolicyError(ValueError):
    pass


def validate_complexity(password: str) -> None:
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )
    if not _UPPER_RE.search(password):
        raise PasswordPolicyError(
            "Password must contain at least one uppercase letter (A–Z)"
        )
    if not _LOWER_RE.search(password):
        raise PasswordPolicyError(
            "Password must contain at least one lowercase letter (a–z)"
        )
    if not _DIGIT_RE.search(password):
        raise PasswordPolicyError(
            "Password must contain at least one number (0–9)"
        )
    if not _SYMBOL_RE.search(password):
        raise PasswordPolicyError(
            "Password must contain at least one symbol (e.g. ! @ # $ % ^ & *)"
        )


def hash_password(password: str) -> str:
    validate_complexity(password)
    return _HASHER.hash(password)


def hash_token(token: str) -> str:
    """Argon2id hash without user-password complexity rules.

    Use for random tokens (invitations, password-reset) whose entropy comes
    from `secrets.token_urlsafe` rather than user input, so the uppercase /
    lowercase / digit / symbol requirements don't apply.
    """
    if not isinstance(token, str) or len(token) < 16:
        raise ValueError("Token must be at least 16 characters")
    return _HASHER.hash(token)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        _HASHER.verify(stored_hash, password)
        return True
    except (VerifyMismatchError, InvalidHashError, TypeError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _HASHER.check_needs_rehash(stored_hash)
    except (InvalidHashError, Exception):
        return True


def is_in_history(password: str, history: Iterable[dict]) -> bool:
    for row in history or []:
        h = row.get("hash") if isinstance(row, dict) else None
        if not h:
            continue
        if verify_password(password, h):
            return True
    return False
