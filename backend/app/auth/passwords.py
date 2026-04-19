"""argon2id password hashing + history + complexity."""
from __future__ import annotations

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


class PasswordPolicyError(ValueError):
    pass


def validate_complexity(password: str) -> None:
    if not isinstance(password, str):
        raise PasswordPolicyError("Password must be a string")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters"
        )


def hash_password(password: str) -> str:
    validate_complexity(password)
    return _HASHER.hash(password)


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
