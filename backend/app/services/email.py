"""Email infrastructure — ConsoleEmailProvider default.

To flip to SendGrid in production:
  1. Add SENDGRID_API_KEY, EMAIL_FROM_ADDRESS, EMAIL_FROM_NAME, EMAIL_REPLY_TO to backend/.env
  2. `pip install sendgrid` and add to requirements.txt
  3. Uncomment the SendGridEmailProvider branch in `get_email_provider()` below
  4. That's it — the interface is identical, and every call site already hits get_email_provider().

All sends are logged to email_send_log regardless of provider so we can trace
deliverability without diving into the SendGrid dashboard.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Protocol

from sqlalchemy.orm import Session

from app.models.sessions import EmailSendLog

log = logging.getLogger("syhomes.email")


@dataclass
class SendResult:
    ok: bool
    status: str
    provider_message_id: Optional[str] = None
    error: Optional[str] = None


class EmailProvider(Protocol):
    template_id: str  # sentinel so we know the provider shape
    def send(
        self, to: str, subject: str, html: str, text: str,
        template_id: Optional[str] = None,
    ) -> SendResult: ...


class ConsoleEmailProvider:
    """Writes emails to stdout. Used when SENDGRID_API_KEY is not set."""

    def send(
        self, to: str, subject: str, html: str, text: str,
        template_id: Optional[str] = None,
    ) -> SendResult:
        banner = "\n" + "=" * 72 + "\n"
        log.info(
            "%s[dev_console email] → %s\n  Subject: %s\n  Template: %s\n\n%s%s",
            banner, to, subject, template_id or "(none)", text, banner,
        )
        return SendResult(ok=True, status="dev_console", provider_message_id=None)


# --- SendGrid provider (inactive until key supplied) ---------------------------------
# class SendGridEmailProvider:  # pragma: no cover - not wired in stage 1b
#     def __init__(self, api_key: str, from_addr: str, from_name: str, reply_to: str):
#         import sendgrid  # lazy
#         self._sg = sendgrid.SendGridAPIClient(api_key)
#         self._from = (from_addr, from_name)
#         self._reply_to = reply_to
#     def send(self, to, subject, html, text, template_id=None):
#         from sendgrid.helpers.mail import Mail, Email, To, Content, ReplyTo
#         mail = Mail(
#             from_email=Email(self._from[0], self._from[1]),
#             to_emails=To(to),
#             subject=subject,
#             plain_text_content=Content("text/plain", text),
#             html_content=Content("text/html", html),
#         )
#         if self._reply_to:
#             mail.reply_to = ReplyTo(self._reply_to)
#         try:
#             resp = self._sg.send(mail)
#             mid = resp.headers.get("X-Message-Id") if hasattr(resp, "headers") else None
#             return SendResult(ok=True, status="sent", provider_message_id=mid)
#         except Exception as e:
#             return SendResult(ok=False, status="failed", error=str(e))


_provider: Optional[EmailProvider] = None


def get_email_provider() -> EmailProvider:
    global _provider
    if _provider is not None:
        return _provider
    key = os.environ.get("SENDGRID_API_KEY", "").strip()
    # if key:
    #     _provider = SendGridEmailProvider(
    #         api_key=key,
    #         from_addr=os.environ["EMAIL_FROM_ADDRESS"],
    #         from_name=os.environ.get("EMAIL_FROM_NAME", "SY Homes"),
    #         reply_to=os.environ.get("EMAIL_REPLY_TO", ""),
    #     )
    # else:
    _provider = ConsoleEmailProvider()
    return _provider


def send_email(
    db: Session,
    to: str,
    subject: str,
    html: str,
    text: str,
    template_id: Optional[str] = None,
) -> EmailSendLog:
    """Send an email and persist a row to email_send_log.

    Never raises — failures are recorded with status='failed' + error message.
    Callers that absolutely need to know about failure should read the
    returned log record.
    """
    provider = get_email_provider()
    try:
        result = provider.send(to, subject, html, text, template_id)
    except Exception as e:  # safety net
        result = SendResult(ok=False, status="failed", error=str(e))

    record = EmailSendLog(
        to_address=to,
        subject=subject,
        template_id=template_id,
        status=result.status,
        error=result.error,
        provider_message_id=result.provider_message_id,
    )
    db.add(record)
    db.flush()
    return record
