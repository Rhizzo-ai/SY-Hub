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
# Usage: bash /app/scripts/seed_demo_budget.sh

set -euo pipefail

PGPASSWORD=syhomes_dev psql -h 127.0.0.1 -U syhomes -d syhomes -tq << 'SQL'
-- Wipe MFA on test users so login is one-step.
UPDATE users SET mfa_enabled=false, mfa_method=NULL,
  mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
  mfa_enrolled_at=NULL, failed_login_attempts=0,
  locked_until=NULL, lockout_level=0
WHERE email LIKE 'test-%@example.test';

-- Ensure the demo project exists with a stable id (so URLs survive).
INSERT INTO projects (
  id, project_code, name, project_type, primary_entity_id, land_ownership_method,
  site_address, site_postcode, created_by_user_id
) VALUES (
  'b2a265ef-dc30-4779-96f6-e139d1881e07',
  'SY-DEMO-01', 'SY Demo Project', 'Dev_Build',
  (SELECT id FROM entities LIMIT 1), 'Direct_Purchase',
  '1 Demo Street, Shrewsbury', 'SY1 1AA',
  (SELECT id FROM users WHERE email='test-pm@example.test')
) ON CONFLICT (project_code) DO NOTHING;
SQL

PGPASSWORD=syhomes_dev psql -h 127.0.0.1 -U syhomes -d syhomes -tq << 'SQL'
DO $$
DECLARE
  v_project_id uuid := 'b2a265ef-dc30-4779-96f6-e139d1881e07';
  v_user_id uuid; v_appraisal_id uuid; v_b_id uuid;
  v_entity_id uuid; v_cc_ids uuid[]; v_line_id uuid;
BEGIN
  -- Idempotent: skip if a budget already exists on this project.
  IF EXISTS (SELECT 1 FROM budgets WHERE project_id=v_project_id) THEN
    RAISE NOTICE 'demo budget already present — skipping';
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

  INSERT INTO budgets (project_id, source_appraisal_id, version_number, version_label,
    is_current, status, total_budget, created_by_user_id, notes)
  VALUES (v_project_id, v_appraisal_id, 1, 'v1 — opening',
    true, 'Draft', 1250000, v_user_id, 'Demo seed (provision script)')
  RETURNING id INTO v_b_id;

  SELECT array_agg(id) INTO v_cc_ids FROM (SELECT id FROM cost_codes LIMIT 3) sub;

  -- *** CRITICAL: ftc_method must be 'Budget_Remaining' (not 'Manual') ***
  -- The backend recomputes FTC = max(0, current - actuals - committed)
  -- in Budget_Remaining mode → FFC = current, variance = 0, Green pill.
  -- Setting 'Manual' with forecast_to_complete=0 creates a bogus
  -- "100% under budget" state — not representative of any realistic
  -- Draft-budget starting point.
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
      -- forecast_to_complete = current_budget for Budget_Remaining mode
      CASE i WHEN 1 THEN 400000 WHEN 2 THEN 600000 ELSE 250000 END,
      'Budget_Remaining', 0, false, false, i-1)
    RETURNING id INTO v_line_id;

    -- 2 items on the first line so LineDrawer + LineItemsPanel
    -- have real data to render.
    IF i = 1 THEN
      INSERT INTO budget_line_items (budget_line_id, description, quantity, unit, rate, amount, display_order)
      VALUES (v_line_id, 'Excavation', 1000, 'm3', 150, 150000, 0),
             (v_line_id, 'Foundations', 1, 'item', 250000, 250000, 1);
    END IF;
  END LOOP;

  -- Pre-compute the FFC/variance fields so the UI doesn't depend on
  -- an explicit refresh-attention scan to populate them.
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
END$$;

SELECT id, version_number, status, is_current,
       total_budget, forecast_final_cost, variance_vs_budget, variance_pct
FROM budgets
WHERE project_id='b2a265ef-dc30-4779-96f6-e139d1881e07';
SQL

echo "[seed-demo-budget] DONE"
