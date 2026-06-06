# Gate 3 VERIFY — Build Pack 2.7-BE-rev-B (SharePoint via Microsoft Graph)

Date: 2026-02 (rev-B Gate 3 / pack close)
Scope: §R6 (operator-run smoke-test script) + closing docs.
Pack closes here. Operator runs the script once Azure admin consent +
`Sites.Selected` site grant are in place.

---

## A) Smoke-test script — stub-mode refusal (live-only guard)

Command (with default `SHAREPOINT_MODE` unset / 'test-stub'):

    $ cd backend
    $ python scripts/sharepoint_smoke_test.py
    === SharePoint smoke test — resolved configuration ===
      mode         : test-stub
      tenant_id    : <empty>
      client_id    : <empty>
      client_secret: <UNSET>  (value never printed)
      site_url     :
      drive_name   : Documents
      root_folder  : SY-Hub
      max_bytes    : 26214400

    REFUSED: this script is operator-run live verification.
      SHAREPOINT_MODE is currently 'test-stub' (stub).
      Stub-mode coverage is the automated unit suite:
        pytest tests/test_sharepoint_client.py
        pytest tests/test_supplier_document_files.py

      To run live: export SHAREPOINT_MODE=live and provide
      SHAREPOINT_TENANT_ID / CLIENT_ID / CLIENT_SECRET / SITE_URL,
      then re-run this script.

    EXIT=2

The script refuses to run in stub mode and exits with **code 2**.

---

## B) Smoke-test script — live mode with blank creds (fail-loud)

Command (SHAREPOINT_MODE=live, all four required vars blank):

    $ SHAREPOINT_MODE=live SHAREPOINT_TENANT_ID="" SHAREPOINT_CLIENT_ID="" \
      SHAREPOINT_CLIENT_SECRET="" SHAREPOINT_SITE_URL="" \
      python scripts/sharepoint_smoke_test.py
    === SharePoint smoke test — resolved configuration ===
      mode         : live
      tenant_id    : <empty>
      client_id    : <empty>
      client_secret: <UNSET>  (value never printed)
      site_url     :
      drive_name   : Documents
      root_folder  : SY-Hub
      max_bytes    : 26214400

    REFUSED: missing required SharePoint env vars: SHAREPOINT_TENANT_ID,
    SHAREPOINT_CLIENT_ID, SHAREPOINT_CLIENT_SECRET, SHAREPOINT_SITE_URL

    EXIT=2

The script names every missing env var; refuses to construct the Graph
client; exits with **code 2**.

---

## C) Smoke-test script — secret value never printed

Command (SHAREPOINT_MODE=live with a deliberately-marked secret):

    $ SHAREPOINT_MODE=live SHAREPOINT_TENANT_ID="aaaa-tenant-id" \
      SHAREPOINT_CLIENT_ID="bbbb-client-id" \
      SHAREPOINT_CLIENT_SECRET="THIS_SECRET_VALUE_MUST_NEVER_PRINT_xy321" \
      SHAREPOINT_SITE_URL="" \
      python scripts/sharepoint_smoke_test.py
    === SharePoint smoke test — resolved configuration ===
      mode         : live
      tenant_id    : aaaa…(redacted)
      client_id    : bbbb…(redacted)
      client_secret: <set>  (value never printed)
      site_url     :
      drive_name   : Documents
      root_folder  : SY-Hub
      max_bytes    : 26214400

    REFUSED: missing required SharePoint env vars: SHAREPOINT_SITE_URL

Grep the captured stdout/stderr for the marker:

    $ grep -c 'THIS_SECRET_VALUE_MUST_NEVER_PRINT_xy321' /tmp/smoke_live.log
    0

The marker appears **zero** times. The script:
- truncates `tenant_id` / `client_id` to the first 4 chars before
  printing,
- never reads `client_secret` into any print path (only its `bool()`
  presence),
- in error-mapping paths uses the SharePointError's own message
  (which never contains tokens or response bodies per Gate 1 contract),
- redacts `item_id` to 6 chars in the post-upload success line.

---

## D) Smoke-test script — argparse contract

    $ python scripts/sharepoint_smoke_test.py --help
    usage: sharepoint_smoke_test.py [-h] [--grant] [-v]

    SharePoint smoke test (operator-run, live mode only). Refuses to run in
    SHAREPOINT_MODE='test-stub'.

    options:
      -h, --help     show this help message and exit
      --grant        Before the round-trip, perform the Sites.Selected
                     site-grant for this app. Required ONCE per app/site,
                     by an operator who holds tenant-admin rights for the
                     resource. Idempotent: re-running is safe.
      -v, --verbose  Enable DEBUG logging (still redacts secrets).

`--grant` flag exposed; help text matches §R6 contract.

---

## E) Closing-docs file list — Gate 3 touched

    backend/scripts/sharepoint_smoke_test.py        (new)
    CHANGELOG.md                                    (+Gate 3 closing block)
    docs/chat-summaries/chat-41-closing.md          (APPENDED — earlier rev-A close preserved)
    memory/PRD.md                                   (+Gate 3 status)
    memory/Gate3_VERIFY_2.7-BE-rev-B.md             (this file)

NOT touched:

    docs/SY_Hub_Phase2_Backlog.md                   (operator-owned — confirmed)

Two backlog items captured via the closing doc only, NOT written into
the backlog file:
- **B76** — Frontend document upload control (drag-drop on the
  Documents tab, wired to `POST/GET /{id}/file`). Separate FE prompt.
- **B77** — Multi-site document routing (Track 5): per-document-type
  target sites, external sharing for drawings, reusing the rev-B
  `DocumentStore` engine.

---

## F) Final pack state confirmation

### Alembic head

    $ cd backend && alembic current
    INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
    INFO  [alembic.runtime.migration] Will assume transactional DDL.
    0042_file_ref_text (head)

### Permission count

    $ psql -c "SELECT count(*) AS perm_count FROM permissions;"
     perm_count
    ------------
            132
    (1 row)

Unchanged across the entire rev-B pack (Gate 1 → Gate 2 → Gate 3).

### Test surface — final double-run (stub mode, zero Azure dep)

    $ cd backend && python -m pytest \
        tests/test_sharepoint_client.py \
        tests/test_supplier_documents.py \
        tests/test_supplier_document_files.py

    Run 1: 25 + 12 + 20 = 57 passed
    Run 2: 25 + 12 + 20 = 57 passed

### Build flag

No live Microsoft Graph call was made during the build. Live
verification is the operator's job via this Gate 3 script.

---

## PACK CLOSED at Gate 3 per §R7. Awaiting Save to GitHub before raw-fetch verification.
