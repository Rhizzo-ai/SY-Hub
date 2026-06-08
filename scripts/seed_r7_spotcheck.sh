#!/bin/bash
# /app/scripts/seed_r7_spotcheck.sh
#
# Chat 23 §R7 spot-check seed. Replaces the base demo budget with a
# richer fixture so the operator can verify bulk delete + CSV export
# against real-looking data:
#
#   - 10 budget_lines across 3 prefix categories (ACQ / EXT / FIN)
#     — variance grouping renders 3 distinct group headers.
#   - 5 lines carry non-zero actuals_to_date (heat-map visible).
#   - 2 lines deliberately Red (>10% over budget).
#   - 1 line Amber (between 0% and 10%).
#   - Budget left in Active status so DELETE on a line is permitted.
#
# Visibility: test-admin (super_admin) sees every project tenant-wide.
# test-readonly (read_only, entity_scope=All) also sees every project
# in the default tenant, so both can spot-check the same budget.
#
# Idempotent: drops the existing project's budgets and re-seeds. Safe
# to re-run after a container recycle.
set -euo pipefail

PROJECT_ID="${E2E_PROJECT_ID:-b2a265ef-dc30-4779-96f6-e139d1881e07}"
PSQL="PGPASSWORD=syhomes_dev /usr/lib/postgresql/16/bin/psql -h 127.0.0.1 -U syhomes -d syhomes -tq"

eval "$PSQL" <<SQL
UPDATE users SET mfa_enabled=false, mfa_method=NULL,
  mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
  mfa_enrolled_at=NULL, failed_login_attempts=0,
  locked_until=NULL, lockout_level=0
WHERE email LIKE 'test-%@example.test';

INSERT INTO projects (
  id, project_code, name, project_type, primary_entity_id,
  land_ownership_method, site_address, site_postcode, created_by_user_id
) VALUES (
  '${PROJECT_ID}', 'SY-R7-DEMO', 'SY R7 Spot-check Project', 'Dev_Build',
  (SELECT id FROM entities WHERE name='SY Homes (Shrewsbury) Ltd'),
  'Direct_Purchase',
  '1 R7 Spot-check Way, Shrewsbury', 'SY1 9AA',
  (SELECT id FROM users WHERE email='test-pm@example.test')
) ON CONFLICT (id) DO UPDATE
  SET primary_entity_id =
    (SELECT id FROM entities WHERE name='SY Homes (Shrewsbury) Ltd'),
      name=EXCLUDED.name;
SQL

# Wipe any prior budgets on the demo project (idempotent re-run).
eval "$PSQL" <<SQL
ALTER TABLE audit_log DISABLE TRIGGER USER;
DELETE FROM audit_log
 WHERE resource_type IN ('budgets','budget_lines','budget_line_items',
                         'appraisals','appraisal_units',
                         'appraisal_cost_lines','appraisal_finance_model')
   AND project_id = '${PROJECT_ID}';
ALTER TABLE audit_log ENABLE TRIGGER USER;
DELETE FROM budget_line_items
 WHERE budget_line_id IN (
   SELECT bl.id FROM budget_lines bl
   JOIN budgets b ON b.id = bl.budget_id
   WHERE b.project_id = '${PROJECT_ID}'
 );
DELETE FROM budget_lines
 WHERE budget_id IN (SELECT id FROM budgets WHERE project_id='${PROJECT_ID}');
DELETE FROM budgets WHERE project_id='${PROJECT_ID}';
DELETE FROM appraisal_finance_model
 WHERE appraisal_id IN (SELECT id FROM appraisals WHERE project_id='${PROJECT_ID}');
DELETE FROM appraisal_cost_lines
 WHERE appraisal_id IN (SELECT id FROM appraisals WHERE project_id='${PROJECT_ID}');
DELETE FROM appraisal_units
 WHERE appraisal_id IN (SELECT id FROM appraisals WHERE project_id='${PROJECT_ID}');
