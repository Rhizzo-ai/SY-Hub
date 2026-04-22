"""Fernet envelope + TOTP + backup codes."""
from __future__ import annotations

import base64
import json
import os
import secrets
from typing import Any

import pyotp
import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from cryptography.fernet import Fernet, InvalidToken


_BACKUP_HASHER = PasswordHasher(time_cost=2, memory_cost=32 * 1024, parallelism=2)
_BACKUP_CODE_COUNT = 10
_BACKUP_CODE_CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_BACKUP_CODE_LEN = 10
_ISSUER_NAME = "SY Homes Operations"


def _get_fernet() -> Fernet:
    key = os.environ.get("MFA_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "MFA_ENCRYPTION_KEY is not set in backend/.env — generate with "
            "`python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())'`"
        )
    try:
        return Fernet(key.encode() if isinstance(key, str) else key)
    except (ValueError, TypeError) as e:
        raise RuntimeError(f"MFA_ENCRYPTION_KEY is not a valid Fernet key: {e}")


def encrypt_secret(plaintext: str) -> str:
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise RuntimeError(f"MFA payload decryption failed: {e}")


# ---------- TOTP ----------

def generate_totp_secret() -> str:
    """Return a base32 TOTP secret, unencrypted (persist via encrypt_secret)."""
    return pyotp.random_base32()


def totp_provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(
        name=email, issuer_name=_ISSUER_NAME
    )


def totp_qr_png_data_uri(secret: str, email: str) -> str:
    uri = totp_provisioning_uri(secret, email)
    img = qrcode.make(uri)
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{b64}"


def verify_totp(secret: str, code: str) -> bool:
    if not code or not secret:
        return False
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


# ---------- Backup codes ----------

def _format_code(raw: str) -> str:
    # Display as XXXXX-XXXXX for readability
    return f"{raw[:5]}-{raw[5:]}"


def generate_backup_codes(count: int = _BACKUP_CODE_COUNT) -> list[str]:
    """Return `count` plaintext backup codes (display once, then discard)."""
    out: list[str] = []
    for _ in range(count):
        code = "".join(secrets.choice(_BACKUP_CODE_CHARS) for _ in range(_BACKUP_CODE_LEN))
        out.append(_format_code(code))
    return out


def encrypt_backup_codes(plaintext_codes: list[str]) -> str:
    """Hash + encrypt the backup-codes array as a single string."""
    hashed = [
        {"hash": _BACKUP_HASHER.hash(c), "used_at": None}
        for c in plaintext_codes
    ]
    payload = json.dumps(hashed)
    return encrypt_secret(payload)


def consume_backup_code(
    encrypted_blob: str, code: str
) -> tuple[bool, str | None]:
    """Verify `code` against stored backup codes; mark used on success.

    Returns (verified, updated_blob). If not verified, returns (False, None).
    """
    try:
        payload = json.loads(decrypt_secret(encrypted_blob))
    except (json.JSONDecodeError, RuntimeError):
        return False, None

    now_iso = _now_iso()
    normalized = code.strip().upper().replace(" ", "")
    for entry in payload:
        if entry.get("used_at"):
            continue
        try:
            _BACKUP_HASHER.verify(entry["hash"], normalized)
        except (VerifyMismatchError, InvalidHashError):
            continue
        except Exception:
            continue
        entry["used_at"] = now_iso
        return True, encrypt_secret(json.dumps(payload))
    return False, None


def count_unused_backup_codes(encrypted_blob: str | None) -> int:
    if not encrypted_blob:
        return 0
    try:
        payload = json.loads(decrypt_secret(encrypted_blob))
    except Exception:
        return 0
    return sum(1 for entry in payload if not entry.get("used_at"))


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
