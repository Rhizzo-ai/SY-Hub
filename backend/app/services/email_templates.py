"""Inline HTML + plain-text templates.

All templates use inline CSS (many mail clients strip <style> blocks) and share
a common SY Homes layout: mono header, muted footer, tabular metadata.

Public helper: render(name, **context) -> (subject, html_body, text_body)
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable


_BRAND_BG = "#0f172a"
_BRAND_ACCENT = "#1e293b"
_MUTED = "#64748b"
_BORDER = "#e2e8f0"


def _wrap(title: str, body_html: str, preheader: str = "") -> str:
    year = datetime.now(timezone.utc).year
    return f"""<!doctype html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;padding:0;background:#f8fafc;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;color:#0f172a">
<div style="display:none;max-height:0;overflow:hidden;opacity:0">{preheader}</div>
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f8fafc;padding:40px 16px">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#ffffff;border:1px solid {_BORDER};border-radius:8px;overflow:hidden">
<tr><td style="background:{_BRAND_BG};padding:24px 32px;color:#ffffff">
  <div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;letter-spacing:3px;text-transform:uppercase;opacity:0.7">SY Homes · Operations</div>
  <div style="font-weight:700;font-size:20px;margin-top:4px">{title}</div>
</td></tr>
<tr><td style="padding:32px">
{body_html}
</td></tr>
<tr><td style="background:#f8fafc;padding:20px 32px;border-top:1px solid {_BORDER};font-size:12px;color:{_MUTED}">
  Sent automatically by SY Homes Operations · © {year}<br>
  If anything looks off, reply to this email or contact your administrator.
</td></tr>
</table>
</td></tr>
</table>
</body></html>
"""


def _btn(href: str, label: str) -> str:
    return (
        f'<a href="{href}" style="display:inline-block;background:{_BRAND_BG};'
        f'color:#ffffff;padding:12px 24px;border-radius:6px;text-decoration:none;'
        f'font-weight:600;font-size:14px">{label}</a>'
    )


# --- password_reset_email ---------------------------------------------------
def password_reset_email(
    *, recipient_name: str, reset_url: str, admin_initiated_by: str | None = None,
) -> tuple[str, str, str]:
    who = (
        f"An administrator ({admin_initiated_by}) initiated this on your behalf."
        if admin_initiated_by
        else "You (or someone with your email) requested this."
    )
    subject = "Reset your SY Homes password"
    html = _wrap(
        "Reset your password",
        f"""
        <p>Hi {recipient_name},</p>
        <p>{who} Click below to set a new password. This link is good for one hour.</p>
        <p style="margin:24px 0">{_btn(reset_url, "Reset password")}</p>
        <p style="color:{_MUTED};font-size:13px">
            If the button doesn't work, copy and paste this URL:<br>
            <span style="font-family:ui-monospace,monospace;word-break:break-all">{reset_url}</span>
        </p>
        <p style="color:{_MUTED};font-size:13px;margin-top:24px">
            Didn't request this? You can safely ignore this email — your password won't change.
        </p>
        """,
        preheader="Reset your SY Homes password — link expires in 1 hour.",
    )
    text = (
        f"Hi {recipient_name},\n\n"
        f"{who} Use the link below to set a new password (valid for 1 hour):\n\n"
        f"{reset_url}\n\n"
        f"If you didn't request this, ignore this email — your password won't change.\n"
    )
    return subject, html, text


# --- password_changed_email -------------------------------------------------
def password_changed_email(
    *, recipient_name: str, when: datetime, ip: str,
    admin_initiated_by: str | None = None,
) -> tuple[str, str, str]:
    who = (
        f"changed by administrator ({admin_initiated_by})"
        if admin_initiated_by
        else "changed"
    )
    when_str = when.strftime("%d %b %Y, %H:%M UTC")
    subject = "Your SY Homes password was changed"
    html = _wrap(
        "Password changed",
        f"""
        <p>Hi {recipient_name},</p>
        <p>Your SY Homes password was {who} on <strong>{when_str}</strong> from IP <code>{ip}</code>.</p>
        <p>All active sessions were signed out — you'll need to log in again on every device.</p>
        <p style="color:#7c2d12;background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:6px;font-size:13px">
            <strong>Didn't do this?</strong> Contact your administrator immediately.
        </p>
        """,
    )
    text = (
        f"Hi {recipient_name},\n\n"
        f"Your SY Homes password was {who} on {when_str} from IP {ip}.\n"
        f"All active sessions were signed out.\n\n"
        f"Didn't do this? Contact your administrator immediately.\n"
    )
    return subject, html, text


# --- session_revoked_email --------------------------------------------------
def session_revoked_email(
    *, recipient_name: str, revoked_by: str, reason: str,
) -> tuple[str, str, str]:
    subject = "Your SY Homes sessions were revoked"
    html = _wrap(
        "Sessions revoked",
        f"""
        <p>Hi {recipient_name},</p>
        <p>Your active SY Homes sessions were revoked by <strong>{revoked_by}</strong>
        (reason: {reason}).</p>
        <p>You'll need to log in again. If this wasn't expected, contact your administrator.</p>
        """,
    )
    text = (
        f"Hi {recipient_name},\n\n"
        f"Your active SY Homes sessions were revoked by {revoked_by} (reason: {reason}).\n"
        f"You'll need to log in again.\n"
    )
    return subject, html, text


TEMPLATES: dict[str, Callable] = {
    "password_reset_email": password_reset_email,
    "password_changed_email": password_changed_email,
    "session_revoked_email": session_revoked_email,
}