ALTER TABLE appraisal_decision_log DISABLE TRIGGER USER;
DELETE FROM appraisal_decision_log
 WHERE appraisal_id IN (SELECT id FROM appraisals WHERE project_id='${PROJECT_ID}');
ALTER TABLE appraisal_decision_log ENABLE TRIGGER USER;
DELETE FROM appraisals WHERE project_id='${PROJECT_ID}';
SQL

eval "$PSQL" <<SQL
DO \$\$
DECLARE
  v_project_id uuid := '${PROJECT_ID}';
  v_user_id uuid;
  v_entity_id uuid;
  v_appraisal_id uuid;
  v_b_id uuid;
  v_cc_acq1 uuid; v_cc_acq2 uuid; v_cc_acq3 uuid;
  v_cc_ext1 uuid; v_cc_ext2 uuid; v_cc_ext3 uuid; v_cc_ext4 uuid;
  v_cc_fin1 uuid; v_cc_fin2 uuid; v_cc_fin3 uuid;
BEGIN
  SELECT id INTO v_user_id FROM users WHERE email='test-pm@example.test';
  SELECT primary_entity_id INTO v_entity_id FROM projects WHERE id=v_project_id;

  SELECT id INTO v_cc_acq1 FROM cost_codes WHERE code='ACQ-01';
  SELECT id INTO v_cc_acq2 FROM cost_codes WHERE code='ACQ-02';
  SELECT id INTO v_cc_acq3 FROM cost_codes WHERE code='ACQ-03';
  SELECT id INTO v_cc_ext1 FROM cost_codes WHERE code='EXT-01';
  SELECT id INTO v_cc_ext2 FROM cost_codes WHERE code='EXT-02';
  SELECT id INTO v_cc_ext3 FROM cost_codes WHERE code='EXT-03';
  SELECT id INTO v_cc_ext4 FROM cost_codes WHERE code='EXT-04';
  SELECT id INTO v_cc_fin1 FROM cost_codes WHERE code='FIN-01';
  SELECT id INTO v_cc_fin2 FROM cost_codes WHERE code='FIN-02';
  SELECT id INTO v_cc_fin3 FROM cost_codes WHERE code='FIN-03';

  -- Source Approved appraisal (lightweight; only needed to satisfy
  -- the source_appraisal_id FK on budgets).
  -- Enable the 10 cost codes we use on this project so the cost-code
  -- lookup in BudgetGridV2 finds them (the grid groups by code prefix
  -- via the per-project cost-code list, not the global table).
  INSERT INTO project_cost_codes (project_id, cost_code_id, is_enabled)
  SELECT v_project_id, id, true FROM cost_codes
   WHERE code IN ('ACQ-01','ACQ-02','ACQ-03',
                  'EXT-01','EXT-02','EXT-03','EXT-04',
                  'FIN-01','FIN-02','FIN-03')
  ON CONFLICT (project_id, cost_code_id) DO UPDATE SET is_enabled=true;

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
    'R7 Demo Appraisal', v_project_id, 'Approved', CURRENT_DATE,
    400000, 'Residential_Standard', false, 5, 20, 17, 18,
    1500000, 0, 700000, 0, 0, 0, 0, 0, 0, 1025000,
    475000, 0, 0, false, 'on_cost', 20, '{}'::jsonb, false,
    v_user_id, gen_random_uuid(), true, 'Base', 1
  ) RETURNING id INTO v_appraisal_id;

  -- Active budget — total_budget recomputed below by summing lines.
  INSERT INTO budgets (
    project_id, source_appraisal_id, version_number, version_label,
    is_current, status, total_budget, created_by_user_id, notes
  ) VALUES (
    v_project_id, v_appraisal_id, 1, 'R7 spot-check',
    true, 'Active', 0, v_user_id, 'R7 spot-check seed — 10 lines, 3 cats, mixed variance'
  ) RETURNING id INTO v_b_id;

  -- 10 lines. Variance fields are computed by the trigger via the
  -- recompute formulas below (FFC = actuals + committed + FTC).
  INSERT INTO budget_lines (
    budget_id, cost_code_id, entity_id, line_description,
    original_budget, approved_changes, current_budget,
    actuals_to_date, committed_not_invoiced, forecast_to_complete,
    ftc_method, percentage_complete, is_locked, requires_attention,
    display_order, notes
  ) VALUES
    -- ACQ category (3 lines) — all Green
    (v_b_id, v_cc_acq1, v_entity_id, 'Site purchase price',
       400000, 0, 400000, 0,      0, 400000, 'Budget_Remaining', 0, false, false, 0, NULL),
    (v_b_id, v_cc_acq2, v_entity_id, 'SDLT payment',
       50000,  0, 50000,  25000,  0, 25000,  'Budget_Remaining', 50, false, false, 1,
       'Stage 1 SDLT paid Apr 26'),
    (v_b_id, v_cc_acq3, v_entity_id, 'Conveyancing & legal',
       15000,  0, 15000,  12000,  0, 3000,   'Budget_Remaining', 80, false, false, 2, NULL),
    -- EXT category (4 lines) — 1 Red, 1 Amber, 2 Green
    (v_b_id, v_cc_ext1, v_entity_id, 'Externals — drainage (overrun)',
       100000, 0, 100000, 80000,  0, 40000,  'Manual', 80, false, true, 3,
       'Hit unexpected rock; ground works overrun by ~20%'),
    (v_b_id, v_cc_ext2, v_entity_id, 'Externals — landscaping (slight)',
       50000,  0, 50000,  0,      0, 53000,  'Manual', 0, false, false, 4,
       'Awaiting quote, expect ~5% over'),
    (v_b_id, v_cc_ext3, v_entity_id, 'Externals — boundary fencing',
       80000,  0, 80000,  70000,  0, 10000,  'Budget_Remaining', 87, false, false, 5, NULL),
    (v_b_id, v_cc_ext4, v_entity_id, 'Externals — paving (not started)',
       30000,  0, 30000,  0,      0, 30000,  'Budget_Remaining', 0, false, false, 6, NULL),
    -- FIN category (3 lines) — 1 Red, 2 Green
    (v_b_id, v_cc_fin1, v_entity_id, 'Senior debt interest (extension)',
       200000, 0, 200000, 50000,  0, 200000, 'Manual', 25, false, true, 7,
       'Loan extended 3 months; expect ~25% overrun'),
    (v_b_id, v_cc_fin2, v_entity_id, 'Mezzanine finance fees',
       60000,  0, 60000,  0,      0, 60000,  'Budget_Remaining', 0, false, false, 8, NULL),
    (v_b_id, v_cc_fin3, v_entity_id, 'Bank charges',
       40000,  0, 40000,  0,      0, 40000,  'Budget_Remaining', 0, false, false, 9, NULL);

  -- Recompute FFC + variance band on every line.
  UPDATE budget_lines SET
    forecast_final_cost = COALESCE(actuals_to_date,0) + COALESCE(committed_not_invoiced,0) + COALESCE(forecast_to_complete,0),
    variance_value = (COALESCE(actuals_to_date,0) + COALESCE(committed_not_invoiced,0) + COALESCE(forecast_to_complete,0)) - current_budget
  WHERE budget_id = v_b_id;

  UPDATE budget_lines SET
    variance_pct = CASE WHEN current_budget > 0
      THEN ROUND((variance_value::numeric / current_budget) * 100, 2)
      ELSE 0 END
  WHERE budget_id = v_b_id;

  -- Variance band: Green if pct <= 0, Amber if 0 < pct < 10, Red if pct >= 10.
  -- (R1.1 bands per Chat 23 R1: AMBER=0, RED=10.) Cast to the enum.
  UPDATE budget_lines SET
    variance_status = (CASE
      WHEN variance_pct >= 10 THEN 'Red'
      WHEN variance_pct > 0   THEN 'Amber'
      ELSE 'Green'
    END)::budget_line_variance_status
  WHERE budget_id = v_b_id;

  -- Recompute header totals from the line aggregate.
  UPDATE budgets SET
    total_budget = (SELECT COALESCE(SUM(current_budget),0) FROM budget_lines WHERE budget_id=v_b_id),
    total_actuals = (SELECT COALESCE(SUM(actuals_to_date),0) FROM budget_lines WHERE budget_id=v_b_id),
    total_committed_not_invoiced = (SELECT COALESCE(SUM(committed_not_invoiced),0) FROM budget_lines WHERE budget_id=v_b_id),
    total_forecast_to_complete = (SELECT COALESCE(SUM(forecast_to_complete),0) FROM budget_lines WHERE budget_id=v_b_id),
    forecast_final_cost = (SELECT COALESCE(SUM(forecast_final_cost),0) FROM budget_lines WHERE budget_id=v_b_id),
    variance_vs_budget =
      (SELECT COALESCE(SUM(forecast_final_cost),0) FROM budget_lines WHERE budget_id=v_b_id)
      - (SELECT COALESCE(SUM(current_budget),0) FROM budget_lines WHERE budget_id=v_b_id),
    summary_refreshed_at = now()
  WHERE id = v_b_id;

  UPDATE budgets SET
    variance_pct = CASE WHEN total_budget > 0
      THEN ROUND((variance_vs_budget::numeric / total_budget) * 100, 2)
      ELSE 0 END
  WHERE id = v_b_id;

  RAISE NOTICE 'R7 spot-check budget seeded: id=% project=%', v_b_id, v_project_id;
