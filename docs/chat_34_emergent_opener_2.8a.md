SY-Hub Prompt 2.8a — Subcontracts & Variations. Backend-only. Push-to-main.
The full Build Pack is the attached file
BuildPack_2.8a_Subcontracts_Variations.md — follow it verbatim. This message
is the kickoff only; the Build Pack is authoritative on every detail.

PRE-FLIGHT (pod may have recycled):
1. bash /app/scripts/provision_postgres.sh
2. pip install -r /app/backend/requirements.txt --break-system-packages -q
3. cd /app/backend && set -a; source /app/backend/.env; set +a; python -m app.bootstrap   (rc=0)
WARM-DB: first pytest run on a fresh pod throws ~90 seed IntegrityErrors.
ALWAYS double-run pytest; trust the 2nd run only.

START AT §R0 (pre-flight STOP gate). Do NOT write code until all 8 items are
confirmed against main and deltas reported. Key verifies: alembic HEAD
(expect 0036_budget_changes), that purchase_orders has the columns named,
that budget_changes.create_bcr accepts source_variation_id (2.6 stub, NO FK
yet — this pack adds it), that suppliers.supplier_type has 'Subcontractor'
(2.7), and the PO numbering-helper pattern to mirror. Permission baseline
expect 112. If anything differs materially, HALT and report.

This build REUSES machinery — do NOT reimplement BCR logic. A BudgetChange
variation calls the EXISTING create_bcr(change_type='Adjustment',
source_variation_id=...). The generated BCR is a normal Draft BCR with its
own approve/apply lifecycle — do NOT auto-apply it. The 2.6 self-approval
guard carries through: the BCR creator (= variation approver) cannot
self-approve the generated BCR above threshold; that's intended SoD.

Scope locked. No frontend. No 2.8b (valuations/payment-notices/retention/CIS
— retention_pct + cis_applies are stored but UNUSED this pack). Decline scope
additions; log ideas to backlog.

CRITICAL — name test files EXACTLY per §R5. Do NOT consolidate into one file
(the 2.6 single-file miss caused a partial push and a rework — must not
recur).

At session end: write CHANGELOG entry + docs/chat-summaries/chat-34-closing.md
as part of the save, THEN stop for the operator to push via Save to GitHub.
Report commit SHAs. "Committed" ≠ "pushed". End with the self-report block
exactly as specified.
