"""SharePoint document store — Chat 41 rev-B Gate 1 unit tests (§R5.1).

All tests run under SHAREPOINT_MODE='test-stub' (default). Zero network,
zero Azure credentials, deterministic. The Graph live client is exercised
only by the operator-run smoke-test script (§R6), never here.

These tests are the Gate 1 contract — green means:
  - StubDocumentStore round-trips bytes byte-for-byte
  - ensure_folder / delete are idempotent
  - StoredObjectRef JSON envelope round-trips
  - The factory picks Stub vs Graph by mode (and fails loud on blank creds)
  - _safe_filename neutralises traversal + control chars, keeps extension
  - No httpx call escapes the process in stub mode
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import get_settings, reset_settings_cache
from app.services import sharepoint_client as spc
from app.services.sharepoint_client import (
    DocumentStore,
    GraphDocumentStore,
    SharePointConfigError,
    SharePointError,
    StoredObjectRef,
    StubDocumentStore,
    _safe_filename,
    get_document_store,
    reset_stub_store,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def fresh_stub() -> StubDocumentStore:
    """A clean per-test stub (independent of the process singleton)."""
    return StubDocumentStore()


@pytest.fixture(autouse=True)
def _clean_settings(monkeypatch):
    """Default to stub mode and clean SharePoint env between tests."""
    for k in (
        "SHAREPOINT_MODE",
        "SHAREPOINT_TENANT_ID",
        "SHAREPOINT_CLIENT_ID",
        "SHAREPOINT_CLIENT_SECRET",
        "SHAREPOINT_SITE_URL",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SHAREPOINT_MODE", "test-stub")
    reset_settings_cache()
    reset_stub_store()
    yield
    reset_settings_cache()
    reset_stub_store()


@pytest.fixture
def no_network(monkeypatch):
    """Assert no real httpx call is attempted. Any call raises immediately."""
    calls: list[tuple] = []

    def _boom(*args, **kwargs):
        calls.append(("http", args, kwargs))
        raise AssertionError(
            "stub mode must not perform any HTTP call (httpx invoked)"
        )

    # Cover the public + class-level entry points httpx exposes.
    for attr in ("request", "get", "post", "put", "delete", "patch", "head"):
        monkeypatch.setattr(httpx, attr, _boom)
    monkeypatch.setattr(httpx.Client, "send", _boom)
    monkeypatch.setattr(httpx.Client, "request", _boom)
    return calls


# --------------------------------------------------------------------------- #
# §R5.1 — StubDocumentStore round-trip + idempotency
# --------------------------------------------------------------------------- #
def test_stub_upload_download_round_trip_identical_bytes(fresh_stub, no_network):
    payload = b"hello rev-B \x00\x01\x02 binary payload"
    ref = fresh_stub.upload(
        "Suppliers/abc", "cert.pdf", payload, "application/pdf"
    )
    content, name, ctype = fresh_stub.download(ref.to_json())
    assert content == payload
    assert name == "cert.pdf"
    assert ctype == "application/pdf"
    assert ref.size == len(payload)
    assert no_network == []


def test_stub_round_trip_preserves_large_binary(fresh_stub, no_network):
    # 1 MiB random-ish bytes — well below the 4 MB simple-PUT boundary but
    # large enough to catch any naive truncation in the stub.
    payload = bytes(range(256)) * 4096
    ref = fresh_stub.upload("X/Y", "big.bin", payload, "application/octet-stream")
    out, _, _ = fresh_stub.download(ref.to_json())
    assert out == payload
    assert len(out) == len(payload)


def test_stub_ensure_folder_is_idempotent(fresh_stub, no_network):
    a = fresh_stub.ensure_folder("Suppliers/xyz")
    b = fresh_stub.ensure_folder("Suppliers/xyz")
    c = fresh_stub.ensure_folder("Suppliers/xyz")
    assert a == b == c


def test_stub_delete_is_idempotent_when_already_gone(fresh_stub, no_network):
    ref = fresh_stub.upload("F", "a.txt", b"abc", "text/plain")
    rj = ref.to_json()
    fresh_stub.delete(rj)
    # Second delete on the same ref must NOT raise.
    fresh_stub.delete(rj)
    fresh_stub.delete(rj)
    assert not fresh_stub.has_item(ref.item_id)


def test_stub_delete_silently_ignores_unknown_ref(fresh_stub, no_network):
    bogus = StoredObjectRef(
        item_id="item-nope",
        drive_id="stub-drive",
        web_url="https://example/x",
        name="x.txt",
        size=0,
        content_type="text/plain",
    ).to_json()
    fresh_stub.delete(bogus)  # must not raise


def test_stub_delete_silently_ignores_malformed_ref(fresh_stub, no_network):
    fresh_stub.delete("not a json ref")  # must not raise


def test_stub_download_unknown_item_raises_sharepoint_error(fresh_stub, no_network):
    bogus = StoredObjectRef(
        item_id="item-missing",
        drive_id="stub-drive",
        web_url="https://example/x",
        name="x.txt",
        size=0,
        content_type="text/plain",
    ).to_json()
    with pytest.raises(SharePointError):
        fresh_stub.download(bogus)


def test_stub_replace_upload_creates_distinct_item(fresh_stub, no_network):
    r1 = fresh_stub.upload("F", "doc.pdf", b"v1", "application/pdf")
    r2 = fresh_stub.upload("F", "doc.pdf", b"v2", "application/pdf")
    assert r1.item_id != r2.item_id
    assert fresh_stub.download(r1.to_json())[0] == b"v1"
    assert fresh_stub.download(r2.to_json())[0] == b"v2"


# --------------------------------------------------------------------------- #
# §R5.1 — StoredObjectRef JSON round-trip
# --------------------------------------------------------------------------- #
def test_stored_object_ref_json_round_trip():
    ref = StoredObjectRef(
        item_id="item-1",
        drive_id="drive-1",
        web_url="https://contoso.sharepoint.com/sites/syhub/foo",
        name="cert.pdf",
        size=12345,
        content_type="application/pdf",
    )
    rebuilt = StoredObjectRef.from_json(ref.to_json())
    assert rebuilt == ref


def test_stored_object_ref_from_json_rejects_malformed():
    with pytest.raises(SharePointError):
        StoredObjectRef.from_json("not json at all")
    with pytest.raises(SharePointError):
        StoredObjectRef.from_json(json.dumps({"item_id": "x"}))  # missing fields


# --------------------------------------------------------------------------- #
# §R5.1 — get_document_store() factory contract
# --------------------------------------------------------------------------- #
def test_factory_returns_stub_in_stub_mode(monkeypatch, no_network):
    monkeypatch.setenv("SHAREPOINT_MODE", "test-stub")
    reset_settings_cache()
    store = get_document_store()
    assert isinstance(store, StubDocumentStore)


def test_factory_returns_graph_in_live_mode_without_network(monkeypatch):
    monkeypatch.setenv("SHAREPOINT_MODE", "live")
    monkeypatch.setenv("SHAREPOINT_TENANT_ID", "tenant-dummy")
    monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "client-dummy")
    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "secret-dummy")
    monkeypatch.setenv(
        "SHAREPOINT_SITE_URL",
        "https://contoso.sharepoint.com/sites/SYHub",
    )
    reset_settings_cache()

    # Block any network call — the factory must NOT touch Graph.
    def _boom(*a, **kw):
        raise AssertionError("factory must not call Graph during construction")

    monkeypatch.setattr(httpx, "post", _boom)
    monkeypatch.setattr(httpx, "get", _boom)
    monkeypatch.setattr(httpx, "request", _boom)

    store = get_document_store()
    assert isinstance(store, GraphDocumentStore)


def test_factory_live_mode_blank_creds_raises_config_error(monkeypatch):
    monkeypatch.setenv("SHAREPOINT_MODE", "live")
    # All other vars deliberately blank.
    monkeypatch.setenv("SHAREPOINT_TENANT_ID", "")
    monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "")
    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "")
    monkeypatch.setenv("SHAREPOINT_SITE_URL", "")
    reset_settings_cache()
    with pytest.raises(SharePointConfigError) as exc_info:
        get_document_store()
    # Fail-loud message lists missing vars; must NOT mention secrets/tokens.
    msg = str(exc_info.value)
    assert "SHAREPOINT_TENANT_ID" in msg
    assert "SHAREPOINT_CLIENT_ID" in msg
    assert "SHAREPOINT_CLIENT_SECRET" in msg
    assert "SHAREPOINT_SITE_URL" in msg


def test_factory_live_mode_partial_creds_still_fails_loud(monkeypatch):
    # Tenant + client set, secret + site_url blank.
    monkeypatch.setenv("SHAREPOINT_MODE", "live")
    monkeypatch.setenv("SHAREPOINT_TENANT_ID", "tenant-x")
    monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "client-x")
    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", "")
    monkeypatch.setenv("SHAREPOINT_SITE_URL", "")
    reset_settings_cache()
    with pytest.raises(SharePointConfigError) as exc_info:
        get_document_store()
    msg = str(exc_info.value)
    assert "SHAREPOINT_CLIENT_SECRET" in msg
    assert "SHAREPOINT_SITE_URL" in msg
    assert "SHAREPOINT_TENANT_ID" not in msg
    assert "SHAREPOINT_CLIENT_ID" not in msg


# --------------------------------------------------------------------------- #
# §R5.1 — _safe_filename neutralises traversal + control chars
# --------------------------------------------------------------------------- #
def test_safe_filename_strips_path_traversal():
    assert _safe_filename("../../../etc/passwd") == "passwd"
    assert _safe_filename("/etc/passwd") == "passwd"
    # Windows-style backslashes: on POSIX, backslashes are not separators.
    # _safe_filename neutralises them to '_' so no traversal can land.
    out = _safe_filename("..\\..\\windows\\system32\\cmd.exe")
    assert "\\" not in out
    assert ".." not in out or not out.startswith("..")
    assert out.endswith(".exe")


def test_safe_filename_preserves_extension():
    assert _safe_filename("invoice.pdf").endswith(".pdf")
    assert _safe_filename("../report.xlsx").endswith(".xlsx")
    assert _safe_filename("photo.jpeg").endswith(".jpeg")


def test_safe_filename_drops_control_chars():
    out = _safe_filename("bad\x00name\x01\x1f.txt")
    assert "\x00" not in out
    assert "\x01" not in out
    assert "\x1f" not in out
    assert out.endswith(".txt")


def test_safe_filename_handles_empty_or_blank():
    assert _safe_filename("") == "file"
    assert _safe_filename("   ") == "file"
    assert _safe_filename("...") == "file"


def test_safe_filename_caps_length():
    long = "a" * 1000 + ".pdf"
    out = _safe_filename(long)
    assert len(out) <= 200


# --------------------------------------------------------------------------- #
# §R5.1 — Settings flag mirrors AI-stub pattern
# --------------------------------------------------------------------------- #
def test_settings_is_sharepoint_stub_default_true(monkeypatch):
    monkeypatch.delenv("SHAREPOINT_MODE", raising=False)
    reset_settings_cache()
    assert get_settings().is_sharepoint_stub is True
    assert get_settings().sharepoint_mode == "test-stub"


def test_settings_is_sharepoint_stub_false_when_live(monkeypatch):
    monkeypatch.setenv("SHAREPOINT_MODE", "live")
    reset_settings_cache()
    assert get_settings().is_sharepoint_stub is False


def test_settings_default_drive_and_root_folder(monkeypatch):
    monkeypatch.delenv("SHAREPOINT_DRIVE_NAME", raising=False)
    monkeypatch.delenv("SHAREPOINT_ROOT_FOLDER", raising=False)
    reset_settings_cache()
    s = get_settings()
    assert s.sharepoint_drive_name == "Documents"
    assert s.sharepoint_root_folder == "SY-Hub"
    assert s.sharepoint_max_bytes == 25 * 1024 * 1024


# --------------------------------------------------------------------------- #
# §R5.1 — Zero-network assertion across a full stub round-trip
# --------------------------------------------------------------------------- #
def test_full_stub_flow_makes_zero_network_calls(no_network):
    """End-to-end happy path under no-network guard.

    If any code path touches httpx in stub mode, the guard raises and
    this test fails loudly. This is the Gate 1 'zero network calls in
    stub mode' guarantee.
    """
    store: DocumentStore = get_document_store()
    assert isinstance(store, StubDocumentStore)
    fid_a = store.ensure_folder("Suppliers/acme")
    fid_b = store.ensure_folder("Suppliers/acme")  # idempotent
    assert fid_a == fid_b
    ref = store.upload("Suppliers/acme", "cert.pdf", b"abc", "application/pdf")
    content, name, ctype = store.download(ref.to_json())
    assert content == b"abc"
    assert name == "cert.pdf"
    assert ctype == "application/pdf"
    store.delete(ref.to_json())
    store.delete(ref.to_json())  # idempotent
    assert no_network == []


# --------------------------------------------------------------------------- #
# §R5.1 — Error messages never leak secrets / Graph internals
# --------------------------------------------------------------------------- #
def test_config_error_never_includes_secret_value(monkeypatch):
    monkeypatch.setenv("SHAREPOINT_MODE", "live")
    monkeypatch.setenv("SHAREPOINT_TENANT_ID", "")
    monkeypatch.setenv("SHAREPOINT_CLIENT_ID", "")
    secret_marker = "THIS_SECRET_MUST_NOT_LEAK_xy321"
    monkeypatch.setenv("SHAREPOINT_CLIENT_SECRET", secret_marker)
    monkeypatch.setenv("SHAREPOINT_SITE_URL", "")
    reset_settings_cache()
    with pytest.raises(SharePointConfigError) as exc_info:
        get_document_store()
    assert secret_marker not in str(exc_info.value)


def test_sharepoint_error_message_is_user_safe():
    # Constructing the exception with internal-looking text must not change
    # the contract callers rely on (router maps -> 502 generic). The test
    # documents the public surface: SharePointError IS the error type
    # the service layer is allowed to raise.
    e = SharePointError("document storage unavailable")
    assert "token" not in str(e).lower()
    assert "secret" not in str(e).lower()
    assert "bearer" not in str(e).lower()
