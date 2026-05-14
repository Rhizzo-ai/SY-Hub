#!/bin/bash
# /app/scripts/seed_demo_budget.sh
#
# Deterministic demo-data seed for the budgets module — committed to
# repo so it survives pod recycles (cf. /app/scripts/provision_postgres.sh).
#
# Critical lesson from Chat 17 E13 (post-R8 click-test bug):
# Always set `ftc_method = 'Budget_Remaining'` on seeded budget_lines.
# Setting `ftc_method='Manual'` with `forecast_to_complete=0` made
# every line FFC=0 → variance=-100% Red, which doesn't represent any
# realistic real-world Draft-budget state.
#
# `Budget_Remaining` mode = "for an un-spent line, FTC equals
# (current_budget − actuals − committed)" — which collapses to
# current_budget on a fresh Draft. FFC then equals current_budget,
# variance is 0, all pills Green. That's what finance expects to see
# on a freshly-cloned Draft.
#
# Usage:
#   bash /app/scripts/seed_demo_budget.sh
#   E2E_PROJECT_ID=... bash /app/scripts/seed_demo_budget.sh [flags...]
#
# Flags (chat-18, Prompt 2.4B-ii):
#   --with-v2-lineage     seed v1 Superseded + v2 Draft chain
#   --empty-project       seed E2E_EMPTY_PROJECT_ID with NO budgets
#   --extra-appraisal     seed an un-linked Approved appraisal (with cloned cost lines)

set -euo pipefail

PROJECT_ID="${E2E_PROJECT_ID:-b2a265ef-dc30-4779-96f6-e139d1881e07}"
EMPTY_PROJECT_ID="${E2E_EMPTY_PROJECT_ID:-c2e4a3f1-1111-4000-8000-000000000002}"

WITH_V2_LINEAGE=0; WITH_EMPTY_PROJECT=0; WITH_EXTRA_APPRAISAL=0
for arg in "$@"; do
  case "$arg" in
    --with-v2-lineage) WITH_V2_LINEAGE=1 ;;
    --empty-project) WITH_EMPTY_PROJECT=1 ;;
    --extra-appraisal) WITH_EXTRA_APPRAISAL=1 ;;
    *) echo "[seed-demo-budget] unknown flag: $arg" >&2; exit 2 ;;
  esac
done

PSQL="PGPASSWORD=syhomes_dev /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U syhomes -d syhomes -tq"

# ─── Wipe MFA + ensure demo project exists ───────────────────────────
eval "$PSQL" <<SQL
UPDATE users SET mfa_enabled=false, mfa_method=NULL,
  mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
  mfa_enrolled_at=NULL, failed_login_attempts=0,
  locked_until=NULL, lockout_level=0
WHERE email LIKE 'test-%@example.test';

INSERT INTO projects (
  id, project_code, name, project_type, primary_entity_id, land_ownership_method,
  site_address, site_postcode, created_by_user_id
) VALUES (
  '${PROJECT_ID}',
  'SY-DEMO-' || substr('${PROJECT_ID}', 1, 6),
  'SY Demo Project', 'Dev_Build',
  (SELECT id FROM entities LIMIT 1), 'Direct_Purchase',
  '1 Demo Street, Shrewsbury', 'SY1 1AA',
  (SELECT id FROM users WHERE email='test-pm@example.test')
) ON CONFLICT (id) DO NOTHING;
SQL

# ─── Base seed: v1 Draft budget + 3 lines + 2 items on line 1 ────────
eval "$PSQL" <<SQL
DO \$\$
DECLARE
  v_project_id uuid := '${PROJECT_ID}';
  v_user_id uuid; v_appraisal_id uuid; v_b_id uuid;
  v_entity_id uuid; v_cc_ids uuid[]; v_line_id uuid;