END\$\$;
SQL

# Print summary so the operator gets the direct URL.
echo ""
echo "─── R7 spot-check seeded ────────────────────────────────────────────"
eval "$PSQL" <<SQL
SELECT
  '  Budget ID:    ' || id || E'\n' ||
  '  Status:       ' || status || E'\n' ||
  '  Total budget: £' || to_char(total_budget, 'FM999,999,999.00') || E'\n' ||
  '  Forecast FFC: £' || to_char(forecast_final_cost, 'FM999,999,999.00') || E'\n' ||
  '  Variance:     £' || to_char(variance_vs_budget, 'FM999,999,999.00') ||
                         ' (' || variance_pct || '%)' AS info
FROM budgets WHERE project_id='${PROJECT_ID}' AND is_current=true;
SQL

echo ""
eval "$PSQL" <<SQL
SELECT
  '  ' || rpad(cc.code, 8) ||
  rpad(bl.line_description, 36) ||
  'budget=£' || rpad(to_char(bl.current_budget, 'FM999,999.00'), 12) ||
  'actuals=£' || rpad(to_char(bl.actuals_to_date, 'FM999,999.00'), 12) ||
  'var=' || rpad(bl.variance_pct::text || '%', 8) ||
  bl.variance_status AS line_summary
FROM budget_lines bl
JOIN budgets b ON b.id = bl.budget_id
JOIN cost_codes cc ON cc.id = bl.cost_code_id
WHERE b.project_id='${PROJECT_ID}' AND b.is_current=true
ORDER BY bl.display_order;
SQL

PROJ="$PROJECT_ID"
BID=$(eval "$PSQL" -c "SELECT id FROM budgets WHERE project_id='${PROJ}' AND is_current=true" | tr -d ' ')
APP_URL="${REACT_APP_BACKEND_URL:-https://production-contract-1.preview.emergentagent.com}"

echo ""
echo "─── Direct URLs ─────────────────────────────────────────────────────"
echo "  Budgets list:  ${APP_URL}/projects/${PROJ}/budgets"
echo "  Budget detail: ${APP_URL}/projects/${PROJ}/budgets/${BID}"
echo ""
echo "  Login as test-admin@example.test  or  test-readonly@example.test"
echo "  Password: TestUser-Dev-2026!"
echo "─────────────────────────────────────────────────────────────────────"
