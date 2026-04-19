"""Pytest config — loads backend .env before any app imports.

Also provides a session-scoped fixture to ensure alembic migrations are
applied before tests run (so the schema matches what the tests expect).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

# Sanity check so tests fail fast with a clear message.
assert "DATABASE_URL" in os.environ, (
    "DATABASE_URL is not set; check /app/backend/.env"
)
