"""Postmark inbound webhook payload schema — Prompt 2.5A / Chat 19A.

We accept Postmark's full inbound JSON shape per
https://postmarkapp.com/developer/webhooks/inbound-webhook with
`extra='allow'` because Postmark adds fields over time and we don't want to
break on benign additions. Required fields are explicit.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PostmarkAttachment(BaseModel):
    model_config = ConfigDict(extra="allow")
    Name: str
    Content: str  # base64
    ContentType: str = ""
    ContentLength: int = 0


class PostmarkInboundPayload(BaseModel):
    """The subset of fields we use. Postmark sends ~30 fields; we ignore the rest."""
    model_config = ConfigDict(extra="allow")

    MessageID: str
    From: str
    FromName: Optional[str] = None
    To: str = ""
    Subject: Optional[str] = ""
    Date: Optional[str] = None
    TextBody: Optional[str] = ""
    HtmlBody: Optional[str] = ""
    Attachments: List[PostmarkAttachment] = Field(default_factory=list)
