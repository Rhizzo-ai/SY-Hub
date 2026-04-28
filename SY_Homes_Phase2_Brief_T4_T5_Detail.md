<!-- ================================================================
     SY HOMES PLATFORM — PHASE 2 EMERGENT BRIEF
     SESSION 4a OUTPUT: TRACKS 4 + 5 — PROMPT-LEVEL DETAIL
     ================================================================
     Version: 2.0-detail (T4 + T5 only)
     Date: April 2026
     Status: Replaces one-paragraph descriptions in skeleton lines
             ~254-318 (Track 4 prompts 4.1-4.7, Track 5 prompts 5.1-5.3).
             Track 6, 7, 8 detail follows in session 4b (separate chat
             for context budget — opener authorised the split).
     Companion: SY_Homes_Emergent_Brief_Phase1.md (Phase 1 brief —
                referenced for "carried forward" Track 5 prompts);
                SY_Homes_Phase2_Brief_T2_T3_Detail.md (session 3 —
                referenced for portal patterns and infra hooks).
     ================================================================ -->

# Session 4a — Tracks 4 and 5 prompt-level detail

This document supplies the full prompt detail for Tracks 4 and 5, intended to replace the one-paragraph descriptions in `SY_Homes_Emergent_Brief_Phase2.md` skeleton sections "Track 4 — Site Operations" and "Track 5 — Documents & Compliance". Same depth and structure as session 3's T2+T3 detail.

## Changes versus skeleton

1. **Prompt 4.6 stays as one prompt.** Skeleton flagged it as a candidate split (snag + activity streams). On detail review, snagging is the substantial half (three tables, status workflow with severity/sign-off/photo evidence, links to QA failures and DLP defects). Activity streams is a thin feed-rendering surface on a single generic `activity_events` table that every other module already writes into via the audit hook from 1.4 — 4.6 just builds the read side. No clear seam; splitting would produce a 2h activity-streams prompt that is mostly view code. Remains one prompt at 10h.
2. **Chat (4.3) acceptance criteria do not include WhatsApp displacement.** The brief calls for chat that is good enough that the team chooses it over WhatsApp for project comms. Whether they actually do so is operational and measured post-launch, not at prompt acceptance. This is flagged explicitly in 4.3 below so the prompt isn't held against an unmet adoption metric.
3. **Labourer portal (4.7) reuses portal infrastructure from 2.9.** No new tables; the `is_portal_user` flag, invitation flow, session policy, rate limit, and field allowlist pattern from 2.9 extend with `portal_user_type='Labourer'` and a third seeded portal role.
4. **Track 5 carried forward unchanged in shape from Phase 1 Track 4.** Phase 1 already specified the document store, approvals, access log, compliance registers, and certificate machinery at full depth. Phase 2 deltas are: (a) mobile-friendly upload flows, (b) new document-link foreign keys onto Phase 2 records (subcontracts from 2.8a, valuations from 2.8b, supplier_documents from 2.7, daily_log_photos / qa_photos / snag_photos from T4 — though those photos are stored as their own first-class tables, not as documents), (c) wiring 5.1 document_types into 4.5 QA evidence and 4.4 RFI attachments.

## Carried-forward prompts — note on depth

Prompts 5.1, 5.2, 5.3 are carried forward from Phase 1 Track 4 (`SY_Homes_Emergent_Brief_Phase1.md` Prompts 4.1, 4.2, 4.3) with deltas only. Their full schemas, business logic, and acceptance criteria already exist in the Phase 1 brief. Sections below state the Phase 1 reference, the deltas, the new cross-track wiring, and any out-of-scope additions surfaced by Phase 2 scope.

Prompts 4.1 through 4.7 are all new and are written here at full Phase 1 depth.

---

# Track 4 — Site Operations

**Goal:** The on-site experience — what site managers, contractors, and labourers actually do. Mobile-first throughout, offline-capable for the parts that need it, real-time where it matters. This is the track that replaces WhatsApp groups, paper diaries, clipboard QA, and end-of-day phone calls. It is also the track most directly visible to the team that will judge the platform on its merits.

**Duration:** ~14 weeks at 25 hrs/week
**Prompts:** 7
**Tables added:** ~25
**Audit checkpoint (mid-track):** After 4.3 (chat) lands and is in use, bring MD, Louise, the contracts manager, and at least one site manager in for a directional review. This is the "mid T4 with team" review specified in Project Instructions. It is the first time non-Rhys users have substantial hands-on exposure; their feedback shapes 4.4–4.7. Schedule it as a working session, not a demo — give the team accounts, give them a few days to use chat and the daily logs in anger, then debrief.

---

## Prompt 4.1 — Daily Logs

**Dependencies:** 1.5, 3.1, 3.2
**Tables in this prompt:** `daily_logs`, `daily_log_entries`, `daily_log_photos`, `daily_log_weather_snapshots`
**Estimated hours:** 10h
**Status:** NEW.

The site diary. One log per project per date, structured into entry types (weather, attendance, work completed, deliveries, issues, delays, visitors, photos), submitted at end of day by the site manager. Designed for three-minute entry on a phone. Offline-capable (sync via 3.2). Searchable, exportable to PDF for monthly reports.

This module replaces the paper diary and the "I'll WhatsApp the photos to the office" workflow that currently lives outside any system.

### Build `daily_logs`

Header per project per date. One row per project per day. Created on first entry; locked once submitted; reopenable by site manager or director with reason logged.

```
daily_logs
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
log_date                        date NOT NULL
weather_summary                 varchar(255)         -- denormalised from weather_snapshots latest
weather_temp_min_c              decimal(4,1)
weather_temp_max_c              decimal(4,1)
weather_precipitation_mm        decimal(5,2)
weather_wind_max_kmh            decimal(5,1)
weather_source                  enum DEFAULT 'API_OpenWeather'
                                  ('API_OpenWeather','Manual','Site_Station')
attendance_summary              text         -- free-text "12 on site: 4 GW, 6 first fix, 2 site"
total_attendance_count          int
work_completed_summary          text
deliveries_summary              text
issues_summary                  text
delays_summary                  text
visitors_summary                text
notes                           text
status                          enum NOT NULL DEFAULT 'Draft'
                                  ('Draft','Submitted','Reopened','Locked')
submitted_at                    timestamp
submitted_by_user_id            uuid FK→users.id
locked_at                       timestamp
locked_by_user_id               uuid FK→users.id
reopened_at                     timestamp
reopened_by_user_id             uuid FK→users.id
reopen_reason                   text
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (project_id, log_date)
- INDEX (project_id, log_date DESC)
- INDEX (status) WHERE status IN ('Draft','Submitted')
- INDEX (submitted_by_user_id, submitted_at DESC)
```

`UNIQUE (project_id, log_date)` is critical — one log per project per day. Attempts to create a second row for the same project/date upsert into the existing row.

### Build `daily_log_entries`

Sub-entries within a log. Allows multiple entries of the same type (e.g. three deliveries received at different times) without bloating the header. Free-form by `entry_type` because the bar is "fast on a phone" not "structured data we'll mine".

```
daily_log_entries
─────────────────────────────────────────────
id                              uuid PK
daily_log_id                    uuid NOT NULL FK→daily_logs.id ON DELETE CASCADE
entry_type                      enum NOT NULL
                                  ('Weather_Note','Attendance','Work_Completed','Delivery_Received',
                                   'Issue','Delay','Visitor','Safety_Briefing','Inspection','Other')
content                         text NOT NULL
related_programme_task_id       uuid FK→programme_tasks.id        -- 3.4; for Work_Completed
related_supplier_id             uuid FK→suppliers.id              -- 2.7; for Delivery_Received
related_commitment_id           uuid FK→commitments.id            -- 2.5; for Delivery_Received
event_time                      time                              -- HH:MM, optional
duration_minutes                int                               -- for delays
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
sort_order                      int NOT NULL DEFAULT 100

Indexes:
- INDEX (daily_log_id, entry_type, sort_order)
- INDEX (related_programme_task_id) WHERE related_programme_task_id IS NOT NULL
- INDEX (related_supplier_id) WHERE related_supplier_id IS NOT NULL
- INDEX (entry_type, created_at DESC)
```

Cross-references on entries are optional: a delivery-received entry can be free-text or it can link to the specific PO and supplier for richer reporting. Site managers won't always tag everything; that's accepted.

### Build `daily_log_photos`

Inline photos attached to log entries or to the log header. First-class table, not via the document store (5.2), because: (a) photos at this volume — dozens per log per project per day across 5+ projects — would bloat the document table with low-value records, (b) photo metadata (geotag, timestamp, device) needs first-class storage for evidence purposes, (c) lifecycle differs (photos archive with logs, not as standalone documents).

```
daily_log_photos
─────────────────────────────────────────────
id                              uuid PK
daily_log_id                    uuid NOT NULL FK→daily_logs.id ON DELETE CASCADE
daily_log_entry_id              uuid FK→daily_log_entries.id ON DELETE SET NULL
caption                         varchar(500)
file_storage_backend            enum NOT NULL DEFAULT 'S3'
                                  ('S3','Azure_Blob','GCS','Local')
file_storage_key                text NOT NULL
file_thumbnail_storage_key      text                              -- generated server-side
file_original_name              varchar(500)
file_mime_type                  varchar(50) NOT NULL              -- image/jpeg, image/heic, image/png
file_size_bytes                 bigint NOT NULL
file_width_px                   int
file_height_px                  int
file_sha256                     varchar(64) NOT NULL
exif_taken_at                   timestamp                         -- from EXIF DateTimeOriginal
exif_lat                        decimal(9,6)                      -- from EXIF GPSLatitude
exif_lon                        decimal(9,6)
exif_device_model               varchar(100)
uploaded_via                    enum NOT NULL DEFAULT 'Mobile_Web'
                                  ('Mobile_Web','Mobile_PWA','Desktop_Web','API')
uploaded_by_user_id             uuid NOT NULL FK→users.id
uploaded_at                     timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (daily_log_id, uploaded_at DESC)
- INDEX (daily_log_entry_id) WHERE daily_log_entry_id IS NOT NULL
- INDEX (exif_taken_at)
```

EXIF data is opportunistically extracted server-side on upload using `exifread` or equivalent; absence is fine (older devices, screen-grabs). HEIC support is required (iPhone default format) — server-side conversion to JPEG for thumbnail; original retained.

### Build `daily_log_weather_snapshots`

Audit history of weather pulls. Allows replay if the API returns differently a day later, and supports the offline case (a phone with no signal can record observed weather; the API pull happens on sync).

```
daily_log_weather_snapshots
─────────────────────────────────────────────
id                              uuid PK
daily_log_id                    uuid NOT NULL FK→daily_logs.id ON DELETE CASCADE
fetched_at                      timestamp NOT NULL DEFAULT now()
source                          enum NOT NULL
                                  ('API_OpenWeather','Manual','Site_Station')
raw_response                    jsonb         -- full API payload for replay
summary                         varchar(255)
temp_min_c                      decimal(4,1)
temp_max_c                      decimal(4,1)
precipitation_mm                decimal(5,2)
wind_max_kmh                    decimal(5,1)
humidity_pct                    int
notes                           text

Indexes:
- INDEX (daily_log_id, fetched_at DESC)
```

### Business logic

**Weather fetch on first-touch of the day:**

```
On daily_log creation (first entry of the day):
  IF project.site_lat AND project.site_lon set:
    Async job: fetch from OpenWeather "current + history-for-day" endpoints
    Store full response in daily_log_weather_snapshots
    Denormalise summary fields onto daily_log header
  ELSE:
    Leave weather fields null; site manager fills manually if useful
```

OpenWeather is one of multiple options; `weather_provider` config in 1.7 selects which (default OpenWeather; alternatives Met Office DataPoint API for UK accuracy). Free tier covers expected volume (5 projects × 1 call/day = 150/month, well under free 1,000/month).

**Submission and locking:**

```
Site manager: action "Submit log"
  Pre-flight checks:
    - At least one Work_Completed OR Issue OR Delay entry (not blank)
    - Attendance count > 0 OR explicit zero-attendance reason
  Set status = Submitted, submitted_at, submitted_by_user_id
  Broadcast realtime event channel="project:{id}" type="daily_log.submitted"
  Notify: project lead, contracts manager (digest)

Auto-lock: scheduled job at 06:00 next day for any log still in Submitted state.
  Set status = Locked, locked_at, locked_by_user_id = system user.

Reopen (site manager or director):
  Required: reopen_reason ≥ 10 chars
  Set status = Reopened, reopened_at, reopen_reason logged
  Audit log entry
  After re-submission, status returns to Submitted; auto-lock re-applies.
```

**Cross-reference auto-population:**

When site manager taps "Add work completed":
- Picker shows programme tasks (from 3.4) for this project that are `In_Progress` or have predecessors completed in the last 7 days. Selecting one auto-fills `related_programme_task_id` and pre-fills the content with the task name.
- After save, the programme module's task progress updater (3.5) is *prompted* (not forced) to capture % complete on the task. Task update flows still go through 3.5.

When site manager taps "Add delivery received":
- Picker shows POs (commitments from 2.5) on this project with status `Issued` or `Confirmed` and `expected_delivery_date` within ±14 days of today.
- Selecting one auto-fills `related_supplier_id` and `related_commitment_id`.
- A delivery-received entry can flip the linked commitment line's `delivery_received_at` (small business-logic hook back into 2.5).

**Offline behaviour (uses 3.2 outbox):**

```
Site manager opens daily log on phone with no signal:
  Local IndexedDB cache holds: project list (recent), open programme tasks, recent POs.
  All entry types creatable offline.
  Photos uploaded to local IndexedDB blob store (size cap 100MB per device — older drafts evicted).
  Outbox queues: daily_log row, daily_log_entries rows, daily_log_photos rows + blobs.
  
On reconnect:
  Outbox flushes in order: log → entries → photos.
  Idempotency keys per row prevent duplicate creation if sync retries.
  Photos uploaded one at a time, with progress indicator.
  On photo upload completion, server-side EXIF extraction + thumbnail generation runs async.
  
Conflict (two devices submit same log_date for same project):
  UNIQUE (project_id, log_date) catches at DB.
  Conflict policy from 3.2 — last-write-wins on header, but entries are append-only so both devices' entries merge.
  Loser sees overwrite toast on header fields only.
```

This is one of the modules where offline matters most — site managers often walk site at end of day with intermittent signal.

**PDF export:**

```
Action: "Export logs as PDF"
  Filter: project, date range
  Renders: 
    Cover page (project, date range, generated by, generated at)
    Per day:
      Header (date, weather, attendance count, submitted by/at)
      Each entry section (Work, Deliveries, Issues, Delays, Visitors)
      Photos (4 per page, with captions, EXIF timestamp)
  Engine: WeasyPrint or similar HTML→PDF.
  File generated async (large month exports can be 50MB).
  User receives notification when ready, downloadable from /exports for 7 days.
```

PDF export is the bridge to the monthly progress report SY Homes currently produces in Word. Removing the manual collation is one of the bigger time savings of this module.

**Search:**

Full-text index across `daily_logs.notes`, `daily_log_entries.content`, `daily_log_photos.caption`. Postgres `tsvector` column with weighted ranking (entries: A, header notes: B, captions: C). Search box on `/projects/:id/diary` with type filter and date filter.

### UI

**Site manager mobile flow** — `/projects/:id/diary/today`:
- Big "Today" header with weather card (auto-pulled).
- Quick-add buttons: Photo · Delivery · Issue · Delay · Visitor · Note.
- Swipe each button to launch the right entry sub-form.
- Existing entries listed underneath, latest first, with type icon and snippet.
- Photo entries show 60×60 thumbnail inline.
- Bottom: "Submit log" sticky button (changes colour when ≥1 substantive entry present).

**Quick-add entry sub-forms** are intentionally minimal:
- *Photo:* device camera or photo library; optional caption (focus auto-jumps; caption optional).
- *Delivery:* PO picker (showing supplier name + expected date) → optional notes → save.
- *Issue / Delay:* free text; for delay, optional duration; save.
- *Visitor:* name + reason free text; save.

**Site manager desktop flow** — `/projects/:id/diary`:
- Calendar grid (month view) with status dots per day (green = submitted, amber = draft, grey = nothing).
- Click a day → detail view (entries grouped by type, photo gallery, submit button).
- "Bulk PDF export" with month picker.

**Director / contracts manager view** — `/projects/:id/diary` (read-only by default):
- Same desktop view, no edit affordances.
- "Open log" reveal of any specific day.
- Cross-project digest at `/diary` global: yesterday's logs across all live projects, photo strip, top issues raised.

### Permissions

- `daily_logs.view` — project team (scoped by project_team_members from 1.5), director, finance (read-only)
- `daily_logs.create` — site manager, project lead, contracts manager
- `daily_logs.submit` — site manager, project lead
- `daily_logs.reopen` — site manager (own logs), director (any)
- `daily_logs.export_pdf` — project team
- `daily_log_photos.upload` — site manager, project lead, contracts manager, **labourer (via 4.7 portal — own end-of-day summary only)**

Labourer access is read-restricted: a labourer sees the day's photos and entries via the 4.7 labourer portal end-of-day summary screen, not the full diary. They can add a single end-of-day note/photo through that portal that lands in the daily log as an entry tagged with their user_id.

### Acceptance criteria

