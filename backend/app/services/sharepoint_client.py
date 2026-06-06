"""SharePoint / Microsoft Graph document store — Chat 41 rev-B (§R2).

This module is the platform's document-storage engine. It is deliberately
document-type-agnostic: supplier compliance docs land on it now; drawings,
invoices, and QA photos will sit on the same `DocumentStore` interface later.

Architecture mirrors the AI-capture stub pattern verbatim:

    SHAREPOINT_MODE='test-stub'  -> StubDocumentStore  (in-process, no network)
    SHAREPOINT_MODE='live'       -> GraphDocumentStore (real Microsoft Graph)

The stub IS the test surface. Every automated test runs against the stub —
zero Azure credentials, zero network, deterministic round-trip. The live
path is exercised only by the operator-run smoke-test script (§R6) once
Azure admin consent + Sites.Selected grant are in place.

No secret, token, or Graph internal may ever appear in an API response or
log. Live-mode-with-blank-creds fails loud (SharePointConfigError). Any
Graph operational failure surfaces as SharePointError -> mapped to HTTP 502
"document storage unavailable" upstream.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from dataclasses import dataclass, asdict
from typing import Optional, Protocol, Tuple
from urllib.parse import quote

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Exceptions
# --------------------------------------------------------------------------- #
class SharePointError(Exception):
    """Operational failure talking to the document store.

    Routers map this -> HTTP 502 "document storage unavailable". Message
    MUST be safe to surface; Graph internals (URLs, tokens, response
    bodies) MUST NOT leak into the message.
    """


class SharePointConfigError(Exception):
    """Misconfiguration — live mode requested without all required creds.

    This is fail-loud at factory-construction time; it should never be
    caught and silently downgraded to stub mode.
    """


# --------------------------------------------------------------------------- #
# StoredObjectRef — the JSON pointer we persist in supplier_documents.file_ref
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StoredObjectRef:
    """Structured pointer to a file in the document store.

    Persisted as JSON in `supplier_documents.file_ref` (Text, widened in
    migration 0042). System-owned — clients never construct or submit this.
    """
    item_id: str
    drive_id: str
    web_url: str
    name: str
    size: int
    content_type: str

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",", ":"), sort_keys=True)

    @classmethod
    def from_json(cls, raw: str) -> "StoredObjectRef":
        try:
            d = json.loads(raw)
            return cls(
                item_id=str(d["item_id"]),
                drive_id=str(d["drive_id"]),
                web_url=str(d["web_url"]),
                name=str(d["name"]),
                size=int(d["size"]),
                content_type=str(d["content_type"]),
            )
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            raise SharePointError("invalid stored file reference") from e


# --------------------------------------------------------------------------- #
# Filename safety
# --------------------------------------------------------------------------- #
_UNSAFE_CHARS_RE = re.compile(r'[\x00-\x1f\\/"<>:|?*]')


def _safe_filename(name: str) -> str:
    """Strip path traversal + control chars, preserve extension.

    - basename only: '../etc/passwd' -> 'passwd'
    - drops control chars (\\x00-\\x1f) + Windows-illegal chars
    - non-printables -> '_'
    - capped at 200 chars (Graph item-name limit is ~400; we stay well under)
    - empty result falls back to 'file'
    """
    base = os.path.basename(name or "")
    # Replace unsafe + control chars with '_'
    cleaned = _UNSAFE_CHARS_RE.sub("_", base)
    # Replace any other non-printable
    cleaned = "".join(ch if ch.isprintable() else "_" for ch in cleaned)
    cleaned = cleaned.strip(" .")  # leading/trailing dots & spaces are unsafe
    if not cleaned:
        cleaned = "file"
    return cleaned[:200]


# --------------------------------------------------------------------------- #
# DocumentStore protocol
# --------------------------------------------------------------------------- #
class DocumentStore(Protocol):
    """Document-store contract.

    Document-type-agnostic by design — drawings/invoices/QA photos will
    sit on this same interface. Implementations: StubDocumentStore (tests),
    GraphDocumentStore (live SharePoint via Microsoft Graph).
    """

    def ensure_folder(self, folder_path: str) -> str:
        """Idempotently ensure folder_path exists. Returns folder item id."""
        ...

    def upload(
        self,
        folder_path: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> StoredObjectRef:
        """Upload bytes. Returns a structured StoredObjectRef pointer."""
        ...

    def download(self, ref_json: str) -> Tuple[bytes, str, str]:
        """Download by ref. Returns (content, filename, content_type)."""
        ...

    def delete(self, ref_json: str) -> None:
        """Delete by ref. Idempotent — no error if already gone."""
        ...


# --------------------------------------------------------------------------- #
# StubDocumentStore — in-process, deterministic, zero network
# --------------------------------------------------------------------------- #
class StubDocumentStore:
    """In-process fake store for tests.

    Mirrors the AI-capture test-stub pattern: no network, no auth, no
    Azure dependency. Per-instance state — tests get a clean store by
    constructing a new instance (or calling `reset()`).
    """

    _DRIVE_ID = "stub-drive"

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._folders: dict[str, str] = {}  # path -> folder_id
        self._items: dict[str, dict] = {}   # item_id -> {content, ref}

    def reset(self) -> None:
        with self._lock:
            self._folders.clear()
            self._items.clear()

    # -- internals --------------------------------------------------------- #
    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}-{uuid.uuid4().hex}"

    # -- DocumentStore API ------------------------------------------------- #
    def ensure_folder(self, folder_path: str) -> str:
        if not folder_path:
            raise SharePointError("folder_path required")
        with self._lock:
            fid = self._folders.get(folder_path)
            if fid is None:
                fid = self._new_id("folder")
                self._folders[folder_path] = fid
            return fid

    def upload(
        self,
        folder_path: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> StoredObjectRef:
        if not isinstance(content, (bytes, bytearray)):
            raise SharePointError("content must be bytes")
        safe = _safe_filename(filename)
        with self._lock:
            self.ensure_folder(folder_path)  # idempotent
            item_id = self._new_id("item")
            # Build a plausible-looking web_url (NOT a real SharePoint URL).
            web_url = (
                f"https://stub.sharepoint.invalid/sites/syhub/Shared%20Documents/"
                f"{quote(folder_path)}/{quote(safe)}"
            )
            ref = StoredObjectRef(
                item_id=item_id,
                drive_id=self._DRIVE_ID,
                web_url=web_url,
                name=safe,
                size=len(content),
                content_type=content_type,
            )
            self._items[item_id] = {
                "content": bytes(content),
                "ref": ref,
            }
            return ref

    def download(self, ref_json: str) -> Tuple[bytes, str, str]:
        ref = StoredObjectRef.from_json(ref_json)
        with self._lock:
            obj = self._items.get(ref.item_id)
        if obj is None:
            raise SharePointError("file not found")
        stored: StoredObjectRef = obj["ref"]
        return obj["content"], stored.name, stored.content_type

    def delete(self, ref_json: str) -> None:
        # Idempotent: bad ref / missing item is a no-op, not an error.
        try:
            ref = StoredObjectRef.from_json(ref_json)
        except SharePointError:
            return
        with self._lock:
            self._items.pop(ref.item_id, None)

    # -- test helpers ------------------------------------------------------ #
    def has_item(self, item_id: str) -> bool:
        with self._lock:
            return item_id in self._items


# --------------------------------------------------------------------------- #
# GraphDocumentStore — live Microsoft Graph (scaffolded, NOT exercised in build)
# --------------------------------------------------------------------------- #
class GraphDocumentStore:
    """Live Microsoft Graph document store (client-credentials flow).

    NOTE — Build Pack 2.7-BE-rev-B Gate 1: this class is constructable
    and has the network-shaped surface (auth + simple PUT + upload-session
    + streamed download + retry), but is NOT exercised during the build.
    The operator-run smoke-test (§R6, Gate 3) is the live verification
    path. ALL automated tests use StubDocumentStore.

    Robustness invariants (any deviation must be noted in CHANGELOG):
    - Client-credentials OAuth2 with token cache + 60s pre-expiry refresh.
    - Simple PUT for content <= 4 MB; upload session w/ 10 MB chunks above.
    - Streamed download — the SharePoint URL never leaves this module.
    - 429 / 503 honour Retry-After, single retry on transient 5xx.
    - SharePointError on operational failure (mapped to 502 upstream).
    - No secret, token, or Graph body ever logged.
    """

    _GRAPH_BASE = "https://graph.microsoft.com/v1.0"
    _SIMPLE_PUT_MAX = 4 * 1024 * 1024  # 4 MB — Graph upload-session threshold
    _CHUNK_SIZE = 10 * 1024 * 1024     # 10 MB — recommended chunk size

    def __init__(self, settings=None) -> None:
        s = settings or get_settings()
        missing = [
            n for n, v in (
                ("SHAREPOINT_TENANT_ID", s.sharepoint_tenant_id),
                ("SHAREPOINT_CLIENT_ID", s.sharepoint_client_id),
                ("SHAREPOINT_CLIENT_SECRET", s.sharepoint_client_secret),
                ("SHAREPOINT_SITE_URL", s.sharepoint_site_url),
            ) if not v
        ]
        if missing:
            # Fail loud — do not silently fall back to stub.
            raise SharePointConfigError(
                "SharePoint live mode missing required config: "
                + ", ".join(missing)
            )
        self._tenant_id = s.sharepoint_tenant_id
        self._client_id = s.sharepoint_client_id
        self._client_secret = s.sharepoint_client_secret
        self._site_url = s.sharepoint_site_url
        self._drive_name = s.sharepoint_drive_name
        self._root_folder = s.sharepoint_root_folder
        self._max_bytes = s.sharepoint_max_bytes

        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0
        self._site_id_cache: Optional[str] = None
        self._drive_id_cache: Optional[str] = None
        self._lock = threading.Lock()

    # -- auth -------------------------------------------------------------- #
    def _get_access_token(self) -> str:
        with self._lock:
            now = time.time()
            if self._token and now < self._token_expires_at - 60:
                return self._token
            url = (
                f"https://login.microsoftonline.com/"
                f"{self._tenant_id}/oauth2/v2.0/token"
            )
            try:
                resp = httpx.post(
                    url,
                    data={
                        "grant_type": "client_credentials",
                        "client_id": self._client_id,
                        "client_secret": self._client_secret,
                        "scope": "https://graph.microsoft.com/.default",
                    },
                    timeout=30.0,
                )
                resp.raise_for_status()
                body = resp.json()
            except httpx.HTTPError as e:
                # Do NOT include response body / token / secret in the message.
                log.error("sharepoint_auth_failed status=%s",
                          getattr(getattr(e, "response", None),
                                  "status_code", "n/a"))
                raise SharePointError(
                    "document storage authentication failed"
                ) from e
            self._token = body["access_token"]
            self._token_expires_at = now + int(body.get("expires_in", 3600))
            return self._token

    # -- request helper ---------------------------------------------------- #
    def _request(
        self,
        method: str,
        url: str,
        *,
        headers: Optional[dict] = None,
        json_body: Optional[dict] = None,
        content: Optional[bytes] = None,
        stream: bool = False,
        retried: bool = False,
    ) -> httpx.Response:
        token = self._get_access_token()
        hdrs = {"Authorization": f"Bearer {token}"}
        if headers:
            hdrs.update(headers)
        try:
            if stream:
                # Caller is responsible for closing.
                client = httpx.Client(timeout=60.0)
                req = client.build_request(
                    method, url, headers=hdrs, json=json_body, content=content,
                )
                resp = client.send(req, stream=True)
            else:
                resp = httpx.request(
                    method, url, headers=hdrs, json=json_body,
                    content=content, timeout=60.0,
                )
        except httpx.HTTPError as e:
            log.error("sharepoint_request_failed method=%s", method)
            raise SharePointError("document storage unavailable") from e

        if resp.status_code in (429, 503) and not retried:
            retry_after = int(resp.headers.get("Retry-After", "1"))
            time.sleep(min(retry_after, 10))
            return self._request(
                method, url, headers=headers, json_body=json_body,
                content=content, stream=stream, retried=True,
            )
        if resp.status_code >= 400:
            log.error("sharepoint_graph_error status=%s method=%s",
                      resp.status_code, method)
            raise SharePointError("document storage unavailable")
        return resp

    # -- resolve site + drive --------------------------------------------- #
    def _resolve_site_id(self) -> str:
        if self._site_id_cache:
            return self._site_id_cache
        # site_url e.g. https://contoso.sharepoint.com/sites/SYHub
        from urllib.parse import urlparse
        p = urlparse(self._site_url)
        if not p.netloc or not p.path:
            raise SharePointConfigError("invalid SHAREPOINT_SITE_URL")
        url = f"{self._GRAPH_BASE}/sites/{p.netloc}:{p.path}"
        resp = self._request("GET", url)
        self._site_id_cache = resp.json()["id"]
        return self._site_id_cache

    def _resolve_drive_id(self) -> str:
        if self._drive_id_cache:
            return self._drive_id_cache
        site_id = self._resolve_site_id()
        resp = self._request("GET", f"{self._GRAPH_BASE}/sites/{site_id}/drives")
        for d in resp.json().get("value", []):
            if d.get("name") == self._drive_name:
                self._drive_id_cache = d["id"]
                return self._drive_id_cache
        raise SharePointConfigError(
            f"drive {self._drive_name!r} not found on site"
        )

    # -- DocumentStore API ------------------------------------------------- #
    def ensure_folder(self, folder_path: str) -> str:
        drive_id = self._resolve_drive_id()
        # Resolve/create each segment under root_folder, idempotent.
        segments = [self._root_folder] + [
            s for s in folder_path.split("/") if s
        ]
        parent = "root"
        for seg in segments:
            if parent == "root":
                lookup = f"{self._GRAPH_BASE}/drives/{drive_id}/root:/{quote(seg)}"
                create_parent = f"{self._GRAPH_BASE}/drives/{drive_id}/root/children"
            else:
                lookup = (
                    f"{self._GRAPH_BASE}/drives/{drive_id}/items/{parent}:"
                    f"/{quote(seg)}"
                )
                create_parent = (
                    f"{self._GRAPH_BASE}/drives/{drive_id}/items/{parent}/children"
                )
            try:
                resp = self._request("GET", lookup)
                parent = resp.json()["id"]
            except SharePointError:
                resp = self._request(
                    "POST", create_parent,
                    json_body={
                        "name": seg, "folder": {},
                        "@microsoft.graph.conflictBehavior": "replace",
                    },
                )
                parent = resp.json()["id"]
        return parent

    def upload(
        self,
        folder_path: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> StoredObjectRef:
        if len(content) > self._max_bytes:
            raise SharePointError("file exceeds maximum upload size")
        safe = _safe_filename(filename)
        parent_id = self.ensure_folder(folder_path)
        drive_id = self._resolve_drive_id()

        if len(content) <= self._SIMPLE_PUT_MAX:
            url = (
                f"{self._GRAPH_BASE}/drives/{drive_id}/items/"
                f"{parent_id}:/{quote(safe)}:/content"
            )
            resp = self._request(
                "PUT", url,
                headers={"Content-Type": content_type},
                content=content,
            )
            item = resp.json()
        else:
            # Upload session for files > 4 MB.
            session_url = (
                f"{self._GRAPH_BASE}/drives/{drive_id}/items/"
                f"{parent_id}:/{quote(safe)}:/createUploadSession"
            )
            resp = self._request(
                "POST", session_url,
                json_body={
                    "item": {
                        "@microsoft.graph.conflictBehavior": "replace",
                        "name": safe,
                    }
                },
            )
            upload_url = resp.json()["uploadUrl"]
            item = self._chunked_put(upload_url, content, content_type)
        return StoredObjectRef(
            item_id=item["id"],
            drive_id=drive_id,
            web_url=item.get("webUrl", ""),
            name=item.get("name", safe),
            size=int(item.get("size", len(content))),
            content_type=content_type,
        )

    def _chunked_put(
        self, upload_url: str, content: bytes, content_type: str,
    ) -> dict:
        total = len(content)
        offset = 0
        last: Optional[dict] = None
        while offset < total:
            end = min(offset + self._CHUNK_SIZE, total) - 1
            chunk = content[offset:end + 1]
            # upload_url is a pre-authed Graph session URL: do NOT add bearer.
            try:
                r = httpx.put(
                    upload_url,
                    headers={
                        "Content-Length": str(len(chunk)),
                        "Content-Range": f"bytes {offset}-{end}/{total}",
                        "Content-Type": content_type,
                    },
                    content=chunk,
                    timeout=120.0,
                )
            except httpx.HTTPError as e:
                raise SharePointError(
                    "document storage unavailable"
                ) from e
            if r.status_code >= 400:
                raise SharePointError("document storage unavailable")
            if r.status_code in (200, 201):
                last = r.json()
            offset = end + 1
        if last is None:
            raise SharePointError("document storage unavailable")
        return last

    def download(self, ref_json: str) -> Tuple[bytes, str, str]:
        ref = StoredObjectRef.from_json(ref_json)
        url = (
            f"{self._GRAPH_BASE}/drives/{ref.drive_id}/items/"
            f"{ref.item_id}/content"
        )
        # Streamed — the underlying Graph redirect URL never leaves here.
        resp = self._request("GET", url, stream=True)
        try:
            content = resp.read()
        finally:
            resp.close()
        return content, ref.name, ref.content_type

    def delete(self, ref_json: str) -> None:
        # Idempotent: bad ref / 404 must not raise.
        try:
            ref = StoredObjectRef.from_json(ref_json)
        except SharePointError:
            return
        url = (
            f"{self._GRAPH_BASE}/drives/{ref.drive_id}/items/{ref.item_id}"
        )
        try:
            token = self._get_access_token()
            resp = httpx.delete(
                url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )
        except httpx.HTTPError as e:
            raise SharePointError("document storage unavailable") from e
        if resp.status_code in (200, 202, 204, 404):
            return
        raise SharePointError("document storage unavailable")

    # -- operator-run grant (called only by smoke-test §R6) --------------- #
    def grant_site_access(self) -> None:
        """One-time Sites.Selected grant for this app.

        Called only by the operator-run smoke-test script with --grant.
        NOT part of normal request flow.
        """
        site_id = self._resolve_site_id()
        url = f"{self._GRAPH_BASE}/sites/{site_id}/permissions"
        self._request(
            "POST", url,
            json_body={
                "roles": ["write"],
                "grantedToIdentities": [
                    {"application": {"id": self._client_id}}
                ],
            },
        )


# --------------------------------------------------------------------------- #
# Factory — picks Stub or Graph based on SHAREPOINT_MODE
# --------------------------------------------------------------------------- #
# Process-wide singleton of the stub so the same in-memory state is shared
# across requests in tests (mirrors how a real Graph store would be shared).
_STUB_SINGLETON: Optional[StubDocumentStore] = None
_STUB_LOCK = threading.Lock()


def _get_stub_singleton() -> StubDocumentStore:
    global _STUB_SINGLETON
    with _STUB_LOCK:
        if _STUB_SINGLETON is None:
            _STUB_SINGLETON = StubDocumentStore()
        return _STUB_SINGLETON


def reset_stub_store() -> None:
    """Test helper — clear the stub singleton between tests."""
    global _STUB_SINGLETON
    with _STUB_LOCK:
        if _STUB_SINGLETON is not None:
            _STUB_SINGLETON.reset()


def get_document_store(settings=None) -> DocumentStore:
    """Return the configured DocumentStore.

    SHAREPOINT_MODE='test-stub' (default) -> StubDocumentStore (shared singleton).
    SHAREPOINT_MODE='live' -> GraphDocumentStore (fail-loud on blank creds).
    """
    s = settings or get_settings()
    if s.is_sharepoint_stub:
        return _get_stub_singleton()
    return GraphDocumentStore(s)
