# SY Hub — Engineering Invariants

Cross-chat invariants and conventions. Each entry traces back to the chat
that surfaced it; when in doubt, follow the entry verbatim.

---

## Chat 19C — AI Capture Review Surface (2026-02-17)

### Blob-URL lifecycle for binary fetches

When a React component fetches binary data (e.g. an attachment) via
`api.get(url, { responseType: 'blob' })` and wraps it as an object URL,
the cleanup pattern MUST be:

```js
useEffect(() => {
  let revoke = null;
  let cancelled = false;
  setBlobUrl(null);
  (async () => {
    try {
      const res = await api.get(url, { responseType: 'blob' });
      if (cancelled) return;
      const u = URL.createObjectURL(res.data);
      revoke = u;
      setBlobUrl(u);
    } catch (e) { if (!cancelled) setErr(...); }
  })();
  return () => { cancelled = true; if (revoke) URL.revokeObjectURL(revoke); };
}, [keyId]);
```

The `cancelled` guard is **mandatory**, not optional — the fetch is
unawaited inside the effect, so a quick navigate-back during the in-flight
request would otherwise call `setState` on an unmounted component.
Reference: `frontend/src/components/ai-capture/AttachmentPreview.jsx` (E11).

### Hooks-above-perm-gate

React's rules-of-hooks reject conditional hook calls. The correct pattern
for permission-gated data-fetching pages is:

```jsx
const { data, isLoading } = useThing(id, {
  enabled: !!id && canViewThing(me),       // gate the fetch via enabled
});
if (!canViewThing(me)) return <NoPerm />;  // early-return AFTER hook call
```

Never put the perm-gate early-return *above* the `useQuery`/`useMutation`
call — CRA flags it as a runtime error in strict mode. Reference:
`frontend/src/pages/CaptureJobDetail.jsx` (E13), and the same pattern in
chat-19B `frontend/src/pages/projects/ActualDetail.jsx`.

### BudgetLinePicker stubbing convention in Jest

The real `BudgetLinePicker` runs `api.get('/v1/projects/:id/budgets/...')`
responses through chat-19B's actuals Zod schemas. Mocking the budget
endpoints in a Jest test for a *different* component (e.g. `PromoteForm`)
triggers cascading schema drift errors that don't reflect the production
surface.

The convention is:

1. **Stub `BudgetLinePicker` at `jest.mock` top-of-file** in any test that
   exercises a parent that embeds it (e.g. `PromoteForm.test.jsx`).
2. **UUIDs in the stub options MUST be real v4-shape.** The schemas
   validate `project_id`, `entity_id`, `budget_line_id` as
   `z.string().uuid()`. Short ids like `bl-1` silently fail validation
   and block POST — masking the very payload assertion the test is making.
3. **Exercise the real picker only in chat-19B's `CreateActualSheet`
   integration test** (`frontend/src/pages/projects/__tests__/ActualsList.test.jsx`).

Reference: `frontend/src/components/ai-capture/__tests__/PromoteForm.test.jsx`
§R6.5 H11 (E12).

### Postmark inbound seed hoisting

The HMAC signature for a Postmark inbound webhook seed must be computed
once with the process-loaded `POSTMARK_INBOUND_SECRET`. Inlining the seed
into a per-spec `beforeAll` risks the secret being read mid-suite and
producing inconsistent signatures.

Convention: Postmark seeds live in `frontend/e2e/global-setup.ts` and are
bound to a fixed supplier name keyed off `Date.now()` for idempotency
across full-suite re-runs. Reference: chat-19C §R7 (E15).

---

## Chat 19B carry-forwards (2026-02-15)

These were surfaced in chat-19B and remain canonical:

- **React Router routes must remain flat siblings in App.js.** Do NOT
  nest actuals/payments/capture routes under `ProjectDetail`. They are
  separate page-level routes reached via Link from the project tab strip.
- **`fmtGBP(value)` for ALL money rendering.** `lib/format.js`. Pass it
  `null | undefined | "1234.56"` → `—` / `—` / `£1,234.56`.
- **D32 status comma-split contract.** `ActualsListFilters.status`
  accepts `"Posted,Disputed"`. Validator rejects unknown values 422
  (wrapped via `_actuals_filters_dep` to avoid 500). DO NOT regress.
- **`canPostDraft` uses `actuals.edit`, not `actuals.approve`.** The
  router docstring's "actuals.post" label is documentation-only; the
  decorator uses `actuals.edit`. PM holds `actuals.edit` and MUST see
  Post button.
- **`react-dropzone@^14` ref override.** v14 hardcodes its internal ref;
  React's `onPaste` must be attached to the wrapper *after* spreading
  `getRootProps()`.
- **`BulkPayDialog` snapshot pattern.** Dialog freezes its `actuals`
  prop into local snapshot state at open-time, because the parent's
  `onComplete(succeededIds)` shrinks the selection mid-display.

---

## Chat 19A carry-forwards (2026-02-15)

- **`POSTMARK_INBOUND_ENABLED=false` in production `.env`.** Sandbox/E2E
  override is `true`; production cutover is B23.
- **9 audit_action enum values added.** Post, Mark_Paid, Void, Dispute,
  Undispute, Release_Retention, Add_Attachment, Remove_Attachment,
  Promote_From_Capture.
- **`actuals.admin` is sensitive.** Finance inherits; PM does NOT.

---

## Earlier chats

See `docs/SY_Hub_2.3_Checkpoint3_Handoff.md` and
`docs/SY_Hub_Pre_2_4_Cleanup_Build_Pack.md` for pre-2.4 invariants.