- [ ] Daily log can be created on a phone end-to-end (open, add 3 entries with photos, submit) in under 3 minutes on a mid-range Android over 4G
- [ ] One log per project per date — second creation upserts into existing
- [ ] Weather auto-fetches when project has lat/lon; manual entry available when not
- [ ] Photo upload supports HEIC (iPhone) with server-side conversion to JPEG thumbnail
- [ ] EXIF timestamp and GPS extracted opportunistically on upload
- [ ] Programme task picker for Work_Completed entries shows only relevant tasks (in-progress or recently completable)
- [ ] PO picker for Delivery_Received entries shows only POs with expected_delivery_date ±14d
- [ ] Submit requires ≥1 substantive entry (Work / Issue / Delay) plus attendance > 0 or explicit zero
- [ ] Auto-lock at 06:00 next day if still Submitted
- [ ] Reopen requires reason ≥ 10 chars; audit-logged
- [ ] Search returns hits from log notes, entry content, photo captions
- [ ] PDF export of a month renders with all entries and 4-photos-per-page layout
- [ ] Offline flow: open log, add entries with photos on aeroplane mode, restore connection, all entries sync in correct order, no duplicates
- [ ] Realtime broadcast on submit reaches subscribed users via 3.1
- [ ] Mobile UX tested on iOS Safari (iPhone 12+) and Android Chrome (mid-range Android, 4GB RAM)
- [ ] Photo upload size cap of 50MB per photo enforced; client-side resize for >12MP cameras

### Out of scope

- AI-generated daily log summaries from photos / entries — Future Tasks Phase 5 (AI document ingestion sibling).
- Voice-to-text entry — Future Tasks Phase 5 (relies on platform-native speech recognition; iOS/Android handle their own).
- Cross-project diary views beyond a simple yesterday-digest — Phase 7 reporting.
- Automated H&S incident reporting from Issue entries (RIDDOR feed) — Future Tasks Phase 4.
- Site Manager nightly digest email — Phase 3 (digest infrastructure not in scope here).
- Automatic delay-impact analysis (does this delay shift the programme?) — Future Tasks Phase 5; for now, delay entries are advisory and the site manager updates programme tasks separately via 3.5.

---

## Prompt 4.2 — Clocking In/Out and Timesheets

**Dependencies:** 1.2, 1.5, 3.2
**Tables in this prompt:** `clock_events`, `geofences`, `timesheets`, `timesheet_entries`, `clock_corrections`
**Estimated hours:** 10h
**Status:** NEW.

Labourers and contractors clock in at start of shift, clock out at end. Optional geofence verification. Site managers approve weekly timesheets. CSV export to whatever payroll system SY Homes uses (payroll itself out of scope).

This module creates the audit trail HMRC and CIS-eligible subcontractors need, replaces paper sign-in sheets, and produces clean timesheet data with no manual transcription.

### Build `clock_events`

Append-only log of every clock action. Two events form a shift; mismatched events (in without out) are flagged for correction.

```
clock_events
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
user_id                         uuid NOT NULL FK→users.id ON DELETE RESTRICT
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
event_type                      enum NOT NULL ('Clock_In','Clock_Out','Break_Start','Break_End')
event_time                      timestamp NOT NULL                 -- when the action occurred
recorded_at                     timestamp NOT NULL DEFAULT now()  -- when server received it (may differ if offline)
recorded_via                    enum NOT NULL DEFAULT 'Mobile_Web'
                                  ('Mobile_Web','Mobile_PWA','Kiosk','Manual_Entry','API')
device_lat                      decimal(9,6)
device_lon                      decimal(9,6)
device_accuracy_m               decimal(8,2)                       -- HTML5 geolocation accuracy
geofence_id                     uuid FK→geofences.id
geofence_check_result           enum
                                  ('Inside','Outside','Skipped','No_Geofence')
device_info                     jsonb         -- { user_agent, ip, app_version }
notes                           text
is_corrected                    boolean NOT NULL DEFAULT false
corrected_by_clock_correction_id uuid FK→clock_corrections.id
created_by_user_id              uuid NOT NULL FK→users.id          -- = user_id unless Manual_Entry
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (user_id, event_time DESC)
- INDEX (project_id, event_time DESC)
- INDEX (event_time)
- INDEX (geofence_check_result) WHERE geofence_check_result = 'Outside'
```

Note: append-only. Corrections are made via separate `clock_corrections` rows, never by mutating the original event. This satisfies the "never lose financial data" hard constraint extended to operational records that drive payment.

### Build `geofences`

One polygon per project. Optional — projects without a geofence skip the check.

```
geofences
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid NOT NULL UNIQUE FK→projects.id ON DELETE CASCADE
name                            varchar(255) NOT NULL              -- defaults to project name
boundary                        jsonb NOT NULL                     -- GeoJSON Polygon
                                  -- {"type":"Polygon","coordinates":[[[lon,lat],...]]}
buffer_metres                   int NOT NULL DEFAULT 50            -- expansion of polygon for inaccuracy
is_active                       boolean NOT NULL DEFAULT true
enforcement                     enum NOT NULL DEFAULT 'Warn'
                                  ('Off','Warn','Block')
                                  -- Off = log result, no action
                                  -- Warn = log + flag for review
                                  -- Block = clock event rejected
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (project_id) WHERE is_active = true
```

Polygon stored as GeoJSON in JSONB. Postgres has PostGIS for proper geo support but adding PostGIS is heavy for this single use case; haversine + ray-casting in application code is sufficient at this scale (point-in-polygon for ~50 polygons, ~50 events/day each = trivial CPU). PostGIS becomes a Future Tasks ask if geo features expand.

`enforcement = Warn` is the default. `Block` is too aggressive for v1 — GPS in a partly-built warehouse is unreliable; rejecting a clock-in because the phone thought it was 60m off site annoys exactly the people we need to onboard. Site manager reviews `Outside` results weekly during timesheet approval.

### Build `timesheets`

Weekly aggregate per user per project. Not stored as a header in the strict sense — derived from `clock_events` — but materialised because (a) approval status sits at the weekly level, (b) export-to-payroll consumes the weekly view, (c) computing on the fly across thousands of events for an end-of-week run is needlessly expensive.

```
timesheets
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
user_id                         uuid NOT NULL FK→users.id
project_id                      uuid NOT NULL FK→projects.id
week_starting                   date NOT NULL                      -- Monday of the week
week_ending                     date NOT NULL                      -- Sunday
total_hours_worked              decimal(6,2) NOT NULL DEFAULT 0
total_hours_break               decimal(6,2) NOT NULL DEFAULT 0
total_hours_billable            decimal(6,2) NOT NULL DEFAULT 0    -- worked - break
status                          enum NOT NULL DEFAULT 'Open'
                                  ('Open','Submitted','Approved','Rejected','Exported','Locked')
submitted_at                    timestamp
submitted_by_user_id            uuid FK→users.id                   -- usually = user_id
approved_at                     timestamp
approved_by_user_id             uuid FK→users.id                   -- site manager
rejection_reason                text
exported_at                     timestamp
exported_in_batch_id            uuid                               -- for payroll batch tracking
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (user_id, project_id, week_starting)
- INDEX (project_id, week_starting DESC)
- INDEX (status, week_starting DESC)
- INDEX (approved_by_user_id) WHERE status = 'Approved'
```

### Build `timesheet_entries`

Per-day rollup within a timesheet. Computed; rebuildable from clock_events. Materialised for fast view rendering.

```
timesheet_entries
─────────────────────────────────────────────
id                              uuid PK
timesheet_id                    uuid NOT NULL FK→timesheets.id ON DELETE CASCADE
day_date                        date NOT NULL
clock_in_event_id               uuid FK→clock_events.id            -- first clock_in of the day
clock_out_event_id              uuid FK→clock_events.id            -- last clock_out
hours_worked                    decimal(5,2) NOT NULL DEFAULT 0
hours_break                     decimal(5,2) NOT NULL DEFAULT 0
hours_billable                  decimal(5,2) NOT NULL DEFAULT 0
shift_count                     int NOT NULL DEFAULT 0             -- usually 1; can be more
has_geofence_warning            boolean NOT NULL DEFAULT false
has_missing_clockout            boolean NOT NULL DEFAULT false
has_correction                  boolean NOT NULL DEFAULT false
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (timesheet_id, day_date)
- INDEX (day_date)
```

### Build `clock_corrections`

Site manager corrections. Append-only, references the original clock_event being corrected.

```
clock_corrections
─────────────────────────────────────────────
id                              uuid PK
original_clock_event_id         uuid FK→clock_events.id
correction_type                 enum NOT NULL
                                  ('Add_Missing_Event','Adjust_Time','Mark_Invalid','Add_Note')
new_event_id                    uuid FK→clock_events.id            -- if Add_Missing_Event or Adjust_Time
new_event_time                  timestamp                          -- requested time
reason                          text NOT NULL
corrected_by_user_id            uuid NOT NULL FK→users.id          -- site manager
corrected_at                    timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (original_clock_event_id)
- INDEX (corrected_by_user_id, corrected_at DESC)
```

A correction never mutates the original event. `Adjust_Time`: original is marked `is_corrected=true`, a new event is created with the corrected time and a back-pointer. The timesheet_entries computation prefers the corrected event when both exist.

### Business logic

**Clock-in flow (mobile):**

```
Labourer / contractor opens portal → "Clock in" button (project pre-selected based on assignment).
Browser requests geolocation (HTML5 navigator.geolocation).
On location acquired (or denied / timed out after 10s):
  Construct clock_events row:
    user_id = current user
    project_id = active project assignment
    event_type = Clock_In
    event_time = now() (server time after sync; client time stored in notes if offline)
    device_lat / device_lon / device_accuracy_m if available
    recorded_via = 'Mobile_PWA' or 'Mobile_Web'

If project has active geofence:
  Run point-in-polygon check (with buffer_metres expansion):
    If inside: geofence_check_result = 'Inside'
    If outside: geofence_check_result = 'Outside'
      If enforcement = 'Block': reject the clock event with explanation, prompt for manual entry
      If enforcement = 'Warn': accept event, flag on timesheet for review
    If location unavailable: geofence_check_result = 'Skipped', accept event
Else:
  geofence_check_result = 'No_Geofence'

Insert clock_events row.
Async: update or create timesheet_entries for the day.
Show confirmation: "Clocked in at 07:23 on Site A".
```

**Clock-out flow:** mirror of clock-in. Computes shift duration on the fly and shows it on confirmation ("8h 12m today").

**Missing clock-out detection:**

```
Scheduled job at 23:30 each day:
  For each user with a Clock_In today and no matching Clock_Out:
    Mark timesheet_entries.has_missing_clockout = true
    Notify the user (push + portal banner): "You forgot to clock out — please add a clock-out time"
    Notify the site manager: "[user] has a missing clock-out for [project] [date]"
  
  After 48h with no resolution:
    Auto-correction proposal: site manager prompted to set clock-out time
    Default proposed time: 17:00 or end-of-shift per project default working hours from 1.7 config
    Site manager approves or sets custom; clock_corrections row created with correction_type='Add_Missing_Event'
```

**Break handling:**

Optional. Two patterns supported:
1. *Implicit:* user clocks in, clocks out at end of shift; break time is a fixed deduction per project rule (e.g. 30 min if shift > 6h). Configurable in 1.7 per project.
2. *Explicit:* user clocks Break_Start at lunchtime and Break_End on return. More accurate for variable-break sites but more friction. Defaults Off; project-level toggle.

**Timesheet weekly close:**

```
Scheduled job at 23:00 Sunday each week:
  For each user × project with clock_events in the week:
    Compute timesheet aggregates from clock_events.
    Set timesheets.status = 'Submitted' (auto-submission).
    Notify site manager: "Timesheets ready for approval — [N] users, [Y] hours total"
```

Auto-submission, not manual: labourers shouldn't have to remember to submit weekly. Site manager approves at the timesheet level (not per-event); approval flips status to `Approved` and locks the underlying clock_events from further correction (only director can re-open).

**Site manager weekly approval:**

```
Site manager view (/timesheets/approval):
  Table of timesheets where project IN site_manager.assigned_projects AND status = 'Submitted'
  Per row: user, total hours, has_warnings flag
  Click row → drill into timesheet_entries with per-day breakdown
  Per day: clock-in time, clock-out time, hours, geofence status, corrections
  Click any anomaly: see clock_events history with map (lat/lon plotted)
  Actions per timesheet: Approve, Reject (with reason), Adjust (creates clock_corrections)
  Bulk approve action for clean-no-anomaly timesheets
```

**CSV export to payroll:**

```
Action: "Export approved timesheets" on /timesheets/exports
  Filter: week, project, entity, status='Approved' or 'Approved+Exported'
  Renders one row per (user, project, week):
    user_employee_ref (from users.payroll_ref - new field), name,
    week_starting, total_hours_billable, project_code, entity_code,
    is_cis_subcontractor, cis_uvtr_or_utr (for sub) — for CIS-applicable users
  Format: standard CSV, configurable column order (1.7 setting).
  Marks status = 'Exported', records exported_in_batch_id (uuid).
  CSV downloadable and emailable to finance + payroll provider.
```

This is the intentional limit: the platform produces clean weekly hours; the actual payroll calc, PAYE, pension contributions are out of scope (Project Instructions: "Not a payroll system").

**Offline behaviour (uses 3.2 outbox):**

```
Labourer opens portal on phone with no signal:
  Recently-cached project assignment held in IndexedDB.
  Tap clock-in: clock_events row queued in outbox, event_time = client now().
  GPS captured if available locally.
  
On reconnect:
  Outbox flushes clock_events (idempotency key per event).
  Server validates: event_time cannot be > 24h in the future or > 7 days in the past (rejected if so, surfaced as correction request).
  Geofence check runs server-side against device_lat/lon at submission time.
  Timesheet_entries refresh.
  
Clock-out on different device than clock-in:
  Allowed. The two events share user_id and project_id, sequenced by event_time.
```

This is the second module (after 4.1) where offline matters most.

### UI

**Labourer portal — clock screen** (`/portal/labourer/clock`, also reached via 4.7):
- Big primary button: "Clock in" or "Clock out" depending on current state.
- Project name + site address visible.
- Below: today's hours so far ("you've worked 4h 12m today, on break 0m").
- Tertiary: this week's hours ("28h 42m this week").
- No other clutter. Tap-to-clock should take 2 taps total from app open.

**Site manager dashboard** — `/site/clocking`:
- Live "who's on site" widget — list of users currently Clocked_In on this site, with clock-in time and a stale flag if > 12h ago.
- Recent geofence warnings (yesterday + today).
- Missing clock-outs needing resolution.

**Timesheet approval** — `/timesheets/approval`:
- Status tabs: Submitted | Approved | Rejected | Exported.
- Submitted tab default; bulk approve action available.
- Per timesheet drill-down with map of clock locations.

**Director / contracts manager view** — `/timesheets`:
- Cross-project view, filterable by project, week, user, entity.
- Total hours rollup. Read-only after approval.

### Permissions

- `clock_events.create_own` — labourer, contractor portal user, internal users (for own clocks)
- `clock_events.view_own` — labourer, contractor portal user
- `clock_events.view_for_project` — site manager, project lead, contracts manager (project-scoped)
- `clock_events.view_all` — director, finance
- `clock_corrections.create` — site manager (own projects), director (any)
- `geofences.admin` — project lead, contracts manager
- `timesheets.view_own` — every user (own only)
- `timesheets.approve` — site manager (own projects), director (any)
- `timesheets.export` — finance, director
- `timesheets.reopen` — director only

The `Labourer` portal role (seeded in 4.7) ships with `clock_events.create_own`, `clock_events.view_own`, `timesheets.view_own` plus the site-tasks and end-of-day-summary scopes from 4.7 — and nothing else.

### Acceptance criteria

- [ ] Labourer can clock in via portal in 2 taps from app open
- [ ] Geolocation captured opportunistically; absence does not block clock-in
- [ ] Geofence check runs when project has active geofence; result logged on event
- [ ] Outside-geofence with `enforcement = Warn` accepts event but flags for review; with `Block` rejects with manual-entry option
- [ ] Geofence enforcement defaults to `Warn` for all projects (per spec — `Block` not configured by default)
- [ ] Clock-in followed by clock-out same day produces correct daily hours in timesheet_entries
- [ ] Missing clock-out detected at 23:30 with notification to user and site manager
- [ ] Auto-resolution proposal at 48h with default end-of-shift time
- [ ] Break handling supports both implicit (project rule deduction) and explicit (Break_Start/End events) modes
- [ ] Weekly auto-close at 23:00 Sunday; site manager notified of pending approvals
- [ ] Bulk approve action available for clean timesheets (no warnings, no corrections)
- [ ] CSV export produces one row per (user, project, week) with correct hours and CIS flags
- [ ] Approval locks underlying clock_events from correction (only director can re-open)
- [ ] Append-only enforcement: corrections create new clock_corrections rows; original events never mutated
- [ ] Offline flow: clock in/out on aeroplane mode, restore connection, both events sync correctly
- [ ] Idempotency keys prevent duplicate clock_events on retry
- [ ] Cross-device flow: clock in on device A, clock out on device B works end-to-end
- [ ] HMRC-applicable audit log present (who clocked, when, where, who approved, when exported)

### Out of scope

- Direct payroll processing (PAYE, RTI, pension) — Project Instructions: "Not a payroll system".
- Direct HMRC CIS submission from clock data — Future Tasks Phase 4. Manual export to CIS module of Xero (or third-party) covers Phase 2.
- Biometric authentication for clock-in (face / fingerprint) — Future Tasks Phase 5.
- Kiosk-mode clocking app for shared site terminals — Future Tasks Phase 5; for v1, every clocker uses their own phone.
- Geofence editing UI on a map — basic JSON editor only for v1; map drawing tool is Future Tasks Phase 3.
- Sub-shift or multi-project-per-day attribution beyond simple project switching (e.g. "I worked 3h on Project A then 5h on Project B") — supported by clocking out of A and into B; per-task time attribution is Future Tasks Phase 5.
- Working Time Directive compliance alerts (≥48h average, daily rest) — Future Tasks Phase 5; contracts manager monitors manually.
- Holiday and absence tracking — out of scope; tracked elsewhere.

---

## Prompt 4.3 — Chat / Messaging

**Dependencies:** 3.1
**Tables in this prompt:** `chat_channels`, `chat_channel_members`, `chat_messages`, `chat_threads`, `chat_attachments`, `chat_reads`, `chat_mentions`
**Estimated hours:** 14h
**Status:** NEW. Heaviest single prompt in T4.