BEGIN
  IF EXISTS (SELECT 1 FROM budgets WHERE project_id=v_project_id) THEN
    RAISE NOTICE 'demo budget already present on % — skipping base seed', v_project_id;
    RETURN;
  END IF;

  SELECT id INTO v_user_id FROM users WHERE email='test-pm@example.test';
  SELECT primary_entity_id INTO v_entity_id FROM projects WHERE id=v_project_id;

  INSERT INTO appraisals (
    name, project_id, status, reference_date,
    land_purchase_price, sdlt_category, developer_relief,
    contingency_pct, target_profit_on_cost_pct, target_profit_on_gdv_pct,
    project_duration_months,
    gdv_total, total_acquisition_cost, total_build_cost, total_professional_fees,
    total_statutory_cost, total_finance_cost, total_contingency,
    total_sales_cost, total_other_cost, total_cost,
    profit_total, profit_on_cost_pct, profit_on_gdv_pct,
    rlv_enabled, rlv_target_basis, rlv_target_value, computation_metadata, is_stale,
    created_by_user_id, appraisal_group_id, is_current, scenario, version_number
  ) VALUES (
    'Demo Appraisal v1', v_project_id, 'Approved', CURRENT_DATE,
    0, 'Residential_Standard', false, 5, 20, 17, 18,
    1800000, 0, 1000000, 0, 0, 0, 0, 0, 0, 1250000,
    550000, 0, 0, false, 'on_cost', 20, '{}'::jsonb, false,
    v_user_id, gen_random_uuid(), true, 'Base', 1
  ) RETURNING id INTO v_appraisal_id;

  -- Seed cost lines on the appraisal so future --extra-appraisal clones
  -- have rows to copy. Live schema is 10 columns (see chat-18 D13):
  --   appraisal_id, display_order, cost_code_id, label, category,
  --   auto_source, percentage, amount, is_locked, notes
  -- (id, created_at, updated_at default at DB layer.)
  SELECT array_agg(id) INTO v_cc_ids FROM (SELECT id FROM cost_codes LIMIT 3) sub;
  INSERT INTO appraisal_cost_lines
    (appraisal_id, display_order, cost_code_id, label, category, auto_source, amount)
  VALUES
    (v_appraisal_id, 0, v_cc_ids[1], 'Substructure works', 'Construction', 'Manual', 400000),
    (v_appraisal_id, 1, v_cc_ids[2], 'Superstructure',     'Construction', 'Manual', 600000),
    (v_appraisal_id, 2, v_cc_ids[3], 'Finishes',           'Construction', 'Manual', 250000);

  INSERT INTO budgets (project_id, source_appraisal_id, version_number, version_label,
    is_current, status, total_budget, created_by_user_id, notes)
  VALUES (v_project_id, v_appraisal_id, 1, 'v1 — opening',
    true, 'Draft', 1250000, v_user_id, 'Demo seed (provision script)')
  RETURNING id INTO v_b_id;

  FOR i IN 1..3 LOOP
    INSERT INTO budget_lines (budget_id, cost_code_id, entity_id, line_description,
      original_budget, approved_changes, current_budget,
      forecast_to_complete, ftc_method, percentage_complete,
      is_locked, requires_attention, display_order)
    VALUES (v_b_id, v_cc_ids[i], v_entity_id,
      CASE i WHEN 1 THEN 'Substructure works' WHEN 2 THEN 'Superstructure' ELSE 'Finishes' END,
      CASE i WHEN 1 THEN 400000 WHEN 2 THEN 600000 ELSE 250000 END,
      0,
      CASE i WHEN 1 THEN 400000 WHEN 2 THEN 600000 ELSE 250000 END,
      CASE i WHEN 1 THEN 400000 WHEN 2 THEN 600000 ELSE 250000 END,
      'Budget_Remaining', 0, false, false, i-1)
    RETURNING id INTO v_line_id;

    IF i = 1 THEN
      INSERT INTO budget_line_items (budget_line_id, description, quantity, unit, rate, amount, display_order)
      VALUES (v_line_id, 'Excavation', 1000, 'm3', 150, 150000, 0),
             (v_line_id, 'Foundations', 1, 'item', 250000, 250000, 1);
    END IF;
  END LOOP;

  UPDATE budget_lines SET
    forecast_final_cost = forecast_to_complete + actuals_to_date + committed_not_invoiced,
    variance_value = (forecast_to_complete + actuals_to_date + committed_not_invoiced) - current_budget,
    variance_pct = 0,
    variance_status = 'Green'
  WHERE budget_id = v_b_id;

  UPDATE budgets SET
    total_actuals = 0,
    total_committed_not_invoiced = 0,
    total_forecast_to_complete = total_budget,
    forecast_final_cost = total_budget,
    variance_vs_budget = 0,
    variance_pct = 0,
    summary_refreshed_at = now()
  WHERE id = v_b_id;

  RAISE NOTICE 'demo budget seeded: %', v_b_id;
END\$\$;
SQL

# ─── --with-v2-lineage: Superseded v1 + Draft v2 chain ───────────────
if [[ "$WITH_V2_LINEAGE" == "1" ]]; then
eval "$PSQL" <<SQL
DO \$\$
DECLARE
  v_project_id uuid := '${PROJECT_ID}';
  v_user_id uuid; v_v1_id uuid; v_v2_id uuid;
