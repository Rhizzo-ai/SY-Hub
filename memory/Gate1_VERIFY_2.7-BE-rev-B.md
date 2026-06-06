# Gate 1 VERIFY — Build Pack 2.7-BE-rev-B (SharePoint via Microsoft Graph)

Date: 2026-02 (rev-B Gate 1)
Scope: §R1 (config) + §R2 (Graph client + stub) + §R5.0 (migration 0042).
Stopped at Gate 1 per §R7 — §R3/§R4/§R6 deferred to Gates 2 and 3.

---

## A) Stub-store unit tests — green, double-run

Command:
    cd backend && python -m pytest tests/test_sharepoint_client.py -v

Run 1 result:    **25 passed in 0.09s**
Run 2 result:    **25 passed in 0.09s**

Test breakdown (25 tests):

  StubDocumentStore round-trip + idempotency (8)
    test_stub_upload_download_round_trip_identical_bytes
    test_stub_round_trip_preserves_large_binary
    test_stub_ensure_folder_is_idempotent
    test_stub_delete_is_idempotent_when_already_gone
    test_stub_delete_silently_ignores_unknown_ref
    test_stub_delete_silently_ignores_malformed_ref
    test_stub_download_unknown_item_raises_sharepoint_error
    test_stub_replace_upload_creates_distinct_item

  StoredObjectRef JSON envelope (2)
    test_stored_object_ref_json_round_trip
    test_stored_object_ref_from_json_rejects_malformed

  get_document_store() factory (4)
    test_factory_returns_stub_in_stub_mode
    test_factory_returns_graph_in_live_mode_without_network
    test_factory_live_mode_blank_creds_raises_config_error
    test_factory_live_mode_partial_creds_still_fails_loud

  _safe_filename hardening (5)
    test_safe_filename_strips_path_traversal
    test_safe_filename_preserves_extension
    test_safe_filename_drops_control_chars
    test_safe_filename_handles_empty_or_blank
    test_safe_filename_caps_length

  Settings property mirror of AI-stub pattern (3)
    test_settings_is_sharepoint_stub_default_true
    test_settings_is_sharepoint_stub_false_when_live
    test_settings_default_drive_and_root_folder

  Zero-network + leak guards (3)
    test_full_stub_flow_makes_zero_network_calls
    test_config_error_never_includes_secret_value
    test_sharepoint_error_message_is_user_safe

---

## B) Migration 0042_file_ref_text — head + round-trip

`alembic current` after upgrade head:

    INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
    INFO  [alembic.runtime.migration] Will assume transactional DDL.
    0042_file_ref_text (head)

Column type via `information_schema.columns`:

    column_name | data_type | character_maximum_length
    ------------+-----------+--------------------------
    file_ref    | text      |

Round-trip up → down → up:

    upgrade  0041 → 0042 : Running upgrade 0041_drop_vat_registered -> 0042_file_ref_text
    downgrade 0042 → 0041 : Running downgrade 0042_file_ref_text -> 0041_drop_vat_registered
        column_name | data_type         | character_maximum_length
        ------------+-------------------+--------------------------
        file_ref    | character varying |                      500
    upgrade  0041 → 0042 (back to head)
        column_name | data_type | character_maximum_length
        ------------+-----------+--------------------------
        file_ref    | text      |

Symmetrical. ✅

---

## C) Live-mode fail-loud — `SharePointConfigError` test

`test_factory_live_mode_blank_creds_raises_config_error` and
`test_factory_live_mode_partial_creds_still_fails_loud` both green:

    tests/test_sharepoint_client.py ..                                       [100%]
    ============================== 2 passed in 0.08s ===============================

Asserts:
- All 4 required env vars listed by name in the exception message when
  all four are blank.
- Only the missing subset listed when partial creds are present
  (tenant + client set; secret + site_url blank).
- The secret VALUE (`THIS_SECRET_MUST_NOT_LEAK_xy321`) is **not**
  present in the raised exception text — fail-loud names the env var,
  never the value.

---

## D) Zero network calls in stub mode

`test_full_stub_flow_makes_zero_network_calls` is green under a
process-wide `httpx` monkeypatch that raises on:

    httpx.request / .get / .post / .put / .delete / .patch / .head
    httpx.Client.send / .request

Result:

    tests/test_sharepoint_client.py .                                        [100%]
    ============================== 1 passed in 0.08s ===============================

Additional static check — the Stub class body contains zero references
to `httpx`, `requests`, or `urllib.request`:

    StubDocumentStore source contains httpx?         False
    StubDocumentStore source contains requests?      False
    StubDocumentStore source contains urllib.request? False

`msal` / `Office365-REST-Python-Client` are NOT in
`backend/requirements.txt` — confirmed by grep.

---

## E) Files touched at Gate 1

    backend/app/config.py                       (+8 SharePoint settings, +is_sharepoint_stub)
    backend/app/services/sharepoint_client.py   (new — Stub + Graph + factory + helpers)
    backend/alembic/versions/0042_file_ref_text.py  (new migration)
    backend/tests/test_sharepoint_client.py     (new — 25 stub-mode tests)
    CHANGELOG.md                                (rev-B Gate 1 entry)
    memory/Gate1_VERIFY_2.7-BE-rev-B.md         (this file)

Not touched: routers, services for supplier_documents, smoke-test script,
`docs/SY_Hub_Phase2_Backlog.md`.

---

## STOPPED at Gate 1 per §R7. Awaiting operator approval before §R3/§R4 (Gate 2).