Real-time messaging built on the 3.1 WebSocket infrastructure. Project-scoped channels, role-scoped channels (e.g. "all site managers"), direct messages, threaded replies, file attachments, @mentions tied to notifications, read receipts, search across messages, mobile push notifications.

The bar is high. Chat replaces WhatsApp for project comms — WhatsApp is convenient and SY Homes's team has muscle memory for it. Phase 2 acceptance criteria do not include WhatsApp displacement; that is operational and measured post-launch. The criterion here is: the chat experience is as fast and as fluid as WhatsApp for the things people use WhatsApp for, plus advantages WhatsApp does not have (linked to project context, audit-trailed, threaded responses, searchable across history, mentions tied to assignments). Coexistence with WhatsApp is the assumed early state.

### Build `chat_channels`

```
chat_channels
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
channel_type                    enum NOT NULL
                                  ('Project','Role_Scoped','Custom_Group','Direct_Message','Announcement')
realtime_channel_id             uuid NOT NULL FK→realtime_channels.id
                                  -- 1:1 binding to the 3.1 realtime channel for this chat
project_id                      uuid FK→projects.id                -- if channel_type=Project
role_id                         uuid FK→roles.id                   -- if channel_type=Role_Scoped
name                            varchar(100) NOT NULL              -- "Site A" / "All Site Managers"
description                     text
is_archived                     boolean NOT NULL DEFAULT false
is_announcement_only            boolean NOT NULL DEFAULT false     -- only admins can post
last_message_at                 timestamp
last_message_id                 uuid                               -- denormalised for sort
message_count                   int NOT NULL DEFAULT 0
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()
archived_at                     timestamp

Indexes:
- INDEX (tenant_id, channel_type, is_archived)
- INDEX (project_id) WHERE channel_type = 'Project' AND is_archived = false
- INDEX (last_message_at DESC) WHERE is_archived = false
- UNIQUE (realtime_channel_id)
```

`Project` channel auto-created when a project goes Live (project status from 1.5). `Role_Scoped` channels seeded for each operational role (`Site_Managers`, `Contracts_Managers`, `Finance`, `Directors`, `Designers`). `Direct_Message` is a 2-person channel created on first DM between any pair. `Custom_Group` for ad-hoc groups (e.g. "Plot 14 fit-out task force").

### Build `chat_channel_members`

```
chat_channel_members
─────────────────────────────────────────────
id                              uuid PK
channel_id                      uuid NOT NULL FK→chat_channels.id ON DELETE CASCADE
user_id                         uuid NOT NULL FK→users.id ON DELETE CASCADE
role_in_channel                 enum NOT NULL DEFAULT 'Member'
                                  ('Owner','Admin','Member','Read_Only')
joined_at                       timestamp NOT NULL DEFAULT now()
left_at                         timestamp
notification_preference         enum NOT NULL DEFAULT 'All'
                                  ('All','Mentions_Only','Muted')
last_read_message_id            uuid                               -- for unread count
last_read_at                    timestamp

Indexes:
- UNIQUE (channel_id, user_id) WHERE left_at IS NULL
- INDEX (user_id, channel_id) WHERE left_at IS NULL
```

Project channel membership auto-derives from `project_team_members` (1.5) + project lead + assigned contracts manager + director with project access. Role channels auto-derive from users with the relevant role. DM channels are 2-row.

### Build `chat_messages`

```
chat_messages
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
channel_id                      uuid NOT NULL FK→chat_channels.id ON DELETE CASCADE
thread_id                       uuid FK→chat_threads.id            -- null = top-level message
parent_message_id               uuid FK→chat_messages.id           -- null unless reply
sender_user_id                  uuid NOT NULL FK→users.id
content                         text NOT NULL                      -- markdown-lite (bold, italic, code, links)
content_plain                   text NOT NULL                      -- stripped for search index
message_type                    enum NOT NULL DEFAULT 'Text'
                                  ('Text','Image','File','System','Quote')
                                  -- System for "user joined", "channel renamed" etc.
is_edited                       boolean NOT NULL DEFAULT false
edited_at                       timestamp
is_deleted                      boolean NOT NULL DEFAULT false     -- soft delete
deleted_at                      timestamp
deleted_by_user_id              uuid FK→users.id
mention_user_ids                jsonb DEFAULT '[]'                 -- denormalised for fast notification fanout
attachment_ids                  jsonb DEFAULT '[]'                 -- list of chat_attachments.id
quoted_message_id               uuid FK→chat_messages.id           -- if message_type=Quote
client_message_id               varchar(60)                        -- idempotency key from client
sequence_number                 bigint NOT NULL                    -- monotonic per channel
sent_at                         timestamp NOT NULL DEFAULT now()
search_vector                   tsvector                           -- generated column

Indexes:
- INDEX (channel_id, sequence_number DESC)
- INDEX (channel_id, sent_at DESC)
- INDEX (thread_id, sent_at) WHERE thread_id IS NOT NULL
- INDEX (sender_user_id, sent_at DESC)
- INDEX (search_vector) USING GIN
- UNIQUE (channel_id, client_message_id) WHERE client_message_id IS NOT NULL
```

`sequence_number` is monotonically allocated per channel (Postgres sequence per-channel via partition key, or simple `MAX + 1` under serializable transaction at message rate; latter sufficient). Used to support reliable replay on reconnect via 3.1's event sequence pattern.

`content` stores a constrained markdown subset: bold (`**x**`), italic (`*x*`), inline code (`` `x` ``), code blocks (triple backtick), links (`[text](url)`), and that's it. No headings, no images-by-syntax (use attachments), no tables. Render client-side with a strict markdown parser; sanitise on display to avoid XSS.

### Build `chat_threads`

```
chat_threads
─────────────────────────────────────────────
id                              uuid PK
channel_id                      uuid NOT NULL FK→chat_channels.id ON DELETE CASCADE
root_message_id                 uuid NOT NULL UNIQUE FK→chat_messages.id ON DELETE CASCADE
reply_count                     int NOT NULL DEFAULT 0
participant_user_ids            jsonb NOT NULL DEFAULT '[]'        -- distinct users in thread
last_reply_at                   timestamp
last_reply_message_id           uuid FK→chat_messages.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (channel_id, last_reply_at DESC)
```

Threads are how conversations don't drown each other. A thread is created automatically when a user replies to a top-level message (the first reply triggers thread creation; the original message gets `thread_id` set retroactively). Root message visible inline in the channel; replies live in a side panel that opens on thread click.

### Build `chat_attachments`

Files attached to messages. Inline photos (small, viewed right in the chat) live here. Larger / formal documents are uploaded to the document store (5.2) and referenced by URL — for documents > 10MB the system prompts the user to use 5.2 instead so they're properly classified, version-controlled, and access-restricted.

```
chat_attachments
─────────────────────────────────────────────
id                              uuid PK
message_id                      uuid NOT NULL FK→chat_messages.id ON DELETE CASCADE
attachment_type                 enum NOT NULL
                                  ('Image','Video','File','Document_Link','Audio')
                                  -- Document_Link = link to documents (5.2), no inline file
display_name                    varchar(500)
file_storage_backend            enum
                                  ('S3','Azure_Blob','GCS','Local')
file_storage_key                text
file_thumbnail_storage_key      text                               -- for images / videos
file_mime_type                  varchar(100)
file_size_bytes                 bigint
file_width_px                   int                                -- for images
file_height_px                  int
file_duration_seconds           decimal(8,2)                       -- for video / audio
linked_document_id              uuid FK→documents.id               -- if attachment_type=Document_Link
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (message_id)
- INDEX (linked_document_id) WHERE linked_document_id IS NOT NULL
```

Image attachments thumbnailed server-side. Inline video supported up to 100MB; over that, prompts user to upload to documents (5.2).

### Build `chat_reads`

Per-user-per-channel high-water mark. The "unread" count is computed from this against `chat_messages.sequence_number`.

```
chat_reads
─────────────────────────────────────────────
id                              uuid PK
user_id                         uuid NOT NULL FK→users.id ON DELETE CASCADE
channel_id                      uuid NOT NULL FK→chat_channels.id ON DELETE CASCADE
last_read_message_id            uuid FK→chat_messages.id
last_read_sequence_number       bigint NOT NULL DEFAULT 0
last_read_at                    timestamp NOT NULL DEFAULT now()
mention_unread_count            int NOT NULL DEFAULT 0             -- fast access without query
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (user_id, channel_id)
- INDEX (user_id, mention_unread_count) WHERE mention_unread_count > 0
```

Per-message read receipts (showing who has viewed each individual message) are deliberately NOT modelled. WhatsApp does this with the double-tick / blue-tick pattern; in a workplace tool it creates pressure ("I saw you read it") that's counterproductive. Per-channel high-water mark only.

### Build `chat_mentions`

```
chat_mentions
─────────────────────────────────────────────
id                              uuid PK
message_id                      uuid NOT NULL FK→chat_messages.id ON DELETE CASCADE
mentioned_user_id               uuid NOT NULL FK→users.id ON DELETE CASCADE
mention_type                    enum NOT NULL DEFAULT 'User'
                                  ('User','Channel','Here','Role')
                                  -- Channel = @channel (everyone in channel)
                                  -- Here = @here (currently online in channel)
                                  -- Role = @site_managers etc.
is_acknowledged                 boolean NOT NULL DEFAULT false
acknowledged_at                 timestamp
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (mentioned_user_id, is_acknowledged, created_at DESC)
- INDEX (message_id)
```

Mentions drive notifications. `@user`: that user only. `@channel`: every member of the channel. `@here`: every member currently subscribed to the channel via 3.1 (i.e. has an open WS). `@role`: every user with that role. Channel and role mentions are firehose; UI warns before sending one to a channel with > 20 members.

### Business logic

**Sending a message:**

```
Client builds message:
  channel_id, content, optional mention parses, optional attachments, client_message_id (uuid)
POST /api/chat/messages with above
Server:
  Verify user is a member of channel (chat_channel_members.left_at IS NULL)
  If channel is_announcement_only: verify user has Admin or Owner role in channel
  Parse mentions from content (@mentions of users / @channel / @here / @role)
  Allocate sequence_number = SELECT max(sequence_number)+1 FROM chat_messages WHERE channel_id=X
                              (under serializable txn or advisory lock per channel)
  Insert chat_messages row with mention_user_ids[]
  Insert chat_mentions rows
  If parent_message_id set: ensure thread exists; append reply
  Update chat_channels.last_message_at, last_message_id, message_count
  Update chat_reads.last_read_sequence_number for sender (sender's own message marks read)
  
  Broadcast via 3.1:
    realtime_events row created with event_type='chat.message', payload={message_id, channel_id, sender, content, ...}
    sequence_number from chat_messages reused
    All subscribers to realtime_channel see it within ~150ms of send
  
  Notification fanout (async):
    For each mentioned_user_id NOT currently subscribed to channel:
      notification.create(type='chat.mention', payload, recipient=user_id)
      push notification fired (mobile push if device registered)
    For each member with notification_preference='All' NOT currently subscribed:
      notification.create(type='chat.message', payload, recipient=member)
      (digest, not push, for non-mention)
```

Idempotency: `client_message_id` UNIQUE per channel — if the client retries after a network blip and the original message was actually delivered, the server returns the existing message rather than creating a duplicate.

**Editing a message:**

- Allowed for sender within 24h of send. After 24h: locked.
- Edits set `is_edited=true`, `edited_at`, content updated. Original content not retained (out of scope; if regulatory replay matters, audit log captures the edit event).
- Realtime broadcast `event_type='chat.message_edited'` so other clients update.

**Deleting a message:**

- Soft delete only. Sets `is_deleted=true`, `deleted_at`, `deleted_by_user_id`.
- Display: "[message deleted]" placeholder retained in flow so thread continuity isn't broken.
- Sender can delete own within 24h. After 24h, only `chat.admin` (channel admin or director) can.
- Hard delete is `chat.admin` action only and explicit; sets content to null, attachments dropped from storage. Audit-logged.

**Search:**

Postgres full-text search via `search_vector` GIN index. Search query against (a) content_plain, (b) attachment display_names, (c) sender display_name. Filters: channel, sender, date range, has-attachment. Mobile and desktop UI both expose search in the same modal. Deleted messages excluded from search.

**Mention notification:**

```
On mention.created:
  recipient_user_id = mentioned_user_id
  in_app_notification.create({
    type: 'chat.mention',
    title: f"{sender.display_name} mentioned you in #{channel.name}",
    body: message_excerpt(140 chars),
    deep_link: f"/chat/{channel.id}#{message.id}",
  })
  
  IF user has push token registered AND notification_preference != 'Muted':
    fcm_or_apns.send(user.push_tokens, {
      title: notification.title,
      body: notification.body,
      data: { deep_link: notification.deep_link },
    })
  
  Update chat_reads.mention_unread_count += 1
```

Push notifications via FCM (Android) and APNs (iOS). PWA supported via Web Push (Notifications API + Service Worker) for desktop notifications too.

**Read receipts (channel-level):**

```
Client signal: user has scrolled to bottom of channel / opened channel
POST /api/chat/channels/:id/read with last_read_message_id
Server:
  Update chat_reads row for (user, channel)
  Reset mention_unread_count = count of unack mentions newer than message_id
  Broadcast 'chat.read' event to user's own subscriptions for unread badge sync across devices
```

**Channel auto-membership rules:**

```
On project.status → 'Live' (from 1.5):
  Create chat_channel(channel_type=Project, project_id, name=project.name)
  Auto-add chat_channel_members:
    - project lead, assistant project lead, contracts manager, finance director, directors with project access
    - all project_team_members (from 1.5)

On project.status → 'On_Hold' or 'Completed':
  Channel remains active. (Communication continues for handover and DLP.)

On project.status → 'Archived':
  Channel set is_archived=true. Read-only via realtime.
  
On project_team_members.add (1.5):
  Add chat_channel_members row for project channel.

On project_team_members.remove (1.5):
  Set chat_channel_members.left_at = now() (preserve history of who saw what).
```

**Direct messages:**

```
User opens DM with another user:
  Look up chat_channels with channel_type='Direct_Message' AND members={user_a, user_b}
  If exists: open it
  Else: create new channel + 2 chat_channel_members rows
  
DM channels not searchable by other users.
DM channels not auto-archived.
```

**WebSocket integration with 3.1:**

```
On chat_messages insert:
  Server-side broadcast hook (3.1 helper):
    realtime_events.publish(
      channel = chat_channels.realtime_channel_id,
      event_type = 'chat.message',
      payload = { message_id, sender, content, sent_at, attachment_ids, mentions },
      sequence_number = chat_messages.sequence_number
    )

Client connects to chat_channels.realtime_channel_id on channel open.
Receives 'chat.message' events live.
On reconnect, replays from last seen sequence_number using realtime_events.
```

`realtime_events.ttl_seconds` for chat events overridden to 30 days (vs 24h default) — this is the "chat events override to 30 days" exception flagged in 3.1's spec. Older messages are read from `chat_messages` directly; replay is for recent reconnect catch-up.

### UI

**Mobile chat home** (`/chat`):
- List of channels sorted by last_message_at DESC.
- Per row: channel name, last message preview, time, unread badge (with mention count if any).
- Tap channel → conversation view.
- Floating "+" for new DM / new custom group.

**Conversation view** (`/chat/:channel_id`):
- Header: channel name, member count, settings cog.
- Message list: virtualised (react-window) for performance with 10k+ message history.
- Each message: avatar + sender name + time + content + attachments + reactions (Phase 2 has no emoji reactions — Future Tasks).
- Reply action launches thread side-panel (mobile: full-screen modal).
- Bottom: composer with text area, attach button, send button.
- Composer @-trigger opens autocomplete: users in channel, then @channel/@here/@role.
- Slash commands: `/giphy` not supported, `/poll` not supported. Plain text only with mentions and attachments.

**Composer attachment flow:**
- Camera → take photo / video → inline upload.
- Photo library → pick image(s) → inline upload.
- File picker → if > 10MB or doc-like (.docx/.xlsx/.pdf) → prompt to upload to documents (5.2) instead, retain reference.

**Search** (`/chat/search` modal):
- Query box, channel filter, sender filter, date filter, has-attachment filter.
- Results grouped by channel; tap to jump.

**Notifications & badge management:**
- Per-channel: All / Mentions_Only / Muted toggle.
- Global: do-not-disturb hours (1.7 user preference — out of band).
- Phone push respects DND.

### Permissions

- `chat.view` — every authenticated internal user (channel-level membership filters)
- `chat.send` — every authenticated internal user (channel-level membership filters)
- `chat.edit_own` — sender within 24h of send
- `chat.delete_own` — sender within 24h of send
- `chat.admin` — director, contracts manager (own projects), site manager (own project channel)
- `chat.create_custom_group` — every internal user (within tenant)
- `chat.create_announcement_channel` — director only
- `chat.invite_external` — **explicitly not in scope** — portal users (suppliers, subcontractors, labourers) do not get chat access in Phase 2. Communication with externals stays in portal-specific notifications + email + WhatsApp. Inviting suppliers to chat is Future Tasks Phase 3.

### Acceptance criteria