BEGIN
  SELECT id INTO v_user_id FROM users WHERE email='test-pm@example.test';

  -- Skip if v2 already exists.
  IF EXISTS (SELECT 1 FROM budgets WHERE project_id=v_project_id AND version_number=2) THEN
    RAISE NOTICE 'v2 lineage already present — skipping';
    RETURN;
  END IF;

  SELECT id INTO v_v1_id FROM budgets WHERE project_id=v_project_id AND version_number=1;
  IF v_v1_id IS NULL THEN
    RAISE EXCEPTION 'v2-lineage: v1 budget not found on project %', v_project_id;
  END IF;

  -- Mark v1 as Superseded + not current.
  UPDATE budgets SET status='Superseded', is_current=false WHERE id=v_v1_id;

  -- Seed v2 Draft. Note: budgets has no parent_budget_id column; lineage
  -- is inferred via source_appraisal_id + version_number. Reuse v1's
  -- appraisal id (the demo Approved one). Unique constraint
  -- uq_budgets_one_current_per_project requires v1 is_current=false above.
  INSERT INTO budgets (
    project_id, source_appraisal_id,
    version_number, version_label,
    is_current, status, total_budget, created_by_user_id, notes
  )
  SELECT
    project_id, source_appraisal_id,
    2, 'v2 — re-baseline',
    true, 'Draft', total_budget, v_user_id, 'v2 lineage seed (chat-18)'
  FROM budgets WHERE id=v_v1_id
  RETURNING id INTO v_v2_id;

  -- Clone lines from v1 onto v2.
  INSERT INTO budget_lines (
    budget_id, cost_code_id, entity_id, line_description,
    original_budget, approved_changes, current_budget,
    forecast_to_complete, ftc_method, percentage_complete,
    is_locked, requires_attention, display_order,
    forecast_final_cost, variance_value, variance_pct, variance_status
  )
  SELECT
    v_v2_id, cost_code_id, entity_id, line_description,
    original_budget, approved_changes, current_budget,
    forecast_to_complete, ftc_method, percentage_complete,
    false, false, display_order,
    forecast_final_cost, variance_value, variance_pct, variance_status
  FROM budget_lines WHERE budget_id=v_v1_id;

  -- Set v2 summary fields to mirror v1.
  UPDATE budgets SET
    total_actuals = 0,
    total_committed_not_invoiced = 0,
    total_forecast_to_complete = total_budget,
    forecast_final_cost = total_budget,
    variance_vs_budget = 0,
    variance_pct = 0,
    summary_refreshed_at = now()
  WHERE id=v_v2_id;

  RAISE NOTICE 'v2 lineage seeded: v1=% v2=%', v_v1_id, v_v2_id;
END\$\$;
SQL
fi

# ─── --empty-project: seed E2E_EMPTY_PROJECT_ID with NO budgets ──────
if [[ "$WITH_EMPTY_PROJECT" == "1" ]]; then
eval "$PSQL" <<SQL
DO \$\$
DECLARE
  v_eid uuid := '${EMPTY_PROJECT_ID}';
BEGIN
  IF EXISTS (SELECT 1 FROM projects WHERE id=v_eid) THEN
    -- Wipe any budgets that snuck onto it (defensive).
    DELETE FROM budgets WHERE project_id=v_eid;
    RAISE NOTICE 'empty project already present — wiped any stray budgets';
    RETURN;
  END IF;

  INSERT INTO projects (
    id, project_code, name, project_type, primary_entity_id, land_ownership_method,
    site_address, site_postcode, created_by_user_id
  ) VALUES (
    v_eid, 'SY-DEMO-EMPTY', 'SY Demo Empty Project', 'Dev_Build',
    (SELECT id FROM entities LIMIT 1), 'Direct_Purchase',
    '2 Empty Street, Shrewsbury', 'SY1 1AB',
    (SELECT id FROM users WHERE email='test-pm@example.test')
  ) ON CONFLICT (id) DO NOTHING;

  RAISE NOTICE 'empty project seeded: %', v_eid;
END\$\$;
SQL
fi

# ─── --extra-appraisal: un-linked Approved appraisal ─────────────────
# Skip-guard: any un-linked Approved appraisal already present?
#   If yes: skip (mid-suite re-runs are no-op).
#   If no: clone the original demo appraisal's header + cost lines
#          (10-column live schema per chat-18 D13). Unique name suffix
#          so multiple --extra-appraisal coexist across runs.
# RAISES EXCEPTION if zero cost lines copied (per Build Pack v4 critical
# fix — without cost lines, create_from_appraisal raises BudgetCreationError).
if [[ "$WITH_EXTRA_APPRAISAL" == "1" ]]; then
eval "$PSQL" <<SQL
DO \$\$
DECLARE
  v_project_id uuid := '${PROJECT_ID}';
  v_user_id uuid;
  v_src_appraisal_id uuid;
  v_new_appraisal_id uuid;
  v_name text;
  v_unlinked_count int;
  v_cost_line_count int;
