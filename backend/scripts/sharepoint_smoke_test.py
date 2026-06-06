"""SharePoint smoke test — operator-run live verification.

Build Pack 2.7-BE-rev-B §R6. NOT part of the automated test suite. The
operator runs this ONCE Azure admin consent + Sites.Selected grant are
in place, to prove the entire chain (auth → site → folder → upload →
download → delete) works end-to-end against the real Microsoft Graph.

This script REFUSES to run in stub mode — its whole purpose is the
live-mode handshake. Stub mode is exercised by the unit suite
(`tests/test_sharepoint_client.py` + `tests/test_supplier_document_files.py`).

Usage
-----

Required env vars (set in your shell or a `.env` not committed to git):

    SHAREPOINT_MODE=live
    SHAREPOINT_TENANT_ID=<Azure AD tenant id>
    SHAREPOINT_CLIENT_ID=<App registration client id>
    SHAREPOINT_CLIENT_SECRET=<App registration client secret>
    SHAREPOINT_SITE_URL=https://<tenant>.sharepoint.com/sites/<site-name>
    SHAREPOINT_DRIVE_NAME=Documents          # optional, default 'Documents'
    SHAREPOINT_ROOT_FOLDER=SY-Hub            # optional, default 'SY-Hub'

Run the round-trip check:

    cd backend
    python scripts/sharepoint_smoke_test.py

Run the round-trip AND perform the `Sites.Selected` site-grant
(required once per app/site, before the round-trip will succeed):

    cd backend
    python scripts/sharepoint_smoke_test.py --grant

Output is intentionally verbose for the operator. **No secret, token,
or Graph response body is ever printed** — only the resolved config
(mode, site_url, drive_name, root_folder), the redacted
tenant/client/site IDs, structural status messages, and the final
"round-trip OK" / actionable failure line.

Exit codes
----------
    0 — success ("✅ round-trip OK")
    1 — operational failure (see actionable message printed above)
    2 — refused to run (stub mode, or missing required env vars)
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# Ensure `app` package is importable when the script is invoked as
# `python backend/scripts/sharepoint_smoke_test.py` from any cwd.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(_BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(_BACKEND_ROOT))


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _redact_id(value: str, *, keep: int = 4) -> str:
    """Show only the first `keep` chars of an opaque id."""
    if not value:
        return "<empty>"
    if len(value) <= keep:
        return value
    return f"{value[:keep]}…(redacted)"


def _print_config(settings) -> None:
    """Print resolved non-secret config. Secrets are NEVER printed."""
    print("=== SharePoint smoke test — resolved configuration ===")
    print(f"  mode         : {settings.sharepoint_mode}")
    print(f"  tenant_id    : {_redact_id(settings.sharepoint_tenant_id)}")
    print(f"  client_id    : {_redact_id(settings.sharepoint_client_id)}")
    has_secret = bool(settings.sharepoint_client_secret)
    print(f"  client_secret: {'<set>' if has_secret else '<UNSET>'}  "
          "(value never printed)")
    print(f"  site_url     : {settings.sharepoint_site_url}")
    print(f"  drive_name   : {settings.sharepoint_drive_name}")
    print(f"  root_folder  : {settings.sharepoint_root_folder}")
    print(f"  max_bytes    : {settings.sharepoint_max_bytes}")
    print("")


def _require_live_mode(settings) -> None:
    """Refuse to run in stub mode. Live verification is the whole point."""
    if settings.is_sharepoint_stub:
        print(
            "REFUSED: this script is operator-run live verification.\n"
            "  SHAREPOINT_MODE is currently "
            f"{settings.sharepoint_mode!r} (stub).\n"
            "  Stub-mode coverage is the automated unit suite:\n"
            "    pytest tests/test_sharepoint_client.py\n"
            "    pytest tests/test_supplier_document_files.py\n\n"
            "  To run live: export SHAREPOINT_MODE=live and provide\n"
            "  SHAREPOINT_TENANT_ID / CLIENT_ID / CLIENT_SECRET / SITE_URL,\n"
            "  then re-run this script.",
            file=sys.stderr,
        )
        sys.exit(2)


def _require_creds(settings) -> None:
    """Check the four required env vars are set in live mode."""
    missing = [
        name for name, val in (
            ("SHAREPOINT_TENANT_ID", settings.sharepoint_tenant_id),
            ("SHAREPOINT_CLIENT_ID", settings.sharepoint_client_id),
            ("SHAREPOINT_CLIENT_SECRET", settings.sharepoint_client_secret),
            ("SHAREPOINT_SITE_URL", settings.sharepoint_site_url),
        ) if not val
    ]
    if missing:
        print(
            "REFUSED: missing required SharePoint env vars: "
            + ", ".join(missing),
            file=sys.stderr,
        )
        sys.exit(2)


def _hint_for_failure(exc: Exception) -> str:
    """Map common live-mode failures to an actionable operator hint."""
    from app.services.sharepoint_client import (
        SharePointConfigError, SharePointError,
    )

    msg = str(exc) or exc.__class__.__name__
    if isinstance(exc, SharePointConfigError):
        return f"CONFIG ERROR — {msg}"

    if not isinstance(exc, SharePointError):
        # Truly unexpected: bubble up the type but never the body.
        return f"UNEXPECTED ({exc.__class__.__name__}) — {msg}"

    # The httpx layer logs status codes via the module logger but the
    # SharePointError message is intentionally generic ("document
    # storage unavailable" / "authentication failed"). The most common
    # failure shapes:
    text = msg.lower()
    if "authentication" in text:
        return (
            "403/AUTH — likely causes:\n"
            "  • Azure admin consent not granted for this app yet.\n"
            "  • Client secret expired / wrong tenant id.\n"
            "  • Sites.Selected not yet granted for this app on this site\n"
            "    — re-run with `--grant`.\n"
            "Check the server-side log (stderr above) for the actual\n"
            "Graph status code; secret values are never logged."
        )
    if "exceeds maximum" in text:
        return (
            "PAYLOAD TOO LARGE — file exceeds SHAREPOINT_MAX_BYTES.\n"
            "  Increase the cap or shrink the payload."
        )
    return (
        "STORAGE UNAVAILABLE — Graph call failed.\n"
        "  Common causes:\n"
        "    • 404 site — check SHAREPOINT_SITE_URL.\n"
        "    • 403 — site not granted to app, run with --grant.\n"
        "    • 429 — throttled (the client retried once; try again).\n"
        "  Check stderr above for the structured client log line."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "SharePoint smoke test (operator-run, live mode only). "
            "Refuses to run in SHAREPOINT_MODE='test-stub'."
        ),
    )
    parser.add_argument(
        "--grant",
        action="store_true",
        help=(
            "Before the round-trip, perform the Sites.Selected site-grant "
            "for this app. Required ONCE per app/site, by an operator who "
            "holds tenant-admin rights for the resource. Idempotent: "
            "re-running is safe."
        ),
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable DEBUG logging (still redacts secrets).",
    )
    args = parser.parse_args()

    _setup_logging(args.verbose)

    # Defer the heavy imports until after argparse so `--help` is fast.
    from app.config import get_settings, reset_settings_cache
    from app.services.sharepoint_client import (
        SharePointError, get_document_store,
    )

    # Always re-read env in case the operator set vars in the same
    # shell as a previous invocation.
    reset_settings_cache()
    settings = get_settings()

    _print_config(settings)
    _require_live_mode(settings)
    _require_creds(settings)

    try:
        store = get_document_store()
    except Exception as exc:  # noqa: BLE001 — operator wants the hint
        print("❌ Failed to construct the document store.", file=sys.stderr)
        print(_hint_for_failure(exc), file=sys.stderr)
        return 1

    # --grant: Sites.Selected permission grant.
    if args.grant:
        print("Granting Sites.Selected to this app on the configured site…")
        try:
            store.grant_site_access()
        except Exception as exc:  # noqa: BLE001
            print("❌ Site-grant failed.", file=sys.stderr)
            print(_hint_for_failure(exc), file=sys.stderr)
            return 1
        print("✅ Site grant call returned OK.\n")

    # Round-trip: ensure folder → upload → download → delete.
    test_folder = "_smoketest"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    test_filename = f"sy-hub-smoke-{stamp}-{uuid.uuid4().hex[:8]}.txt"
    payload = (
        f"SY-Hub rev-B smoke test {stamp}. "
        f"This file is safe to delete."
    ).encode("utf-8")
    content_type = "text/plain"

    print(f"Step 1/4: ensure_folder({test_folder!r})…")
    try:
        store.ensure_folder(test_folder)
        print("  → OK")
    except Exception as exc:  # noqa: BLE001
        print("❌ ensure_folder failed.", file=sys.stderr)
        print(_hint_for_failure(exc), file=sys.stderr)
        return 1

    print(f"Step 2/4: upload({test_filename!r}, {len(payload)} bytes)…")
    stored_ref: Optional[object] = None
    try:
        stored_ref = store.upload(
            folder_path=test_folder,
            filename=test_filename,
            content=payload,
            content_type=content_type,
        )
        print(
            "  → OK — item_id=" + _redact_id(stored_ref.item_id, keep=6)
        )
    except Exception as exc:  # noqa: BLE001
        print("❌ upload failed.", file=sys.stderr)
        print(_hint_for_failure(exc), file=sys.stderr)
        return 1

    print("Step 3/4: download + byte-exact compare…")
    try:
        downloaded, name, ctype = store.download(stored_ref.to_json())
    except Exception as exc:  # noqa: BLE001
        print("❌ download failed.", file=sys.stderr)
        print(_hint_for_failure(exc), file=sys.stderr)
        return 1
    if downloaded != payload:
        print(
            "❌ DOWNLOAD MISMATCH — uploaded "
            f"{len(payload)} bytes but got {len(downloaded)} back; "
            "content differs.",
            file=sys.stderr,
        )
        return 1
    if name != test_filename:
        print(
            f"⚠️  filename changed in round-trip: {name!r} "
            f"(expected {test_filename!r})",
            file=sys.stderr,
        )
    print(f"  → OK — {len(downloaded)} bytes, content-type {ctype!r}")

    print("Step 4/4: delete (cleanup)…")
    try:
        store.delete(stored_ref.to_json())
        print("  → OK")
    except Exception as exc:  # noqa: BLE001
        print(
            "⚠️  delete failed — the smoke-test artefact may still exist "
            "in the drive. Removing it manually is safe.",
            file=sys.stderr,
        )
        print(_hint_for_failure(exc), file=sys.stderr)
        # Round-trip itself succeeded; we still return 0.

    print("")
    print("✅ round-trip OK — SharePoint is wired correctly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
