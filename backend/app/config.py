"""Centralised application settings — Prompt 2.5A / Chat 19A.

Introduced in this chat to consolidate environment-variable access for the
actuals pipeline. Pre-existing modules continue to read `os.environ` directly;
that is fine. New code SHOULD prefer `from app.config import get_settings`.

This module is intentionally framework-light (no pydantic-settings dependency)
so it can be imported during alembic startup without dragging the full ORM
graph in.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Idempotent: subsequent loads do not override existing env vars.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_BACKEND_ROOT / ".env")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # Environment
    app_env: str = field(default_factory=lambda: os.environ.get("APP_ENV", "dev"))

    # Database
    database_url: str = field(default_factory=lambda: os.environ.get("DATABASE_URL", ""))

    # Actuals attachment storage
    actuals_attachments_dir: str = field(
        default_factory=lambda: os.environ.get(
            "ACTUALS_ATTACHMENTS_DIR",
            str(_BACKEND_ROOT / "var" / "attachments"),
        )
    )
    actuals_attachment_max_bytes: int = field(
        default_factory=lambda: _env_int("ACTUALS_ATTACHMENT_MAX_BYTES", 25 * 1024 * 1024)
    )

    # AI capture pipeline
    # AI_CAPTURE_MODEL='test-stub' short-circuits to deterministic fixture output
    # (no live Anthropic call). Any other value is treated as an Anthropic model id.
    ai_capture_model: str = field(
        default_factory=lambda: os.environ.get("AI_CAPTURE_MODEL", "test-stub")
    )
    anthropic_api_key: str = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", "")
    )
    ai_capture_max_attempts: int = field(
        default_factory=lambda: _env_int("AI_CAPTURE_MAX_ATTEMPTS", 3)
    )
    ai_capture_inbound_dir: str = field(
        default_factory=lambda: os.environ.get(
            "AI_CAPTURE_INBOUND_DIR",
            str(_BACKEND_ROOT / "var" / "inbound"),
        )
    )

    # Postmark inbound
    postmark_inbound_secret: str = field(
        default_factory=lambda: os.environ.get("POSTMARK_INBOUND_SECRET", "")
    )
    postmark_inbound_enabled: bool = field(
        default_factory=lambda: _env_bool("POSTMARK_INBOUND_ENABLED", False)
    )

    @property
    def is_test(self) -> bool:
        return self.app_env.lower() == "test"

    @property
    def is_ai_stub(self) -> bool:
        return self.ai_capture_model == "test-stub"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Clear the lru_cache. For tests that monkeypatch env vars."""
    get_settings.cache_clear()