BEGIN
  SELECT COUNT(*)
    INTO v_unlinked_count
    FROM appraisals a
   WHERE a.project_id=v_project_id
     AND a.status='Approved'
     AND NOT EXISTS (SELECT 1 FROM budgets b WHERE b.source_appraisal_id=a.id);

  IF v_unlinked_count > 0 THEN
    RAISE NOTICE 'extra appraisal: un-linked Approved appraisal already exists (%) — skipping', v_unlinked_count;
    RETURN;
  END IF;

  SELECT a.id INTO v_src_appraisal_id
    FROM appraisals a
   WHERE a.project_id=v_project_id
     AND a.status='Approved'
     AND EXISTS (SELECT 1 FROM appraisal_cost_lines cl WHERE cl.appraisal_id=a.id)
   ORDER BY a.created_at ASC
   LIMIT 1;

  IF v_src_appraisal_id IS NULL THEN
    RAISE EXCEPTION 'extra-appraisal: no source appraisal with cost lines found on project % — run base seed first', v_project_id;
  END IF;

  v_name := 'Demo Appraisal extra-' || to_char(clock_timestamp(), 'YYYYMMDDHH24MISSMS');
  SELECT id INTO v_user_id FROM users WHERE email='test-pm@example.test';

  INSERT INTO appraisals (
    name, project_id, status, reference_date,
    land_purchase_price, sdlt_category, developer_relief,
    contingency_pct, target_profit_on_cost_pct, target_profit_on_gdv_pct,
    project_duration_months,
    gdv_total, total_acquisition_cost, total_build_cost, total_professional_fees,
    total_statutory_cost, total_finance_cost, total_contingency,
    total_sales_cost, total_other_cost, total_cost,
    profit_total, profit_on_cost_pct, profit_on_gdv_pct,
    rlv_enabled, rlv_target_basis, rlv_target_value, computation_metadata, is_stale,
    created_by_user_id, appraisal_group_id, is_current, scenario, version_number
  )
  SELECT
    v_name, v_project_id, 'Approved', CURRENT_DATE,
    land_purchase_price, sdlt_category, developer_relief,
    contingency_pct, target_profit_on_cost_pct, target_profit_on_gdv_pct,
    project_duration_months,
    gdv_total, total_acquisition_cost, total_build_cost, total_professional_fees,
    total_statutory_cost, total_finance_cost, total_contingency,
    total_sales_cost, total_other_cost, total_cost,
    profit_total, profit_on_cost_pct, profit_on_gdv_pct,
    rlv_enabled, rlv_target_basis, rlv_target_value, '{}'::jsonb, false,
    v_user_id, gen_random_uuid(), false, 'Base',
    1 + (SELECT COALESCE(MAX(version_number),0) FROM appraisals WHERE project_id=v_project_id AND scenario='Base')
  FROM appraisals WHERE id=v_src_appraisal_id
  RETURNING id INTO v_new_appraisal_id;

  -- Live 10-column schema (chat-18 D13 — Build Pack v4 listed 5 phantom
  -- columns that were dropped before Prompt 2.4A merged).
  INSERT INTO appraisal_cost_lines (
    appraisal_id, display_order, cost_code_id, label, category,
    auto_source, percentage, amount, is_locked, notes
  )
  SELECT
    v_new_appraisal_id, display_order, cost_code_id, label, category,
    auto_source, percentage, amount, is_locked, notes
  FROM appraisal_cost_lines WHERE appraisal_id=v_src_appraisal_id;

  GET DIAGNOSTICS v_cost_line_count = ROW_COUNT;
  IF v_cost_line_count = 0 THEN
    RAISE EXCEPTION 'extra-appraisal: zero cost lines cloned from source — abort';
  END IF;

  RAISE NOTICE 'extra appraisal seeded: % with % cost lines', v_name, v_cost_line_count;
END\$\$;
SQL
fi

# ─── Summary: list budgets on the demo project ───────────────────────
eval "$PSQL" <<SQL
SELECT id, version_number, status, is_current,
       total_budget, forecast_final_cost, variance_vs_budget, variance_pct
FROM budgets
WHERE project_id='${PROJECT_ID}'
ORDER BY version_number;
SQL

echo "[seed-demo-budget] DONE"