- [ ] Sending a text message in a project channel reaches all subscribed members within 200ms median, 500ms p99
- [ ] Reconnecting after a 30s network blip replays missed messages without duplication or gaps
- [ ] Idempotent send: retry of same client_message_id returns existing message, doesn't duplicate
- [ ] @user mention triggers in-app notification + mobile push for the recipient (if not currently subscribed to channel)
- [ ] @channel mention with > 20 channel members shows confirmation dialog before send
- [ ] Threaded replies display in side panel on desktop, full-screen on mobile
- [ ] Image attachment ≤ 25MB uploads inline with thumbnail
- [ ] File attachment > 10MB or doc-typed prompts redirection to documents (5.2) upload
- [ ] Document_Link attachment renders as link with document type and access-restriction badge
- [ ] Edit own message within 24h works; after 24h locked
- [ ] Soft delete leaves "[message deleted]" placeholder; thread continuity intact
- [ ] Hard delete removes content from chat_messages, removes file from storage, audit-logged
- [ ] Search returns matching messages with channel context; permissions respected (won't return DMs of other users)
- [ ] Channel auto-membership: project team member added → channel membership added
- [ ] Read state syncs across devices: read on phone, desktop unread count updates within 1s
- [ ] Mention unread count is fast (no full message scan needed)
- [ ] Notification preferences respected: Muted channel doesn't push for mentions either (explicit user choice)
- [ ] Mobile UX tested on iOS Safari and Android Chrome — typing, sending, scrolling smooth at 60fps with 5k message history
- [ ] PWA install on Android works; web push delivers mention notifications when app closed
- [ ] Audit log captures: channel creation, message hard delete, member add/remove

### Out of scope

- Voice / video calling within chat — Future Tasks Phase 5 (significant infra; external tools cover this).
- Emoji reactions on messages — Future Tasks Phase 3 (low cost; deferred to keep 4.3 size manageable).
- Polls, GIFs, integrations (giphy, calendar, etc.) — out of scope; not what this is for.
- External party (supplier / subcontractor / labourer) chat access — Future Tasks Phase 3. Portal-specific notifications + email cover externals in Phase 2.
- Message scheduling ("send at 8am tomorrow") — Future Tasks Phase 5.
- Chat-to-task conversion ("turn this message into a programme task") — Future Tasks Phase 5.
- Translation / multilingual support — out of scope; SY Homes operates in English.
- WhatsApp bridging (forward WhatsApp messages into chat) — explicitly out of scope. The point of chat is to move project comms off WhatsApp gradually, not to entrench WhatsApp.
- Read receipts at the per-message level (who specifically has read this message) — deliberately not modelled (workplace anti-pattern).

### Operational note (not an acceptance criterion)

The team's adoption of chat over WhatsApp is operational, not technical. The build delivers parity-plus. Whether the team actually uses it is judged at the audit checkpoint mid-T4 and post-launch. If adoption is poor at audit, options are: (a) kill chat and accept WhatsApp as the comms layer with platform notifications by email, (b) invest more in chat features to close gaps. That is a Rhys decision after data, not a build decision now.

---

## Prompt 4.4 — RFIs (Formal Workflow)

**Dependencies:** 1.5, 4.3
**Tables in this prompt:** `rfis`, `rfi_responses`, `rfi_attachments`
**Estimated hours:** 8h
**Status:** NEW.

Formal Request for Information workflow. Per the Chat 5 framing, RFIs stay as a structured workflow rather than collapsing into chat. Chat is conversational; RFIs are the formal record. An RFI on a programme task may pause the task; SLA is tracked; designers and external consultants can be assigned. The audit trail matters because RFIs feed into variation justifications and dispute records later.

### Build `rfis`

```
rfis
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
rfi_number                      varchar(40) NOT NULL                -- "RFI-{project_code}-001"
subject                         varchar(255) NOT NULL
description                     text NOT NULL
raised_by_user_id               uuid NOT NULL FK→users.id
raised_by_role                  varchar(60)                         -- denormalised role at time of raise
assigned_to_user_id             uuid FK→users.id                    -- internal user (designer, CM)
assigned_to_external_email      varchar(255)                        -- external consultant via email
assigned_at                     timestamp
sla_response_days               int NOT NULL DEFAULT 5              -- working days
sla_due_at                      timestamp                           -- computed: assigned_at + sla_response_days WD
status                          enum NOT NULL DEFAULT 'Draft'
                                  ('Draft','Open','Awaiting_Response','Answered','Closed','Withdrawn')
priority                        enum NOT NULL DEFAULT 'Normal'
                                  ('Low','Normal','High','Urgent')
related_task_ids                jsonb DEFAULT '[]'                  -- programme_tasks.id list (3.4)
pauses_tasks                    boolean NOT NULL DEFAULT false      -- if true, linked tasks paused on RFI raise
related_subcontract_id          uuid FK→subcontracts.id             -- 2.8a
related_document_ids            jsonb DEFAULT '[]'                  -- documents (5.2) referenced
final_response_id               uuid FK→rfi_responses.id            -- the response that closed the RFI
closed_at                       timestamp
closed_by_user_id               uuid FK→users.id
withdrawn_at                    timestamp
withdrawn_reason                text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (tenant_id, rfi_number)
- INDEX (project_id, status)
- INDEX (assigned_to_user_id, status) WHERE status IN ('Open','Awaiting_Response')
- INDEX (sla_due_at) WHERE status IN ('Open','Awaiting_Response')
- INDEX (status, raised_at) WHERE status NOT IN ('Closed','Withdrawn')
```

`rfi_number` auto-generated on raise: `RFI-{project_code}-{seq:03d}`. Sequence is per-project.

### Build `rfi_responses`

```
rfi_responses
─────────────────────────────────────────────
id                              uuid PK
rfi_id                          uuid NOT NULL FK→rfis.id ON DELETE CASCADE
response_type                   enum NOT NULL
                                  ('Question_Asked','Information_Provided','Clarification_Requested',
                                   'Withdrawn','Closing_Response')
content                         text NOT NULL
responder_user_id               uuid FK→users.id                   -- internal responder
responder_external_name         varchar(255)                       -- if from external by email
responder_external_email        varchar(255)
is_official_response            boolean NOT NULL DEFAULT false     -- the formal answer that closes the RFI
attachment_ids                  jsonb DEFAULT '[]'                 -- rfi_attachments.id list
created_at                      timestamp NOT NULL DEFAULT now()
sequence_number                 int NOT NULL                       -- per-rfi ordering

Indexes:
- INDEX (rfi_id, sequence_number)
- INDEX (responder_user_id, created_at DESC)
```

Response types accommodate the conversational flow of an RFI (back-and-forth before a final answer). Only the response with `is_official_response=true` closes the RFI. Multiple non-official responses can accumulate.

### Build `rfi_attachments`

```
rfi_attachments
─────────────────────────────────────────────
id                              uuid PK
rfi_id                          uuid FK→rfis.id ON DELETE CASCADE
rfi_response_id                 uuid FK→rfi_responses.id ON DELETE CASCADE
attachment_type                 enum NOT NULL
                                  ('Image','File','Document_Link','Markup')
                                  -- Markup = annotated drawing (PDF + overlay)
display_name                    varchar(500)
file_storage_backend            enum
                                  ('S3','Azure_Blob','GCS','Local')
file_storage_key                text
file_thumbnail_storage_key      text
file_mime_type                  varchar(100)
file_size_bytes                 bigint
linked_document_id              uuid FK→documents.id               -- if Document_Link
markup_pdf_storage_key          text                               -- if Markup
markup_data                     jsonb                              -- annotation overlay JSON
uploaded_by_user_id             uuid FK→users.id
uploaded_at                     timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (rfi_id) WHERE rfi_id IS NOT NULL
- INDEX (rfi_response_id) WHERE rfi_response_id IS NOT NULL
- INDEX (linked_document_id) WHERE linked_document_id IS NOT NULL

Constraint: exactly one of (rfi_id, rfi_response_id) must be non-null.
```

The `Markup` attachment type accommodates the common case: someone marks up a drawing PDF and includes it in the RFI. Phase 2 stores the annotated PDF and a JSON overlay for display; full WYSIWYG markup editor is out of scope (use external tools or just upload a marked-up PDF).

### Business logic

**Raising an RFI:**

```
Site manager / contracts manager raises RFI:
  Form: subject, description, related_task_ids (picker), related_subcontract_id (picker),
        priority, sla_response_days (default 5), assignee
  
  Assignee is one of:
    - internal user (e.g. project lead, designer) → assigned_to_user_id
    - external email (e.g. external structural engineer) → assigned_to_external_email
  
  Submit:
    Generate rfi_number
    Set status = 'Open'
    Set assigned_at = now()
    Compute sla_due_at = working-day calculation: assigned_at + sla_response_days WD
      (uses project.calendar from 3.3 if available, else default UK working-week calendar)
    
    If pauses_tasks = true AND related_task_ids non-empty:
      For each task: programme_tasks.status_modifier = 'Paused_RFI', programme_tasks.paused_rfi_id set
      (Programme module 3.5 picks up this status and adjusts CPM accordingly)
    
    Notify assignee:
      Internal: in-app notification + email (and chat 4.3 mention if assignee in same project channel)
      External: email with secure link to /rfi-external/:token (one-time link)
    
    Audit log entry.
```

**External-email RFI flow:**

External assignees (consultants without portal accounts) receive an email with a token-secured link. The link opens a minimal RFI view: question, attachments, response form (text + attachments). Submission posts a `rfi_responses` row with `responder_external_name` and `responder_external_email`. No login required; one-time link with 30-day expiry.

This supports the common "we have an external structural engineer who's not on the platform" case without forcing portal account creation for occasional consultants.

**SLA tracking and breach:**

```
Scheduled job hourly:
  SELECT rfis WHERE status IN ('Open','Awaiting_Response')
                 AND sla_due_at < now()
                 AND not yet flagged as breached
  
  For each:
    Set internal flag breached=true (denormalised on rfis or computed)
    Notify: assignee, raiser, project lead
    Severity High if priority=High; Critical if Urgent
    
  Sum at project level: count of breached RFIs visible on project dashboard.
```

Breach is informational, not blocking. The platform doesn't auto-escalate on breach (human decision). RFI dashboard shows breached count prominently.

**Conversational responses:**

```
Assignee posts response:
  response_type = Information_Provided / Clarification_Requested
  content + optional attachments
  
  If Clarification_Requested → status moves Open ↔ Awaiting_Response (raiser must respond next)
  If Information_Provided not yet marked official → status stays Open
  
Raiser closes RFI:
  Action: "Mark this response as the answer"
  Sets is_official_response=true on chosen response
  Sets rfis.status='Answered', final_response_id set
  
  If pauses_tasks: unpause linked tasks (status_modifier cleared)
  
  Or raiser explicitly: "Close RFI" (without picking a particular response — uses last response)
  Sets rfis.status='Closed', closed_at, closed_by_user_id

Withdraw:
  Raiser only, with reason. status='Withdrawn'.
  Linked tasks unpaused.
```

**Variation linkage:**

If the closing response indicates a change to scope (UI prompt: "Does this response require a variation?"), a "Raise variation" action is offered, pre-populating a `subcontract_variations` row (2.8a) with this RFI in `instruction_source = 'Architect_Instruction'` and a back-link to the RFI.

This is the audit thread: RFI → response → variation → BCR → budget change. The dispute story unwinds cleanly.

**Realtime updates:**

RFI events (raised, response posted, closed) broadcast on the project's `realtime_channel_id` so an RFI dashboard refreshes live.

### UI

**Project RFI list** (`/projects/:id/rfis`):
- Table: number, subject, raised_by, raised_at, assigned_to, status, SLA badge (green / amber within 1 WD / red breached), priority.
- Filters: status, priority, assignee, breached.
- "+ New RFI" action.

**RFI detail** (`/rfis/:id`):
- Header: number, subject, status pill, priority, SLA countdown.
- Sidebar: raised_by/at, assigned_to/at, related tasks (linked), related subcontract, related documents.
- Conversation thread: chronological list of responses.
- Composer at bottom for new response (assignee or raiser).
- Action buttons: Reassign, Mark as answer, Close, Withdraw.

**External response page** (`/rfi-external/:token`):
- Minimal layout, no app shell.
- Question + attachments visible.
- Response composer + attachment uploader.
- Submit button.
- After submit: "Thank you, your response has been received."

**Project dashboard widget** (used in 7.4 reporting):
- Open RFIs count.
- Breached RFIs count.
- Average response time over last 90 days.

### Permissions

- `rfis.view` — project team (scoped), director, finance (read-only)
- `rfis.create` — site manager, project lead, contracts manager, director
- `rfis.respond_internal` — assignee + project lead + director
- `rfis.respond_external` — externally-assigned via token (no platform user)
- `rfis.close` — raiser, project lead, director
- `rfis.withdraw` — raiser, director
- `rfis.reassign` — project lead, director, contracts manager
- `rfis.admin` — director (override anything)

### Acceptance criteria

- [ ] RFI created with auto-numbered ref (RFI-{project_code}-{seq})
- [ ] SLA due time computed using working-day calendar from 3.3
- [ ] Internal assignee receives in-app notification + email + chat mention (if in project channel)
- [ ] External assignee receives email with token link; link works without authentication; expires at 30 days
- [ ] External response submission posts rfi_responses row with responder_external_email
- [ ] Breach detection runs hourly; notifies relevant parties on first breach
- [ ] Pause-tasks: setting pauses_tasks=true on raise updates programme_tasks.status_modifier; close unpauses
- [ ] Mark-as-answer transitions status correctly and closes the RFI
- [ ] Variation prompt appears on close if response indicates scope change; pre-fills subcontract_variations row
- [ ] Realtime broadcast on raise / response / close reaches subscribed users via 3.1
- [ ] Markup attachment uploads PDF + JSON overlay; renders correctly in detail view
- [ ] Document_Link attachment renders as link to documents (5.2)
- [ ] SLA badge renders correctly: green > 1WD remaining, amber ≤ 1WD, red breached
- [ ] Audit log captures: raise, reassign, response submission, close, withdraw

### Out of scope

- BIM model annotation / IFC integration — Future Tasks Phase 4 (BIM module).
- Auto-routing RFIs to designer based on RFI category — Future Tasks Phase 5.
- RFI templates per project type — Future Tasks Phase 3.
- Automated escalation on SLA breach (e.g. auto-reassign to director after 2 days breached) — Future Tasks Phase 5.
- Multi-stakeholder approval of RFI responses (e.g. structural + architect both must sign off) — out of scope; one closing response only.
- WYSIWYG markup editor in-platform — out of scope; users mark up PDFs externally and upload.
- Export RFI register as PDF — Future Tasks Phase 3 (the wider report exports come in 7.4).

---

## Prompt 4.5 — QA Checklists with Mandatory Photos

**Dependencies:** 1.5, 1.6, 3.2, 3.4
**Tables in this prompt:** `qa_checklist_templates`, `qa_checklist_template_items`, `qa_checklists`, `qa_items`, `qa_photos`, `qa_signoffs`
**Estimated hours:** 12h
**Status:** NEW.

QA checklist templates per cost code or per task type. Checklists instantiated against a project / task / location. Items can be flagged "photo required" — the checklist cannot be marked complete without the photo. Workflow: contractor (often via 2.9 portal) submits checklist with evidence; site manager reviews and approves or returns; failures feed into snagging (4.6). Offline-capable (huge for site use — much QA happens in unfinished buildings with no signal).

This module replaces clipboard QA, the photos-on-WhatsApp evidence trail, and the "did anyone actually check that snag was fixed?" problem.

### Build `qa_checklist_templates`

```
qa_checklist_templates
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
template_code                   varchar(40) NOT NULL                -- "QA-FOUND-001"
name                            varchar(255) NOT NULL                -- "Foundation pour - pre-cast"
description                     text
category                        enum NOT NULL
                                  ('Substructure','Superstructure','Envelope','First_Fix','Second_Fix',
                                   'Finishes','MEP','External_Works','Snag_Fix','Statutory','Other')
applicable_cost_code_ids        jsonb DEFAULT '[]'                  -- cost_codes (1.6) this applies to
applicable_task_types           jsonb DEFAULT '[]'                  -- programme task type tags
trade                           varchar(100)
is_active                       boolean NOT NULL DEFAULT true
is_system_template              boolean NOT NULL DEFAULT false      -- seed templates
version                         int NOT NULL DEFAULT 1
created_by_user_id              uuid NOT NULL FK→users.id
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (tenant_id, template_code, version)
- INDEX (tenant_id, category, is_active)
```

Templates are versioned. When a template is edited, a new version is created (immutable predecessor) so checklists already issued against the previous version retain their original item set. Live checklists never change underneath a contractor.

### Build `qa_checklist_template_items`

```
qa_checklist_template_items
─────────────────────────────────────────────
id                              uuid PK
template_id                     uuid NOT NULL FK→qa_checklist_templates.id ON DELETE CASCADE
sequence                        int NOT NULL
item_text                       varchar(500) NOT NULL
item_detail                     text                                -- guidance / spec ref
photo_required                  boolean NOT NULL DEFAULT false
photo_required_count            int NOT NULL DEFAULT 1              -- minimum photos
expected_response_type          enum NOT NULL DEFAULT 'Pass_Fail'
                                  ('Pass_Fail','Yes_No','Numeric','Text','Pick_One')
response_options                jsonb                               -- if Pick_One
numeric_unit                    varchar(20)                         -- if Numeric (e.g. 'mm', 'mPa')
numeric_min                     decimal(12,4)
numeric_max                     decimal(12,4)
is_critical                     boolean NOT NULL DEFAULT false      -- failure must be raised as snag
linked_spec_document_id         uuid                                -- doc ref (5.2)
notes                           text

Indexes:
- INDEX (template_id, sequence)
```

`is_critical` items: when failed, automatically create a `Snag_Fix` task in 4.6. Non-critical failures still flow to snagging by default but with `severity=Low` rather than the inherited critical severity.

### Build `qa_checklists`

The instantiated checklist against a specific project / task / location.

```
qa_checklists
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
template_id                     uuid NOT NULL FK→qa_checklist_templates.id
template_version                int NOT NULL                        -- version at time of instantiation
related_task_id                 uuid FK→programme_tasks.id          -- 3.4
related_subcontract_id          uuid FK→subcontracts.id             -- 2.8a
related_plot_id                 uuid                                -- 7.1 plots, when in scope
location_label                  varchar(255)                        -- "Block A, Level 2, Plot 14"
location_lat                    decimal(9,6)
location_lon                    decimal(9,6)
status                          enum NOT NULL DEFAULT 'Issued'
                                  ('Issued','In_Progress','Submitted','Returned','Approved','Rejected','Cancelled')
issued_to_subcontractor_id      uuid FK→subcontractors.id           -- 2.7
issued_to_user_id               uuid FK→users.id                    -- internal alternative
issued_by_user_id               uuid NOT NULL FK→users.id
issued_at                       timestamp NOT NULL DEFAULT now()
due_date                        date
submitted_at                    timestamp
submitted_by_user_id            uuid FK→users.id
returned_at                     timestamp
returned_by_user_id             uuid FK→users.id
returned_reason                 text
approved_at                     timestamp
approved_by_user_id             uuid FK→users.id
rejection_reason                text
total_items                     int NOT NULL DEFAULT 0              -- cached from template
items_passed                    int NOT NULL DEFAULT 0
items_failed                    int NOT NULL DEFAULT 0
items_pending                   int NOT NULL DEFAULT 0
notes                           text
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, status)
- INDEX (issued_to_subcontractor_id, status)
- INDEX (related_task_id) WHERE related_task_id IS NOT NULL
- INDEX (status) WHERE status IN ('Submitted','Returned')
```

### Build `qa_items`

Per-item response.

```
qa_items
─────────────────────────────────────────────
id                              uuid PK
qa_checklist_id                 uuid NOT NULL FK→qa_checklists.id ON DELETE CASCADE
template_item_id                uuid NOT NULL FK→qa_checklist_template_items.id
sequence                        int NOT NULL
item_text                       varchar(500) NOT NULL                -- copied from template at issue (immutable)
photo_required                  boolean NOT NULL                    -- copied from template
photo_required_count            int NOT NULL
is_critical                     boolean NOT NULL                    -- copied from template
response_status                 enum NOT NULL DEFAULT 'Pending'
                                  ('Pending','Pass','Fail','Not_Applicable','Returned')
response_value_text             text
response_value_numeric          decimal(12,4)
response_value_pick             varchar(100)
response_notes                  text
photo_count                     int NOT NULL DEFAULT 0
responded_by_user_id            uuid FK→users.id
responded_at                    timestamp
returned_reason                 text
linked_snag_id                  uuid FK→snags.id                    -- 4.6 — set if fail generated a snag
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (qa_checklist_id, sequence)
- INDEX (response_status) WHERE response_status IN ('Pending','Returned')
- INDEX (linked_snag_id) WHERE linked_snag_id IS NOT NULL
```

`item_text` and other template fields are *copied* at issue, not referenced live. This ensures the checklist a contractor sees doesn't change underneath them if the template is edited.

### Build `qa_photos`

```
qa_photos
─────────────────────────────────────────────
id                              uuid PK
qa_item_id                      uuid NOT NULL FK→qa_items.id ON DELETE CASCADE
caption                         varchar(500)
file_storage_backend            enum NOT NULL DEFAULT 'S3'
                                  ('S3','Azure_Blob','GCS','Local')
file_storage_key                text NOT NULL
file_thumbnail_storage_key      text
file_original_name              varchar(500)
file_mime_type                  varchar(50) NOT NULL
file_size_bytes                 bigint NOT NULL
file_width_px                   int
file_height_px                  int
file_sha256                     varchar(64) NOT NULL
exif_taken_at                   timestamp
exif_lat                        decimal(9,6)
exif_lon                        decimal(9,6)
exif_device_model               varchar(100)
uploaded_by_user_id             uuid NOT NULL FK→users.id
uploaded_at                     timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (qa_item_id, uploaded_at DESC)
- INDEX (exif_taken_at)
```

EXIF data is the audit anchor: a QA photo's claim that work was done at a particular time and place is verifiable against EXIF timestamp + GPS. Mismatch with `qa_items.responded_at` more than ±2h or distance from `qa_checklists.location_lat/lon` more than 100m raises a soft warning at submission ("photo timestamp / location doesn't match the checklist context"); doesn't block, but logged for site manager review.

### Build `qa_signoffs`

Multi-party sign-off record. Useful where two parties must endorse the same checklist (contractor submitter + site manager approver, or building control inspector + main contractor). Most checklists use a single sign-off.

```
qa_signoffs
─────────────────────────────────────────────
id                              uuid PK
qa_checklist_id                 uuid NOT NULL FK→qa_checklists.id ON DELETE CASCADE
signoff_type                    enum NOT NULL
                                  ('Contractor_Submission','Site_Manager_Approval','Inspector_Witness',
                                   'Designer_Approval','Director_Final')
signer_user_id                  uuid FK→users.id                    -- internal
signer_external_name            varchar(255)
signer_external_email           varchar(255)
signer_role                     varchar(100)                        -- "Architect" / "Building Inspector"
signature_method                enum NOT NULL DEFAULT 'Click_To_Sign'
                                  ('Click_To_Sign','Drawn_Signature','PIN','None')
signature_data                  jsonb                               -- drawn sig: { strokes: [...] }
signed_at                       timestamp NOT NULL DEFAULT now()
notes                           text

Indexes:
- INDEX (qa_checklist_id, signed_at)
```

E-signature (proper PAdES / DocuSign-style) is Future Tasks Phase 4. `Click_To_Sign` is "I attest I am [name] and I approve this" with audit log capturing the click, IP, user_id. Drawn_Signature is a finger-drawn signature on touchscreen captured as SVG strokes — visually it's a signature; legally it's marginally stronger than click-to-sign but not formally authenticated.

### Business logic

**Issuing a checklist:**

```
Site manager / project lead:
  Action: "Issue QA checklist"
  Pick template (filtered by project's active cost codes / task types)
  Pick context: project (default), related task (3.4), related subcontract (2.8a),
                related plot (7.1), location label, optional GPS pin
  Assign to: subcontractor (2.7) OR internal user
  Set due_date
  
  System:
    Create qa_checklists row with template_version = template's current version
    Copy each qa_checklist_template_items row into qa_items rows (immutable item text)
    Set total_items / items_pending counts
    Notify assignee:
      Internal: in-app notification + chat mention if in project channel
      Subcontractor (with portal user): portal notification + email
      Subcontractor (no portal user): email only with secure-link to portal
```

**Responding (contractor, via 2.9 portal or internally):**

```
Contractor opens checklist:
  Per item:
    Tap response (Pass / Fail / N/A).
    If photo_required and response = Pass: must upload photo_required_count photos.
    If response = Fail: photo strongly encouraged; notes required ≥ 10 chars.
    For Numeric/Text/Pick_One: input value.
  
  Submit checklist:
    Validate:
      - All items have a response (Pending = blocking)
      - Photo requirements met
      - Critical-failed items each have notes
    Set status = 'Submitted', submitted_at, submitted_by
    Create qa_signoffs row (signoff_type='Contractor_Submission')
    Trigger snag creation for failed items (see below)
    Notify site manager: "QA checklist [name] submitted by [contractor], ready for review"
```

**Failure → snag creation (uses 4.6):**

```
On qa_items.response_status = 'Fail':
  Create snags row (4.6) with:
    project_id, location, severity (Critical if is_critical else Medium)
    description = item_text + "\n" + response_notes
    stage = 'Pre_Handover' (default; overridable based on project status)
    raised_via = 'QA_Checklist'
    qa_item_id back-link
    photo_ids = qa_photos for this item, copied via snag_photos
  Set qa_items.linked_snag_id
  Site manager notified once snag is raised (single batch notification at checklist submission)
```

**Site manager review:**

```
Site manager opens submitted checklist:
  Sees per-item: response, photos, notes, linked snag (if any)
  Per-item action: Accept / Return (with reason)
  Whole-checklist action: Approve / Reject (with reason)
  
  Approve:
    Set status = 'Approved', approved_at, approved_by
    Create qa_signoffs row (signoff_type='Site_Manager_Approval')
    Notify contractor: "Your QA checklist [name] has been approved"
    Linked snags remain open until resolved separately in 4.6
  
  Reject:
    Set status = 'Rejected', rejection_reason
    Notify contractor with reason
    Contractor cannot re-submit a rejected checklist; new checklist must be issued
  
  Return individual items:
    Set qa_items.response_status = 'Returned' on the items
    Set qa_checklists.status = 'Returned', returned_reason
    Notify contractor: "QA checklist [name] returned for: [items list]"
    Contractor re-responds to returned items only and re-submits
```

**Offline behaviour (uses 3.2 outbox):**

```
Contractor opens checklist on phone with no signal:
  Local IndexedDB cache: full qa_items list, photos uploaded as blobs.
  All response actions work offline.
  Photos resized on capture (max 2048px, JPEG quality 85) before stash.
  
On reconnect:
  Outbox sync order: qa_items responses first, qa_photos second.
  Photo upload progress visible.
  EXIF extracted server-side after upload.
  Conflict (rare): two devices for same checklist? Last-write-wins per item; site manager review surfaces ambiguity.
```

This is one of the modules where offline matters most; checklists are often filled in unfinished buildings.

**Statutory linkage:**

QA checklists with category='Statutory' (e.g. fire compartmentation, Part L test, structural sign-off) auto-create a register entry in `document_registers` (5.3) on Approved status, tagging the relevant compliance area. The Approved signoff PDF (generated on demand) becomes the linked_document_id.

### UI

**Site manager — issue checklist** (`/projects/:id/qa/issue`):
- Template picker filtered by project's task types.
- Context selectors (task / subcontract / plot / location).
- Assignee picker.
- Due date.
- Issue button.

**Contractor — checklist response** (`/portal/qa/:checklist_id` or internal `/qa/:id`):
- Mobile-first. Each item is a card.
- Tap response, optionally photograph (camera direct), optionally note.
- Progress bar at top: "8 of 12 items responded".
- "Submit" button enabled when all items have responses + photo requirements met.

**Site manager — review checklist** (`/qa/:id/review`):
- Per item: response, photos (gallery), notes, linked snag.
- Action menu per item: Accept / Return.
- Whole-checklist: Approve / Reject.

**QA dashboard** (`/projects/:id/qa`):
- Tabs: Open Checklists | Submitted | Approved | Failed Items.
- Per-checklist row: template name, context, assignee, status, item summary.

### Permissions

- `qa_templates.view` — every internal user
- `qa_templates.create` — director, contracts manager, site manager
- `qa_templates.edit` — director, contracts manager (creates new version)
- `qa_checklists.issue` — site manager, project lead, contracts manager
- `qa_checklists.respond` — assignee user OR subcontractor portal user (own only)
- `qa_checklists.review` — site manager, project lead, contracts manager
- `qa_checklists.approve` — site manager, project lead, contracts manager, director
- `qa_signoffs.add_designer_approval` — designer (internal or via consultant portal — Phase 3)
- `qa_signoffs.add_inspector_witness` — director only (witness/audit role)

### Acceptance criteria

- [ ] Template can be created with mixed item types (Pass_Fail, Numeric, Pick_One)
- [ ] Template versioning: editing creates new version; live checklists retain original version
- [ ] Issue checklist creates qa_items copies of template items at issue time
- [ ] Photo-required items cannot be marked Pass without minimum photo count
- [ ] Critical-failed items auto-create a snag in 4.6 with Critical severity
- [ ] Non-critical-failed items create snags with Medium severity by default
- [ ] EXIF time/location mismatch with checklist context raises soft warning at submission
- [ ] Submission generates Contractor_Submission qa_signoff
- [ ] Approval generates Site_Manager_Approval qa_signoff
- [ ] Returned items can be re-responded; whole-checklist re-submitted
- [ ] Rejected checklist cannot be re-submitted; new checklist issuance required
- [ ] Statutory checklist on Approved auto-creates document_register entry (5.3)
- [ ] Subcontractor portal (2.9) can submit QA checklists for own subcontract scope
- [ ] Offline flow: respond + photograph offline, restore connection, all data syncs in correct order
- [ ] Realtime broadcast on submission / approval reaches site manager / contractor
- [ ] Mobile UX: complete a 15-item checklist with photos in under 10 minutes on a mid-range Android
- [ ] Audit log captures: issue, submission, approval, return, rejection, signoffs

### Seed data

A small set of system templates ships at first run:
- `QA-FOUND-001` — Foundation pour pre-pour checks (15 items, several photo-required)
- `QA-FRAME-001` — Timber frame erection (12 items, 4 critical)
- `QA-DPC-001` — Damp proof course continuity (8 items, photo required for each)
- `QA-FIRST-001` — First fix carcassing inspection (20 items)
- `QA-FIRST-MEP-001` — First fix MEP rough-in (18 items, 6 critical)
- `QA-INSU-001` — Insulation install + airtightness checks (10 items, photo required)
- `QA-PARTL-001` — Part L compliance evidence (Statutory category) (8 items)
- `QA-FIRE-001` — Fire compartmentation (Statutory) (12 items, all critical)
- `QA-2NDFIX-001` — Second fix completion (15 items)
- `QA-PRE-PC-001` — Pre-handover snag-out (25 items)

These are starting points; SY Homes refines per project type over time. Seed-from-spec format (YAML) so additions are easy.

### Out of scope

- E-signature (PAdES, DocuSign-style legal e-signing) — Future Tasks Phase 4.
- Witness recordings (video evidence) — out of scope; photo only for v1.
- Auto-generation of Building Control / NHBC inspection reports from approved checklists — Future Tasks Phase 4 (HMRC / Statutory connectors).
- Cross-project QA template library with import/export — Future Tasks Phase 5.
- AI-based photo analysis (does this photo show what the item asks for?) — Future Tasks Phase 5.
- Per-item checklists for design coordination (clash-detection style) — out of scope; handled via RFIs (4.4) instead.
- Inspection scheduling / calendar integration — out of scope; due_date is the simple field.
- Batched checklist issuance (issue 50 plot checklists at once) — Future Tasks Phase 3 once plot management (7.1) lands.

---

## Prompt 4.6 — Snagging and Activity Streams

**Dependencies:** 1.5, 4.5
**Tables in this prompt:** `snags`, `snag_photos`, `snag_assignments`, `activity_events`
**Estimated hours:** 10h
**Status:** NEW. Unified snagging module + generic activity-stream feed. Skeleton flagged 4.6 as candidate split; on detail review the snag side carries the substance and activity is a thin reader on a generic event table. Stays as one prompt.

Snagging is unified per the Chat 5 framing: the same workflow applies whether a defect arises mid-build, at handover, or in the defects liability period (DLP). One `snags` table with a `stage` flag distinguishes the contexts. Severity, assigned-to, photo evidence, sign-off. Activity streams piggyback on a generic `activity_events` table that every other module already writes to via the audit hook from 1.4 (extended slightly for the user-facing rendering).

### Build `snags`

```
snags
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
snag_number                     varchar(40) NOT NULL                -- "SNAG-{project_code}-001"
title                           varchar(255) NOT NULL
description                     text NOT NULL
stage                           enum NOT NULL
                                  ('In_Progress','Pre_Handover','Handover','DLP','Post_DLP')
                                  -- In_Progress: arose during construction
                                  -- Pre_Handover: arose during pre-PC walkround
                                  -- Handover: arose during PC inspection
                                  -- DLP: arose during defects liability period
                                  -- Post_DLP: rare; arose after DLP ended (usually warranty)
severity                        enum NOT NULL DEFAULT 'Medium'
                                  ('Low','Medium','High','Critical')
status                          enum NOT NULL DEFAULT 'Open'
                                  ('Open','Assigned','In_Progress','Resolved','Verified','Closed','Wont_Fix','Reopened')
location_label                  varchar(255)                         -- "Plot 12, kitchen, north wall"
location_lat                    decimal(9,6)
location_lon                    decimal(9,6)
related_plot_id                 uuid                                 -- 7.1
related_task_id                 uuid FK→programme_tasks.id           -- 3.4
related_subcontract_id          uuid FK→subcontracts.id              -- 2.8a
related_qa_item_id              uuid FK→qa_items.id                  -- 4.5 — set when QA-failure-driven
related_dlp_period_id           uuid                                 -- 7.3 — set when DLP-driven
raised_via                      enum NOT NULL DEFAULT 'Direct'
                                  ('Direct','QA_Checklist','Site_Walk','Buyer_Report','DLP_Inspection',
                                   'Snag_Walk','RFI_Driven','Inspection_Failure')
raised_by_user_id               uuid NOT NULL FK→users.id
raised_at                       timestamp NOT NULL DEFAULT now()
target_resolution_date          date
assigned_to_subcontractor_id    uuid FK→subcontractors.id            -- 2.7
assigned_to_user_id             uuid FK→users.id                     -- internal alternative
assigned_at                     timestamp
resolution_notes                text
resolved_at                     timestamp
resolved_by_user_id             uuid FK→users.id
verified_at                     timestamp
verified_by_user_id             uuid FK→users.id                     -- typically site manager
verification_notes              text
closed_at                       timestamp
closed_by_user_id               uuid FK→users.id
wont_fix_reason                 text
reopened_at                     timestamp
reopened_by_user_id             uuid FK→users.id
reopened_reason                 text
estimated_cost_to_resolve       decimal(12,2)
actual_cost_to_resolve          decimal(12,2)
backcharge_to_subcontractor     boolean NOT NULL DEFAULT false
backcharge_amount               decimal(12,2)
backcharge_actual_id            uuid FK→actuals.id                   -- 2.5; set when backcharge posted
created_at                      timestamp NOT NULL DEFAULT now()
updated_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- UNIQUE (tenant_id, snag_number)
- INDEX (project_id, status, severity)
- INDEX (assigned_to_subcontractor_id, status)
- INDEX (stage, status)
- INDEX (related_plot_id) WHERE related_plot_id IS NOT NULL
- INDEX (related_qa_item_id) WHERE related_qa_item_id IS NOT NULL
- INDEX (status, target_resolution_date) WHERE status IN ('Open','Assigned','In_Progress')
```

`snag_number` auto-generated: `SNAG-{project_code}-{seq:04d}`. Sequence per-project so a project's snag list is contiguous.

The `stage` field is the unification trick: the same status machine runs whether the snag is from a mid-build QA failure, a pre-handover walk, or a DLP defect. Reporting filters by stage when needed (e.g. "show all DLP defects on completed schemes").

### Build `snag_photos`

Same shape as `qa_photos` and `daily_log_photos`. EXIF-aware, thumbnailed, integrity-checked.

```
snag_photos
─────────────────────────────────────────────
id                              uuid PK
snag_id                         uuid NOT NULL FK→snags.id ON DELETE CASCADE
photo_role                      enum NOT NULL DEFAULT 'Evidence'
                                  ('Evidence','Resolution','Verification')
                                  -- Evidence = photo of the snag
                                  -- Resolution = photo from contractor "I fixed it"
                                  -- Verification = photo from site manager confirming fix
caption                         varchar(500)
file_storage_backend            enum NOT NULL DEFAULT 'S3'
                                  ('S3','Azure_Blob','GCS','Local')
file_storage_key                text NOT NULL
file_thumbnail_storage_key      text
file_original_name              varchar(500)
file_mime_type                  varchar(50) NOT NULL
file_size_bytes                 bigint NOT NULL
file_width_px                   int
file_height_px                  int
file_sha256                     varchar(64) NOT NULL
exif_taken_at                   timestamp
exif_lat                        decimal(9,6)
exif_lon                        decimal(9,6)
uploaded_by_user_id             uuid NOT NULL FK→users.id
uploaded_at                     timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (snag_id, photo_role, uploaded_at DESC)
```

The three photo_roles reflect the workflow: Evidence at raise → Resolution at fix → Verification at sign-off. A typical critical snag accumulates one of each.

### Build `snag_assignments`

History of assignments. Tracks the case where a snag is reassigned (e.g. raised against electrical sub, turns out to be groundworks).

```
snag_assignments
─────────────────────────────────────────────
id                              uuid PK
snag_id                         uuid NOT NULL FK→snags.id ON DELETE CASCADE
assigned_to_subcontractor_id    uuid FK→subcontractors.id
assigned_to_user_id             uuid FK→users.id
assigned_at                     timestamp NOT NULL DEFAULT now()
assigned_by_user_id             uuid NOT NULL FK→users.id
unassigned_at                   timestamp
unassign_reason                 text
target_resolution_date          date
notes                           text

Indexes:
- INDEX (snag_id, assigned_at DESC)
- INDEX (assigned_to_subcontractor_id, unassigned_at) WHERE unassigned_at IS NULL
```

The current assignment is whichever row has `unassigned_at IS NULL`. On reassignment, the previous row's `unassigned_at` is set; a new row is inserted. The `snags.assigned_to_*` columns denormalise the current assignment for query speed.

### Build `activity_events`

Generic event-log table. Every module writes to it on significant actions. The user-facing activity feed is a read query against this table filtered by project / event-type / user.

```
activity_events
─────────────────────────────────────────────
id                              uuid PK
tenant_id                       uuid NOT NULL
project_id                      uuid FK→projects.id                  -- null for cross-project events
entity_id                       uuid FK→entities.id                  -- null when not entity-scoped
actor_user_id                   uuid FK→users.id                     -- who did it; null for system
event_type                      varchar(100) NOT NULL
                                  -- e.g. 'document.uploaded', 'task.completed', 'snag.raised',
                                  --      'bill.posted', 'chat.message_pinned', 'rfi.closed',
                                  --      'qa.checklist_approved', 'subcontract.issued'
event_category                  enum NOT NULL
                                  ('Financial','Programme','Documents','Site_Ops','Sales',
                                   'Compliance','System','Communication')
target_record_type              varchar(80)                          -- 'documents', 'snags', 'rfis', etc.
target_record_id                uuid
title                           varchar(255) NOT NULL                -- "Sarah uploaded Drawing GA-001"
body                            text                                 -- optional longer description
deep_link                       varchar(500)                         -- /documents/{id} etc.
icon                            varchar(40)                          -- icon identifier for feed UI
severity                        enum NOT NULL DEFAULT 'Info'
                                  ('Info','Notable','Important','Critical')
metadata                        jsonb DEFAULT '{}'
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, created_at DESC)
- INDEX (entity_id, created_at DESC) WHERE entity_id IS NOT NULL
- INDEX (event_type, created_at DESC)
- INDEX (event_category, created_at DESC)
- INDEX (actor_user_id, created_at DESC)
- INDEX (target_record_type, target_record_id) WHERE target_record_id IS NOT NULL
```

Append-only. Cleanup is retention-based: events older than 24 months archived to cold storage (out of scope for v1; they just stay in the table). The audit_log table from 1.4 is the legal record; activity_events is the user-facing feed (a different cut of similar data — actor/action/target — with display niceties).

The schemas overlap deliberately. `audit_log` (1.4) records every state-changing action for legal replay. `activity_events` records the subset of those that are interesting to surface in feeds, with display fields (icon, title, deep_link, severity). A single trigger writes to audit_log; a configurable subset of those events also write to activity_events.

### Business logic

**Raising a snag:**

```
User raises snag (site manager / contractor / buyer / inspector):
  Form: title, description, location_label, optional GPS pin, severity, stage,
        photos (≥1 evidence photo encouraged), assigned-to (optional at raise)
  
  Auto-set stage based on context:
    If project.status = 'Live': stage = 'In_Progress' (default)
    If project.status = 'Pre_PC' or 'PC_Walkround': stage = 'Pre_Handover'
    If project.status = 'PC' or 'Handover': stage = 'Handover'
    If linked to dlp_periods (7.3) active: stage = 'DLP'
    If linked dlp ended: stage = 'Post_DLP'
  
  Auto-derive severity for QA-driven:
    If raised_via = 'QA_Checklist' AND linked qa_item.is_critical = true: severity = 'Critical'
    Else: severity = 'Medium'
  
  Generate snag_number
  Insert snags row (status='Open' or 'Assigned' if assignee set at raise)
  Insert snag_photos rows for evidence
  If assignee at raise: insert snag_assignments row, set status='Assigned'
  
  activity_events.write({
    type='snag.raised', category='Site_Ops', severity='Notable' (or 'Important' if Critical),
    title=f"{actor} raised {snag.snag_number}: {snag.title}",
    deep_link=f"/snags/{snag.id}"
  })
  
  Notify: assignee (if any), site manager, project lead
  Realtime broadcast on project channel
```

**Status flow:**

```
Open → Assigned (when assignee set; can be set at raise or after)
Assigned → In_Progress (subcontractor / internal user starts work)
In_Progress → Resolved (contractor: "I fixed it", uploads Resolution photo)
Resolved → Verified (site manager confirms fix, uploads Verification photo)
Verified → Closed (final closure, sometimes simultaneous with Verified)
Any → Wont_Fix (with reason; usually after director discussion)
Resolved / Verified / Closed → Reopened (issue recurs or wasn't actually fixed)
```

Reopening creates an audit-logged event; status returns to In_Progress (or whatever the original was).

**Backcharging:**

When `backcharge_to_subcontractor=true` and `backcharge_amount` is set, on snag close the system prompts to post an actual (2.5) of the corrective work cost as a deduction from the next valuation (2.8b) for the named subcontractor. Manual confirmation; not auto.

**Bulk snag list operations:**

For pre-handover snag walks, site managers often raise dozens at once. UI supports:
- Camera-driven rapid raise: tap photo, dictate location, set severity, save → next.
- Bulk reassignment: select N snags → assign to one subcontractor.
- Bulk status change: select N → mark Closed (with confirmation).

**DLP integration (links forward to 7.3):**

Snags raised during a project's DLP period:
- Auto-tagged stage='DLP', related_dlp_period_id set
- Counted toward DLP defect resolution KPIs (7.3 dashboard)
- Resolution before DLP end date contributes to retention release decisioning

If a DLP period ends with snags still Open (status not Closed/Wont_Fix):
- 7.3 retention release schedule prompts director to defer second-half retention release until snags resolved
- Outstanding-DLP-snag list visible on the project DLP card

**Activity feed query patterns:**

```
Project activity feed (/projects/:id/activity):
  SELECT activity_events
  WHERE project_id = :project_id
    AND created_at > :since (default last 30 days)
  ORDER BY created_at DESC
  LIMIT 100
  
Personal activity feed (/me/activity):
  SELECT activity_events
  WHERE actor_user_id = :me OR target_user_id_in_metadata = :me
    OR project_id IN (:my_project_ids)
  ORDER BY created_at DESC
  LIMIT 100

Cross-project director feed (/feed):
  SELECT activity_events
  WHERE project_id IN (:director_accessible_projects)
    AND severity IN ('Important','Critical')
    AND created_at > now() - interval '7 days'
  ORDER BY created_at DESC
```

Filters: event_category, severity, actor, date range. Saved filter views per user.

### Other modules' write hooks

Each module that should appear in the feed writes to `activity_events` on its meaningful state changes:

- **2.5 (actuals/commitments):** `bill.posted`, `po.issued`, `po.confirmed` — Financial category
- **2.6 (BCRs):** `bcr.approved`, `bcr.rejected` — Financial / Important
- **2.8a (subcontracts):** `subcontract.issued`, `variation.approved` — Financial / Notable
- **2.8b (valuations):** `valuation.certified`, `payment_notice.issued` — Financial / Notable
- **3.4 (programme):** `task.completed`, `task.delayed` (slip > 5 days) — Programme
- **3.5 (programme):** `baseline.set` — Programme / Important
- **4.1 (daily logs):** `daily_log.submitted` — Site_Ops / Info
- **4.3 (chat):** `channel.created` — Communication / Info (chat messages NOT every-message in feed; would be noise)
- **4.4 (RFIs):** `rfi.raised`, `rfi.closed`, `rfi.breached` — Communication / Notable / Important
- **4.5 (QA):** `qa.checklist_approved`, `qa.checklist_rejected` — Site_Ops / Notable
- **4.6 (snags):** `snag.raised`, `snag.closed`, `snag.reopened` — Site_Ops / Notable / Important
- **5.2 (documents):** `document.uploaded`, `document.approved`, `document.expired` — Documents / Notable
- **5.3 (compliance):** `register_item.completed`, `certificate.expired` — Compliance / Important / Critical
- **6.4 (Xero — when built):** `xero.connection_lost` — System / Critical
- **7.1 (plots):** `plot.status_changed` — Sales / Notable
- **7.2 (buyers):** `buyer.exchanged`, `buyer.completed` — Sales / Important
- **7.3 (post-completion):** `retention.released`, `dlp.ended` — Financial / Notable

The list above is enumerated here so the feed has a known, controlled set rather than every audit_log event being noise. Adding new event types is a code change accompanied by a migration; it is not user-configurable.

### UI

**Project snag list** (`/projects/:id/snags`):
- Tabs: Open | Assigned | In Progress | Resolved | Verified | Closed | All.
- Filters: stage, severity, assigned-to, raised-via, date range.
- List view: snag_number, title, location, severity badge, status pill, assignee, age.
- Map view: pins on a project site map for snags with GPS.
- Bulk actions in selection mode.

**Snag detail** (`/snags/:id`):
- Header: number, title, status, severity, stage.
- Sidebar: location, related plot/task/subcontract/QA item, raised-by/at, assignee, target date.
- Photo gallery: tabs for Evidence | Resolution | Verification.
- Timeline: status changes, assignment changes, photo uploads, comments.
- Composer: comment + status-change action.

**Snag walk mode** (`/projects/:id/snags/walk`, mobile-first):
- Designed for the pre-handover walk. Big "+ Raise snag" button.
- On tap: camera opens directly, photo taken, then form (title + location label + severity).
- After save, returns to camera view for next snag. Three-tap loop.
- Running list of today's raised snags at the bottom.

**Activity feed** (`/projects/:id/activity` and `/feed`):
- Reverse chronological list.
- Each item: icon + title + actor + time + deep-link.
- Severity-coloured left border (Info: grey, Notable: blue, Important: amber, Critical: red).
- Filters bar: category multiselect, severity, actor, date.
- "Mark as read" personal high-water mark stored per user.

### Permissions

- `snags.view` — project team (scoped), director, finance (read), buyer (own plot only — via 7.2 buyer notifications, not full snag list)
- `snags.create` — project team, contracts manager, director, **subcontractor portal user** (against own subcontract scope)
- `snags.assign` — site manager, project lead, contracts manager
- `snags.edit_own` — raiser (until status > Assigned)
- `snags.resolve` — assignee (subcontractor portal user OR internal user)
- `snags.verify` — site manager, project lead, contracts manager
- `snags.close` — site manager, project lead, contracts manager, director
- `snags.wont_fix` — director only (with reason)
- `snags.reopen` — site manager, project lead, contracts manager, director
- `snags.bulk_actions` — site manager, project lead, contracts manager
- `activity_events.view` — project team (scoped), director, finance (filtered by category)

### Acceptance criteria

- [ ] Snag raised manually: snag_number generated, status='Open' (or 'Assigned' if assignee set)
- [ ] Snag raised from QA failure (4.5): linked_qa_item_id set, severity inherited (Critical from is_critical)
- [ ] Snag raised in DLP period: stage='DLP', related_dlp_period_id set
- [ ] Status flow: Open → Assigned → In_Progress → Resolved → Verified → Closed works end-to-end
- [ ] Wont_Fix requires reason; only director can set
- [ ] Reopen creates audit event; status returns to In_Progress
- [ ] Reassignment creates new snag_assignments row; previous row's unassigned_at set
- [ ] Photo roles (Evidence / Resolution / Verification) correctly tagged at upload
- [ ] EXIF data captured on photo upload
- [ ] Snag walk mode raises snags in 3-tap loop (camera → form → save)
- [ ] Bulk reassignment of N snags works with single action
- [ ] Backcharge flag prompts actual creation (2.5) on close
- [ ] DLP outstanding snags visible on project DLP card
- [ ] Activity events written by other modules appear in feed (test: post a bill, see it)
- [ ] Feed filters by category, severity, actor, date
- [ ] Feed deep links navigate to source records
- [ ] Personal "mark as read" high-water mark works across devices
- [ ] Realtime broadcast on snag.raised / status changes reaches subscribed users via 3.1
- [ ] Audit log captures every snag state transition

### Out of scope

- Auto-categorisation of snags from photo (AI vision) — Future Tasks Phase 5.
- Snag templates / patterns ("standard snag types") with pre-filled descriptions — Future Tasks Phase 3.
- Buyer-raised snag portal (post-handover defects from homeowner) — Future Tasks Phase 3 (depends on customer-facing buyer portal which is also Phase 3).
- Cost-of-defects analytics / heatmap — Future Tasks Phase 7.
- Lessons-learned register linking common snag types to design changes — Future Tasks Phase 3.
- Weekly snag report PDF (export currently via project list export) — Future Tasks Phase 3.
- Activity events archival to cold storage — out of scope for v1; growth is gradual and 24 months is a reasonable hot-window.
- User-configurable activity event types — explicit set only; expansion is a code change.

---

## Prompt 4.7 — Labourer Portal

**Dependencies:** 1.2, 4.1, 4.2, 4.5
**Tables in this prompt:** No new tables. Reuses `users.is_portal_user` flag from 2.9 with `portal_user_type='Labourer'`. New seeded role `Labourer_Portal_User`. New seeded permissions for the labourer scope.
**Estimated hours:** 8h
**Status:** NEW.

A minimal mobile UI for labourers — separate app shell, large tap targets, almost no nesting. Features: clock in/out (4.2), view today's tasks (3.4), mark tasks complete (3.5), end-of-day summary into daily log (4.1), submit QA checklist evidence (4.5), receive safety briefings (read-and-acknowledge). No appraisals, no documents browser, no chat clutter. Forgiving of low tech literacy. Offline-capable.

### Reused infrastructure from 2.9

The portal authentication, session policy, rate limiting, field-allowlist API pattern, and invitation flow all extend the 2.9 portal infrastructure. The differences for labourers:

- `portal_user_type = 'Labourer'`
- `linked_supplier_id` and `linked_subcontractor_id` may BOTH be null (an employed labourer with no supplier link), OR `linked_subcontractor_id` may be set (a subcontractor's employee, where the labourer is also tracked under that subcontractor's CIS scope).
- Session timeout shortened further: **4 hours** (vs 8h for supplier/sub portals; vs 12h internal). Rationale: phones often lent or shared; auto-logout reduces stranger-clocking-in risk.
- Re-auth not required for routine actions (clocking, task completion) because friction kills adoption. Re-auth required only for changing personal info.
- MFA discouraged for labourers (low tech literacy, lost-phone recovery flow is heavy). Optional only.
- PWA install nudged on first login: "Add SY Homes to your home screen for faster access". Service worker caches the shell so opens are sub-second even on weak signal.

### New schema delta

```
users (further extension — building on 2.9's is_portal_user / portal_user_type)
─────────────────────────────────────────────
labourer_employer_type          enum
                                  ('SY_Homes_Direct','Subcontractor_Employed','Agency','Other')
labourer_subcontractor_id       uuid FK→subcontractors.id           -- if Subcontractor_Employed
agency_name                     varchar(255)                         -- if Agency
trade                           varchar(100)                         -- "Groundworker", "Carpenter"
cscs_card_number                varchar(50)                          -- on file
cscs_card_expires_at            date
cscs_card_type                  varchar(50)                          -- "Blue Skilled", "Gold Supervisor"
emergency_contact_name          varchar(255)
emergency_contact_phone         varchar(40)
inducted_at                     timestamp                            -- date of site induction
inducted_at_project_ids         jsonb DEFAULT '[]'                   -- per-project induction history
```

CSCS card details belong on the labourer record (each labourer has their own card, even if they work for a subcontractor). Emergency contact is required for site safety.

### Build `labourer_safety_briefings`

```
labourer_safety_briefings
─────────────────────────────────────────────
id                              uuid PK
project_id                      uuid NOT NULL FK→projects.id ON DELETE RESTRICT
title                           varchar(255) NOT NULL
content                         text NOT NULL                        -- markdown-lite, includes images via 5.2 links
attachment_document_ids         jsonb DEFAULT '[]'                   -- documents (5.2)
audience                        enum NOT NULL DEFAULT 'All_On_Site'
                                  ('All_On_Site','Subcontractor_Specific','Trade_Specific','Individual')
audience_subcontractor_id       uuid FK→subcontractors.id            -- if Subcontractor_Specific
audience_trade                  varchar(100)                         -- if Trade_Specific
audience_user_ids               jsonb DEFAULT '[]'                   -- if Individual
issued_by_user_id               uuid NOT NULL FK→users.id
issued_at                       timestamp NOT NULL DEFAULT now()
expires_at                      timestamp                            -- briefing must be re-issued
must_acknowledge_by             timestamp                            -- enforced shift-block date
created_at                      timestamp NOT NULL DEFAULT now()

Indexes:
- INDEX (project_id, issued_at DESC)
- INDEX (must_acknowledge_by) WHERE must_acknowledge_by IS NOT NULL
```

```
labourer_safety_acknowledgements
─────────────────────────────────────────────
id                              uuid PK
briefing_id                     uuid NOT NULL FK→labourer_safety_briefings.id ON DELETE CASCADE
user_id                         uuid NOT NULL FK→users.id
acknowledged_at                 timestamp NOT NULL DEFAULT now()
device_info                     jsonb
ip_address                      varchar(45)

Indexes:
- UNIQUE (briefing_id, user_id)
```

Two new tables (counted in T4 delta). Acknowledgement is one-tap "I've read this and understood" — auditable, but not legally a signed document. For higher-stakes inductions, the QA module (4.5) provides the signoff machinery instead.

### Business logic

**Invitation flow:**

```
Site manager / project lead on /people/labourers (new view) action "Invite labourer":
  Form: name, mobile, email (optional), trade, employer type, subcontractor link (if applicable),
        CSCS card number + expiry, emergency contact
  
  System:
    Create users row: is_portal_user=true, portal_user_type='Labourer',
      labourer_employer_type, labourer_subcontractor_id, etc.
    Send invitation:
      If email: portal-style invitation per 2.9 pattern, 14-day expiry
      If SMS only (no email): SMS invitation with shortcode + name+DOB confirmation
        (out of scope for v1 — email or app-store install with manual invite code; SMS
         invitation is Future Tasks Phase 3)
    First login: set password (no MFA prompt by default), accept terms, see PWA install prompt
```

**Today screen — primary surface:**

```
On open of /portal/labourer:
  Today section:
    - Clock state: clocked-in / clocked-out badge with time and project name
    - "Clock in" or "Clock out" big button (from 4.2)
    - Today's assigned tasks (from 3.4 via project assignment) — maybe 3-5 cards
    - Each card: task name, target completion date, status, "Mark complete" button
  
  Pending section (if applicable):
    - Outstanding safety briefings to acknowledge — one card each
    - Outstanding QA checklist responses needed (from 4.5) — one card each
  
  Below:
    - "End of day" button — opens end-of-day summary screen
    - "My week" link — timesheet view (read-only)
    - "My profile" link — basic info, CSCS card status, emergency contact
```

**Task completion (writes to 3.5):**

```
Labourer taps "Mark complete" on a task:
  Confirmation: "Mark [task] complete?"
  On confirm:
    POST to programme task-update endpoint (3.5) with:
      task_id, percent_complete=100, status='Complete', updated_by=labourer_user_id
    
    Programme module 3.5 may require approval before marking complete (per project setting):
      If auto-approve: task immediately Complete
      If approval required: task moves to 'Pending_Approval'; site manager confirms in 3.5
    
    activity_events written: 'task.completed', actor=labourer
    Daily log entry auto-suggested (not auto-written): "Mark [task] complete" available as a one-tap pre-fill
       for Work_Completed in 4.1 if labourer adds to daily log
```

**End-of-day summary:**

```
Labourer taps "End of day":
  Sheet opens with:
    - Auto-pulled: tasks marked complete today (read-only display)
    - Auto-pulled: hours worked today (from 4.2 clock_events)
    - Composer: "Anything else?" free text + one optional photo
  
  Submit:
    Adds entry to today's daily_log (4.1) tagged entry_type='Work_Completed' or 'Other'
       with sender_user_id=labourer
    Activity event written
    Returns to today screen with confirmation
```

The end-of-day summary is the labourer's contribution to the daily log. The site manager owns the daily log (submits it formally); labourers contribute entries. This is the key hand-off — labourers don't need to think about "the diary"; they just press "end of day" and answer one question.

**Safety briefing flow:**

```
On portal home: pending briefings shown as cards.
  Tap card → full briefing content displays (text + attached images/documents inline if PDF or image).
  At bottom: "I've read and understood" button.
  Tap → labourer_safety_acknowledgements row inserted.
  Activity event written.

If briefing.must_acknowledge_by < now() AND user has clocked in today without acknowledging:
  Block clocking in next shift until acknowledged.
  Show explanation: "Please acknowledge today's safety briefing before clocking in."
  This is the soft-block enforcement — site manager override allowed via 4.2 manual entry.
```

**QA evidence flow (when labourer is the actual subcontractor employee):**

If a QA checklist (4.5) is issued to the labourer's `linked_subcontractor`, that checklist appears in the labourer's pending list. They can respond per 4.5's mobile flow without needing the full subcontractor portal. This shortcut covers the very common case where the subcontractor is a sole trader or a small team where the on-site labourer IS the person responding to QA.

**Inductions:**

A specific subset of safety briefings tagged "Site Induction" creates a `users.inducted_at_project_ids` entry on acknowledgement. Project access is then permission-checked: a labourer can't clock in to a project they haven't been inducted to.

**Mobile-first considerations:**

- All buttons minimum 56dp tap target.
- Body font minimum 16px (browser default).
- High contrast (WCAG AA where possible).
- No multi-step modal flows; everything resolves on the same screen.
- Connectivity indicator visible: green dot online, amber syncing, grey offline with queue count.
- Offline cache: today's tasks, today's clock events, pending briefings, pending QA checklists.
- Photo upload uses camera direct, not photo library (familiar workflow on a building site).
- Voice-input field via browser-native speech-to-text where supported (PWA on Android Chrome supports this; iOS Safari does not).

### UI

**Labourer home** (`/portal/labourer`):
- Top bar: "[Site name]" or "Not on site" + connectivity indicator.
- Big clock in/out button.
- Today's tasks card stack.
- Pending action card stack.
- Bottom nav: Today | Tasks | Timesheet | Profile.

**Tasks tab:**
- Today's tasks (default).
- Switch to "All my tasks" — projects/tasks assigned in next 14 days.

**Timesheet tab:**
- This week's hours, daily breakdown.
- Read-only.
- "Last week" toggle.

**Profile tab:**
- Name, role, employer.
- CSCS card status (warning if expiring within 60 days).
- Emergency contact (editable; goes through review).
- "Sign out" link.

### Permissions

A new system role seeded: `Labourer_Portal_User` — minimal scope:

- `clock_events.create_own`
- `clock_events.view_own`
- `timesheets.view_own`
- `programme_tasks.view_assigned` — only tasks where labourer is assigned via `programme_task_assignees` (3.4 schema)
- `programme_tasks.complete_own` — mark assigned task complete (subject to 3.5 approval rules)
- `daily_log_entries.create_own` — adds to current day's log
- `qa_checklists.respond_assigned` — only checklists issued to linked_subcontractor where labourer has scope
- `qa_photos.upload_own`
- `qa_items.respond_own`
- `safety_briefings.view_assigned`
- `safety_briefings.acknowledge_own`
- `users.update_own_emergency_contact`

The `_own` and `_assigned` suffixes invoke the row-level filter pattern from 2.9 — server-side filtering at the API layer based on the user's identity and assignments, never UI-only.

### Acceptance criteria

- [ ] Labourer can be invited from /people/labourers with full required field validation
- [ ] Email invitation works (SMS deferred); first login sets password without MFA prompt
- [ ] Portal session timeout enforced at 4h
- [ ] PWA install prompt appears on first login on Android Chrome / iOS Safari (where supported)
- [ ] Today screen renders in <1s on mid-range Android over 4G
- [ ] Clock in/out works in 2 taps (already validated in 4.2)
- [ ] Assigned task list filters to tasks where labourer is in programme_task_assignees
- [ ] Mark-task-complete posts via 3.5 API with correct identity; auto-approve path tested
- [ ] End-of-day summary posts entry to today's daily_log (4.1) with tag and labourer user_id
- [ ] Safety briefing cards appear on home; acknowledgement creates row, dismisses card
- [ ] Briefing past must_acknowledge_by blocks next clock-in until acknowledged; site manager override works
- [ ] Site induction briefing acknowledgement adds to inducted_at_project_ids; un-inducted projects don't accept clock-in
- [ ] QA checklist issued to linked_subcontractor appears in pending list; can be responded to per 4.5 flow
- [ ] Photo capture uses direct camera; photos resize on capture (<2MB after resize)
- [ ] Offline: clock in, complete task, write end-of-day summary all work offline; sync on reconnect with no duplicates
- [ ] Server-side scope enforcement: API returns 404/403 if labourer attempts to access another user's records
- [ ] CSCS expiry warning appears in Profile when within 60 days
- [ ] Audit log captures all portal actions: clock, task complete, briefing ack, QA response, profile edit
- [ ] Mobile UX tested on iOS Safari (iPhone 12+, iOS 16+) and Android Chrome (4GB RAM device, Android 11+)

### Out of scope

- Native iOS / Android apps — PWA only for v1. Native is Future Tasks Phase 5 if PWA proves insufficient.
- SMS invitations — Future Tasks Phase 3 (requires SMS provider integration).
- Voice-only interaction (no-screen mode for labourers with very low literacy) — out of scope; assumes basic text reading.
- Multilingual UI — out of scope; English only. Pictographic icons used to compensate.
- Tip / appreciation / gamification (badges, streaks) — out of scope; not what this is for.
- Direct messaging between labourers and office — out of scope; chat (4.3) doesn't extend to portal users in Phase 2.
- Scheduling future tasks for self ("I'll do this on Monday") — out of scope; programme owned by site manager.
- Holiday request workflow — out of scope; tracked elsewhere.
- Health declarations / pre-shift checklists (DSE, fit-to-work) — Future Tasks Phase 5.
- Toolbox talk attendance tracking beyond safety briefings — Future Tasks Phase 5; safety briefings cover the simple case.

---

# Track 5 — Documents & Compliance

**Goal:** Bring forward the Phase 1 document store, approvals, access log, and compliance registers unchanged in shape, with only the deltas required to wire in the new Phase 2 FK targets (subcontracts from 2.8a, valuations from 2.8b, supplier documents from 2.7, plots placeholder for 7.1) and the new Phase 2 surfaces that link to documents (chat 4.3, RFIs 4.4, QA evidence 4.5, snags 4.6, daily logs 4.1). No new tables in this track. Mobile-friendly upload capability is the only meaningful UX delta, driven by the field surfaces in Track 4 needing to attach documents from phones.

**Duration:** ~3 weeks at 25 hrs/week (was 4-5 weeks in Phase 1; reduced because schemas and core flows already exist — Phase 2 work is wiring deltas, mobile upload polish, and confirming the new FK targets resolve)
**Prompts:** 3 (carried forward from Phase 1 Track 4)
**Tables added:** 0 (existing tables get FK targets activated and a few new doc-type seed rows)
**Audit checkpoint:** End of Track 5 — light self-audit only; no new modules of significant risk. Verify the cross-track wiring back into 4.3 / 4.4 / 4.5 / 4.6 actually resolves end-to-end.

### Phase 1 → Phase 2 prompt mapping

| Phase 1 prompt | Phase 2 prompt | Status |
|---|---|---|
| 4.1 Document Types and Templates | 5.1 | Carried forward + seed-data deltas |
| 4.2 Documents, Approvals, Access Log | 5.2 | Carried forward + FK target activation + mobile upload |
| 4.3 Compliance Registers, Certificates & Permits | 5.3 | Carried forward + auto-seed from QA statutory checklists |

---

## Prompt 5.1 — Document Types and Templates

**Dependencies:** 1.1, 1.2, 1.4
**Tables in this prompt:** `document_types`, `document_templates` (existing — no schema changes)
**Estimated hours:** 4h
**Status:** Carried forward from Phase 1 Prompt 4.1 with seed-data deltas only.

Reference Phase 1 brief Prompt 4.1 in full. Document types form the controlled vocabulary the rest of the platform writes against — "Drawing", "Specification", "Certificate", "Insurance Schedule", "RAMS", etc. Templates are the reusable starting points (letterhead Word docs, branded PDF cover sheets, standard RFI form).

The schemas (`document_types`, `document_templates`) are unchanged. The deltas are seed-data only — Phase 2 introduces several new document surfaces and each needs a corresponding `document_types` seed row so the type picker on upload covers them.

### Phase 2 deltas

**Schema deltas:** None.

**Seed data deltas to `document_types`:**

Add the following rows (or confirm existence — if Phase 1 implementation was generous with seed coverage some may already exist; check before INSERT):

- `QA_Evidence_Photo` — category `QA`, file types `image/*`, used by 4.5 photo uploads. Distinguishes QA-evidence photos from general-purpose photos at the type level so register filters and retention rules can target them.
- `QA_Signoff_Sheet` — category `QA`, file types `application/pdf`, used by 4.5 final signoff PDF export.
- `RFI_Attachment` — category `RFI`, file types `application/pdf,image/*,application/dwg,application/vnd.dwg`, used by 4.4. Scope covers markup PDFs, photos, and DWG references.
- `RFI_Response_Markup` — category `RFI`, file types `application/pdf`, used specifically by 4.4 markup attachments where annotated PDFs are returned by the assignee.
- `Subcontract_Document` — category `Commercial`, file types `application/pdf`, used by 2.8a subcontracts. Applies to the executed contract PDF, schedules, and any signed addenda.
- `Variation_Instruction` — category `Commercial`, file types `application/pdf`, used by 2.8a variation instructions when a formal VI document exists outside the system.
- `Variation_Supporting` — category `Commercial`, file types `application/pdf,image/*`, used by 2.8a for variation supporting evidence (subcontractor quote, photos of varied work, instruction emails).
- `Valuation_Application` — category `Commercial`, file types `application/pdf`, used by 2.8b for the subcontractor's submitted valuation application PDF.
- `Payment_Notice` — category `Commercial`, file types `application/pdf`, used by 2.8b for the issued payment notice PDF (the statutory document).
- `Pay_Less_Notice` — category `Commercial`, file types `application/pdf`, used by 2.8b for issued pay-less notices.
- `Supplier_Document` — category `Commercial`, file types `application/pdf,image/*`, used by 2.7 for delivery notes, supplier confirmations, and PO acknowledgements uploaded against `supplier_documents`.
- `Daily_Log_Photo` — category `Site_Operations`, file types `image/*`, used by 4.1.
- `Snag_Photo` — category `Site_Operations`, file types `image/*`, used by 4.6. Distinct from `QA_Evidence_Photo` because retention and access patterns differ (snag photos persist into DLP, QA photos lock at signoff).

**Seed data deltas to `document_templates`:**

Add the following templates if not already present from Phase 1 (some may exist):

- `Payment_Notice_Template` — Word/HTML template for the statutory payment notice with merge fields for paying party, payee, sum due, basis for sum, due date, final date for payment. Used by 2.8b PDF export.
- `Pay_Less_Notice_Template` — equivalent for pay-less notices.
- `Variation_Instruction_Template` — Word/HTML template for VI issuance if SY Homes elects to use a formal in-system VI document rather than email instruction.
- `RFI_Response_Cover_Sheet` — branded PDF cover sheet wrapping the RFI Q&A and any attachments into a single deliverable.

The two payment-notice templates are the only seed-data items where the wording itself carries legal weight — the statutory notice phrasing flagged in session 3 for a UK QS / construction solicitor consult applies to both. **Do not finalise wording in 5.1 build; wording is locked during 2.8b build only after solicitor consult lands.** 5.1 builds the template *records* with placeholder body text and a `requires_legal_review` flag set true; 2.8b updates the body when the consult completes.

### Cross-track wiring

- 5.1 must complete before 4.3 (chat) and 4.4 (RFIs) and 4.5 (QA) and 4.6 (snags) attempt to write document records, because those modules pick `document_type_id` from the seeded list. Track 5 schedule places this before T4's tail-end builds — **but T4 in calendar terms ships earlier than T5**. Resolution: the seed rows above are added to the migration sequence at the *Phase 1 Prompt 4.1 build* (i.e. they ride into the existing `document_types` seed). Phase 2 only checks the rows are present; it does not gate T4 on T5.
  - Action: when Phase 1 Track 4 ships (already-built territory), confirm seed-row coverage. If a row is missing, add it via a small migration during the Phase 2 module that needs it, not during 5.1.
- 5.1 ships unchanged seed-row IDs; module code in 4.x references types by `code` (varchar) not by `id` (uuid) so seed UUIDs don't have to be hardcoded in app code.

### Acceptance criteria

- [ ] All Phase 2 seed `document_types` rows present and queryable by `code`
- [ ] All Phase 2 seed `document_templates` rows present, with `requires_legal_review = true` on the two payment-notice templates
- [ ] Document type picker on upload (existing UI from Phase 1) shows new types in correct categories
- [ ] No regression: existing Phase 1 type usage (Drawing, Specification, Insurance, etc.) unaffected
- [ ] Changelog entry: "Phase 2 added N document types and M document templates; payment-notice template body deferred to 2.8b post-solicitor consult"

### Out of scope

- Schema changes to `document_types` or `document_templates` — none in Phase 2.
- Template editor UI for end-users to edit template bodies — Future Tasks Phase 5; admin edits via DB / admin tool only for now.
- Auto-detect document type from file content (ML classification) — Future Tasks Phase 5.

---

## Prompt 5.2 — Documents, Approvals, Access Log (Phase 2 wiring + mobile upload)

**Dependencies:** 1.1, 1.2, 1.4, 5.1, plus *target tables active*: 2.7 `supplier_documents`, 2.8a `subcontracts`, 2.8b `valuations`, 7.1 `plots` (if 7.1 has built; if not, FK stays NULLable as in Phase 1).
**Tables in this prompt:** `documents`, `document_approvals`, `document_access_log` (existing — schema deltas only)
**Estimated hours:** 6h
**Status:** Carried forward from Phase 1 Prompt 4.2 with FK target activation and mobile upload UX deltas.

Reference Phase 1 brief Prompt 4.2 in full. The `documents` table is the central blob-pointer with metadata, version history, supersedes/superseded-by chains, file-storage abstraction (S3 / Azure / GCS / Local), SHA256 integrity check, page count, thumbnail URL, and `access_restriction` enum (`Public`, `Project_Team`, `Office_Only`, `Director_Only`, `Custom`). `document_approvals` records review/approval workflow with approver chains. `document_access_log` records every read/download with user_id, timestamp, IP, user_agent.

### Phase 2 deltas

**Schema deltas to `documents`:**

The Phase 1 schema already declared placeholder FK columns for `related_subcontract_id`, `related_valuation_id`, `related_plot_id` with the comment "Phase 4" / "Phase 5". Phase 2 activates these:

```
documents (delta only — full schema in Phase 1 Prompt 4.2)
─────────────────────────────────────────────
related_subcontract_id          uuid FK→subcontracts.id           -- ADD FK constraint (was placeholder)
related_valuation_id            uuid FK→valuations.id             -- ADD FK constraint (was placeholder)
related_supplier_document_id    uuid FK→supplier_documents.id     -- NEW column (Phase 1 didn't anticipate)
related_rfi_id                  uuid FK→rfis.id                   -- NEW column for 4.4 wiring
related_qa_checklist_id         uuid FK→qa_checklists.id          -- NEW column for 4.5 wiring
related_qa_signoff_id           uuid FK→qa_signoffs.id            -- NEW column for 4.5 final signoff PDFs
related_snag_id                 uuid FK→snags.id                  -- NEW column for 4.6 wiring
related_daily_log_id            uuid FK→daily_logs.id             -- NEW column for 4.1 wiring
related_plot_id                 uuid FK→plots.id                  -- ADD FK constraint IF 7.1 has shipped;
                                                                  -- otherwise leave as nullable uuid w/o FK
                                                                  -- and add FK constraint in 7.1 build

Indexes (additions):
- INDEX (related_subcontract_id) WHERE related_subcontract_id IS NOT NULL
- INDEX (related_valuation_id) WHERE related_valuation_id IS NOT NULL
- INDEX (related_rfi_id) WHERE related_rfi_id IS NOT NULL
- INDEX (related_qa_checklist_id) WHERE related_qa_checklist_id IS NOT NULL
- INDEX (related_snag_id) WHERE related_snag_id IS NOT NULL
- INDEX (related_daily_log_id) WHERE related_daily_log_id IS NOT NULL
- INDEX (related_supplier_document_id) WHERE related_supplier_document_id IS NOT NULL
```

**Note on multi-FK pattern:** the Phase 1 design uses one row in `documents` with multiple nullable FK columns ("polymorphic-by-multiple-columns"). This persists in Phase 2 for consistency — *do not* migrate to a single `linked_entity_type` + `linked_entity_id` polymorphic pattern. Reasoning: explicit FK columns give us referential integrity at the DB level, and document-to-many relationships are rare (most docs link to one project, optionally one subcontract OR one valuation OR one plot — not all three). The cost of a wide nullable column set is acceptable given the read patterns.

**Schema deltas to `document_approvals`:** None. Existing approval chain works for new document types.

**Schema deltas to `document_access_log`:** None. Existing access logging captures the new contexts unchanged.

**No deltas to file-storage backend, integrity check, or access-restriction enum.**

### UX delta — mobile upload

Phase 1 upload UX assumed desktop file picker. Phase 2 adds:

- **Camera-first upload** for `image/*` document types when initiated from mobile surfaces (4.1, 4.4, 4.5, 4.6 portals and labourer 4.7) — opens camera directly, captures, resizes (target <2MB after resize, longest edge 1920px), uploads with progress, attaches.
- **Multi-file mobile upload** for the same surfaces — pick or capture up to 10 files in one go, each gets its own `documents` row with the same `related_*` FKs and `access_restriction` inherited from the parent context.
- **Offline document upload queue** — tied to 3.2 offline behaviour. Documents captured offline get a temp local id; on sync, the upload completes via the same multipart endpoint. If the file-storage backend round-trip fails (S3 returns error), queue retries with exponential backoff up to 24h before alerting the user.
- **EXIF capture on mobile photo upload** — preserve `exif_capture_time`, `exif_gps_lat`, `exif_gps_lng` on the `documents` row (or a child `document_exif` row if Phase 1 didn't already have it; check before adding). 4.5 EXIF mismatch warnings (already specified) read these fields.

### Cross-surface document linking from 4.3 (chat) and 4.4 (RFIs)

Chat (4.3) and RFI (4.4) both allow attaching a document that already exists in the document store (link, not re-upload). When this happens:

- A `chat_attachments` row is created (in 4.3) referencing `documents.id`. The chat attachment carries no copy of the file.
- An `rfi_attachments` row in 4.4 likewise references `documents.id`.
- The receiving viewer attempts to render the document. If the viewer's user has read access per `documents.access_restriction`, render. **If not, render the attachment row with a "Restricted document" placeholder and a `request_access` button** rather than failing silently or revealing the file metadata. This is an access-control consistency requirement — if a director attaches a `Director_Only` document into a project chat, project members see it as "restricted", not as a broken link.
- `document_access_log` writes a `access_attempt_denied` row for the failed-access case so admin audit can see who tried to open what.

### Acceptance criteria

- [ ] `related_*` FK columns added to `documents` for all Phase 2 link targets
- [ ] FK constraints active for tables that exist at 5.2 build time (subcontracts, valuations, supplier_documents, rfis, qa_*, snags, daily_logs); plot FK left as nullable uuid until 7.1 ships
- [ ] Indexes on each new `related_*` column applied
- [ ] Mobile camera capture works on iOS Safari and Android Chrome with image resize <2MB
- [ ] Multi-file mobile upload (up to 10) works in a single user gesture
- [ ] Offline upload queue persists captures across app close/reopen and syncs on reconnect
- [ ] EXIF capture time and GPS preserved on photo uploads from mobile (where available — desktop browser uploads typically strip EXIF; that's acceptable)
- [ ] Restricted-document rendering in chat/RFI attachment surfaces shows placeholder + request-access affordance, not an error
- [ ] `document_access_log` records `access_attempt_denied` for restricted access attempts
- [ ] No regression: existing Phase 1 desktop upload, version supersession, approval chain, and access log unchanged
- [ ] FFC of existing document records intact post-migration (fresh integrity check on a random sample of 50 existing documents — SHA256 still matches stored file in S3)

### Out of scope

- Polymorphic refactor of document-link FKs into a single (entity_type, entity_id) pair — explicitly rejected, see "Note on multi-FK pattern" above.
- File preview/render in mobile browser for non-image, non-PDF types (DWG, RVT, native Word) — out of scope; download-only on mobile.
- Inline PDF annotation/markup tooling — Future Tasks Phase 4 (referenced in 4.4 RFI markup attachments — markup is created in external tools, uploaded as a new `RFI_Response_Markup` PDF).
- Real-time collaborative document editing (Office 365 / Google Docs style co-editing) — out of scope.
- Document OCR for scanned PDFs — out of scope; Future Tasks Phase 5 if a use case emerges.
- Document-level e-signature workflow integration (DocuSign etc.) — out of scope; Future Tasks Phase 4. SY Homes currently handles e-sign externally and uploads the signed PDF.
- Cross-project document sharing (one document linked to multiple projects) — out of scope; if needed, upload as a new document with appropriate `related_project_id` per copy. Cost of duplication acceptable given low frequency.

---

## Prompt 5.3 — Compliance Registers, Certificates & Permits (Phase 2 wiring)

**Dependencies:** 1.1–1.7, 5.1, 5.2, plus 4.5 if 4.5 has built (auto-seed wiring depends on it).
**Tables in this prompt:** `document_registers`, `certificates_and_permits` (existing — no schema changes)
**Estimated hours:** 4h
**Status:** Carried forward from Phase 1 Prompt 4.3 with auto-seed wiring from 4.5 only.

Reference Phase 1 brief Prompt 4.3 in full. `document_registers` is the per-project compliance check-list (CDM, BSA, Part L/O/Q, Warranty, Fire Safety, GDPR, Planning Discharge, Building Control, Insurance, Certificates, Contract) with required-by-stage gating, responsible-party tracking, blocker flags for stage progression, and waiver workflow. `certificates_and_permits` covers entity-level and project-level certificates (Building Regs, Fire, Gas Safe, Electrical, EPC, etc.) with expiry tracking, renewal alerts, and supplier issuer details.

The schemas are unchanged. The Phase 2 delta is the auto-seed wiring from 4.5 statutory QA checklists.

### Phase 2 deltas

**Schema deltas:** None.

**Auto-seed wiring from 4.5:**

When a `qa_checklists` row is created (4.5) where the underlying `qa_checklist_templates.is_statutory = true`, automatically create a corresponding `document_registers` row:

```
On qa_checklists INSERT WHERE template.is_statutory = true:
  INSERT INTO document_registers (
    project_id,
    register_type,           -- mapped from template.statutory_register_type
                             -- (e.g. 'Building_Control', 'Fire_Safety', 'Part_L')
    register_item_code,      -- generated as "{register_type}-{template.short_code}-{plot/area_id}"
    register_item_name,      -- copied from template.name
    description,             -- copied from template.description
    required_by_stage,       -- copied from template.required_by_stage
    required_document_type_id, -- the QA_Signoff_Sheet doc type from 5.1
    responsible_party,       -- copied from template.responsible_party
    responsible_user_id,     -- the qa_checklists.assigned_user_id
    linked_document_id,      -- NULL initially; populated when QA signoff PDF is generated
    status,                  -- 'In_Progress'
    is_blocker,              -- copied from template.is_blocker_for_stage
    notes,                   -- "Auto-seeded from QA checklist {qa_checklists.id}"
    display_order
  )

On qa_checklists status change to 'Signed_Off':
  UPDATE document_registers
  SET status = 'Completed',
      completed_at = NOW(),
      linked_document_id = (the qa_signoff_pdf documents.id)
  WHERE notes LIKE 'Auto-seeded from QA checklist {qa_checklists.id}%'
```

**`qa_checklist_templates` schema delta** (back-reference to 4.5 — note here for completeness):

```
qa_checklist_templates (delta — confirm 4.5 build includes these fields)
─────────────────────────────────────────────
is_statutory                boolean NOT NULL DEFAULT false
statutory_register_type     enum NULL    -- maps to document_registers.register_type;
                                         -- required if is_statutory = true
statutory_register_code     varchar(20) NULL  -- short code, e.g. "BR-DRAINS"
is_blocker_for_stage        boolean NOT NULL DEFAULT false
                                         -- if true, the auto-seeded register row carries
                                         -- is_blocker = true
```

These three fields are part of 4.5's `qa_checklist_templates` schema — listed here as well so the wiring contract is explicit. **If 4.5 build does not include these fields, raise the gap during 5.3 build and either backfill in 4.5 or add a small migration in 5.3.** Preference: backfill in 4.5 because templates are versioned and adding fields after seed introduces version-skew complexity.

### Cross-track wiring

- 5.3 should build *after* 4.5, because 5.3 wires off 4.5's events. If T5 calendar slots before 4.5 ships (per skeleton timeline T5 sits between T4 and T6 — i.e. T4 and T5 ship roughly in parallel), the auto-seed handler is built but tested with stub events until 4.5 is integrated.
- 5.3 register `Certificates` type can carry references to `certificates_and_permits.id` via `linked_document_id` indirection — no schema delta needed for this; existing Phase 1 design supports it.

### Acceptance criteria

- [ ] `qa_checklists` INSERT trigger / application-layer hook creates `document_registers` row for statutory checklists
- [ ] `qa_checklists` status change to `Signed_Off` updates the linked register row to Completed and links the signoff PDF
- [ ] `register_item_code` generation produces unique codes per project (no collisions)
- [ ] `is_blocker` flag propagates correctly from template to register row
- [ ] If `qa_checklist_templates.is_statutory = true` but `statutory_register_type` is NULL, validation rejects template save with a clear error
- [ ] Compliance register UI (existing from Phase 1) renders auto-seeded rows alongside manually-seeded rows with no visual difference (both legitimate)
- [ ] No regression: existing Phase 1 manual register seeding, certificate expiry alerts, and waiver workflow unaffected
- [ ] Changelog entry: "Phase 2 wired auto-seed of document_registers from statutory QA checklists"

### Out of scope

- Auto-seed from any 4.x module other than 4.5 (e.g. snags, RFIs) — out of scope; only QA statutory checklists carry the regulatory-evidence semantics that warrant register entries.
- Bidirectional sync (changing a register row updates the underlying QA checklist) — out of scope; the QA checklist is the source of truth, the register is a derived view.
- Statutory register coverage matrix UI ("which CDM items don't have a checklist yet?") — out of scope; Future Tasks Phase 4. Coverage gaps surface via existing register status alerts (Required + overdue).
- BSR (Building Safety Regulator) gateway submission integration — out of scope; submissions remain manual / external.
- Building Control portal API integration — out of scope.
- BIM / IFC model linkage to certificates — out of scope.

---

# Updates required to skeleton

The skeleton (`SY_Homes_Emergent_Brief_Phase2.md`) references one-paragraph descriptions for Tracks 4 and 5. After this detail document merges, the following skeleton edits are required.

## Track 4 — Site Operations

- **Prompt count:** confirmed at **7 prompts** (matches skeleton).
- **Tables added:** confirmed at **17 new tables** (matches skeleton's "~17" estimate exactly): `daily_logs`, `daily_log_entries`, `daily_log_photos`, `daily_log_weather_snapshots`, `clock_events`, `geofences`, `timesheets`, `timesheet_entries`, `clock_corrections`, `chat_channels`, `chat_channel_members`, `chat_messages`, `chat_threads`, `chat_attachments`, `chat_reads`, `chat_mentions`, `rfis`, `rfi_responses`, `rfi_attachments`, `qa_checklist_templates`, `qa_checklist_template_items`, `qa_checklists`, `qa_items`, `qa_photos`, `qa_signoffs`, `snags`, `snag_photos`, `snag_assignments`, `activity_events`, `labourer_safety_briefings`, `labourer_safety_acknowledgements`. (Recount: 31 tables, not 17 — skeleton estimate was understated. Update skeleton T4 row to "~31 tables".)
- **Duration:** confirmed at ~14 weeks at 25 hrs/week (sum of prompt-level estimates: 10+10+14+8+12+10+8 = 72h; plus integration/testing buffer; matches skeleton range).
- **Audit checkpoint added:** mid-track checkpoint after 4.3 (chat) ships, with MD/Louise/CM/site manager review of operational fit. Add to skeleton.
- **Out-of-scope additions to flag at track level:** WhatsApp displacement is operational not technical (4.3); external-party chat access deferred (4.3); native mobile apps deferred (4.7); SMS invitations deferred (4.7); programme stretch per labourer-task-completion deferred (4.7).

## Track 5 — Documents & Compliance

- **Prompt count:** confirmed at **3 prompts** (matches skeleton).
- **Tables added:** **0 new tables**. Skeleton may have estimated otherwise — correct to "0 new tables; existing Phase 1 tables receive FK target activation and seed-row deltas only".
- **Duration:** **3 weeks** at 25 hrs/week (revised down from skeleton's likely 4-5 week estimate inherited from Phase 1 — the deltas are lighter than full builds).
- **Audit checkpoint:** light only; combined with end-of-T6 audit if calendar permits.
- **Cross-track wiring note:** seed-data deltas in 5.1 may need to ride into the existing Phase 1 Track 4 seed if Phase 1 has not yet shipped at the time T4 (Phase 2) modules need them. Track this as a build-order dependency, not a Phase 2 schema gap.

## Brief-level

- **Total prompts:** confirmed at **44** (10 + 5 + 7 + 3 + ... pending sessions 4b for T6+T7+T8). T4+T5 contribution is 10 prompts. No further splits in this session.
- **Total new tables (T4+T5):** ~31 (T4 only; T5 adds zero).
- **No new architectural decisions in this session** — all decisions inherited from session 3 (WebSockets, last-write-wins, 2.8 split) and the pre-decisions from session 4 opener (snagging unified, public API rate-limited no-auth, designer engaged ahead of T8). Pre-decision on snagging confirmed during 4.6 drafting — no clear seam between snagging and activity_events emerged that justified a split.

## Pending for session 4b (separate chat)

- Tracks 6 (Xero connector — 4 carried-forward from Phase 1 Track 5 + 1 NEW for 6.1 CSV framework), 7 (~12 new tables across 4 NEW prompts), 8 (3 NEW prompts, no new tables). Same depth and pattern as this document.
- Updates required to skeleton from session 4b will be appended in the corresponding closing section of that document.

## Pending non-detail items (carried from prior sessions, not session 4 work)

- v2 of `SY_Homes_Data_Model.xlsx` reflecting the new Phase 2 tables (~50 new total once T4+T5+T6+T7+T8 land). Estimated 3-4h, after session 4b completes.
- Project Instructions edit-in-place: prompt count 25 → 44, timeline 10-14 months, Future Tasks reordering. After session 4b.
- UK QS / construction solicitor consult on statutory payment-notice wording (£200-400, ~1 week lead). Blocks 2.8b deployment, not spec. Schedule before T2 ships in build.
- CIS reverse charge VAT interaction with Xero CIS module — re-validate during 6.4 detail in session 4b.
- Cutover plan for Buildertrend retirement — T8 / separate planning doc.

---

<!-- ================================================================
     END OF SESSION 4a OUTPUT
     ================================================================
     Word count target: matched session 3 depth on new prompts (4.1-4.7)
                        and Phase-1-reference depth on carried-forward
                        prompts (5.1-5.3).
     Status: Ready to merge into SY_Homes_Emergent_Brief_Phase2.md
             at skeleton sections covering Tracks 4 and 5.
     Next: Session 4b in fresh chat covers T6 + T7 + T8.
     ================================================================ -->
