"""Pydantic schemas for user_preferences endpoints (Chat 23 R1.4)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class UserPreferenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    surface_key: str
    name: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class CurrentPayloadIn(BaseModel):
    """PUT body for the autosave path. `payload` is REPLACED in full."""
    payload: dict[str, Any] = Field(default_factory=dict)


class SavedViewIn(BaseModel):
    """POST body for creating a named view."""
    name: str = Field(min_length=1, max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)


class SavedViewUpdateIn(BaseModel):
    """PUT body for updating an existing named view."""
    payload: dict[str, Any] = Field(default_factory=dict)


class SurfaceSnapshotOut(BaseModel):
    """Combined GET response: current state + all named views."""
    surface_key: str
    current: dict[str, Any] = Field(default_factory=dict)
    # `current` holds the payload directly (not wrapped). When the row
    # is absent (greenfield) the dict is empty — never null — so the
    # frontend can spread it without an `if` branch.
    views: list[UserPreferenceOut] = Field(default_factory=list)
