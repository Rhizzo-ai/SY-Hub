"""B88 Pack 2 — sandbox demo seed.

Purpose: restore the canonical Job-Costing demo project on the
sandbox after any pod recycle / round-trip / operator-driven state
mutation (e.g. someone clicked New Version and superseded v1).

  • SANDBOX-ONLY: this script is NOT run by `bootstrap.py`, NOT
    referenced by tests, and NOT a migration. Re-run by hand any
    time the operator needs a clean demo.
  • Idempotent: wipes ANY prior 'B88P2 Demo — Pin Oak' project and
    all dependents (appraisals, budgets, lines, items, versions,
    audit rows) before re-creating.
  • Restores exactly ONE Active budget at v1 with the canonical
    Red / Amber / Green heat-map composition.

Invocation:
  cd /app/backend
  set -a; source .env; set +a
  export REACT_APP_BACKEND_URL=$(grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d= -f2-)
  /root/.venv/bin/python scripts/seed_b88_pack2_demo.py
"""
import os
from decimal import Decimal
import requests
from sqlalchemy import create_engine, text

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]
ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"

eng = create_engine(DATABASE_URL, future=True)

# ──────────────────────────────────────────────────────────────────────
# Wipe any prior demo (idempotent re-run)
# ──────────────────────────────────────────────────────────────────────
with eng.begin() as c:
    c.execute(text("ALTER TABLE audit_log DISABLE TRIGGER USER"))
    c.execute(text("""
        DELETE FROM audit_log WHERE project_id IN (
            SELECT id FROM projects WHERE name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("ALTER TABLE audit_log ENABLE TRIGGER USER"))
    c.execute(text("""
        DELETE FROM budget_line_items WHERE budget_line_id IN (
            SELECT bl.id FROM budget_lines bl
            JOIN budgets b ON b.id = bl.budget_id
            JOIN projects p ON p.id = b.project_id
            WHERE p.name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("""
        DELETE FROM budget_lines WHERE budget_id IN (
            SELECT b.id FROM budgets b JOIN projects p ON p.id = b.project_id
            WHERE p.name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("""
        DELETE FROM budgets WHERE project_id IN (
            SELECT id FROM projects WHERE name = 'B88P2 Demo — Pin Oak'
        )
    """))
    for tbl in ("appraisal_finance_model", "appraisal_cost_lines",
                "appraisal_units"):
        c.execute(text(f"""
            DELETE FROM {tbl} WHERE appraisal_id IN (
                SELECT a.id FROM appraisals a JOIN projects p
                  ON p.id = a.project_id WHERE p.name = 'B88P2 Demo — Pin Oak'
            )
        """))
    c.execute(text("ALTER TABLE appraisal_decision_log DISABLE TRIGGER USER"))
    c.execute(text("""
        DELETE FROM appraisal_decision_log WHERE appraisal_id IN (
            SELECT a.id FROM appraisals a JOIN projects p
              ON p.id = a.project_id WHERE p.name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("ALTER TABLE appraisal_decision_log ENABLE TRIGGER USER"))
    c.execute(text("""
        DELETE FROM appraisal_revisions WHERE appraisal_id_to IN (
            SELECT a.id FROM appraisals a JOIN projects p
              ON p.id = a.project_id WHERE p.name = 'B88P2 Demo — Pin Oak'
        ) OR appraisal_id_from IN (
            SELECT a.id FROM appraisals a JOIN projects p
              ON p.id = a.project_id WHERE p.name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("""
        DELETE FROM appraisal_scenarios WHERE scenario_appraisal_id IN (
            SELECT a.id FROM appraisals a JOIN projects p
              ON p.id = a.project_id WHERE p.name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("""
        DELETE FROM appraisals WHERE project_id IN (
            SELECT id FROM projects WHERE name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("""
        DELETE FROM project_team_members WHERE project_id IN (
            SELECT id FROM projects WHERE name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("""
        DELETE FROM user_role_projects WHERE project_id IN (
            SELECT id FROM projects WHERE name = 'B88P2 Demo — Pin Oak'
        )
    """))
    c.execute(text("DELETE FROM projects WHERE name = 'B88P2 Demo — Pin Oak'"))

    c.execute(text("""
        UPDATE user_roles SET project_scope = 'All'
        WHERE id IN (
          SELECT ur.id FROM user_roles ur
          JOIN users u ON u.id = ur.user_id
          JOIN roles r ON r.id = ur.role_id
          WHERE u.email = 'test-pm@example.test'
            AND r.code = 'project_manager'
            AND ur.status = 'Active'
        )
    """))
    c.execute(text("""
        UPDATE users SET mfa_enabled=false, mfa_method=NULL,
          mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
          mfa_enrolled_at=NULL, failed_login_attempts=0,
          locked_until=NULL, lockout_level=0
        WHERE email LIKE 'test-%@example.test'
    """))

# ──────────────────────────────────────────────────────────────────────
# Admin login (MFA-enforced; auto-enroll if needed via pyotp)
# ──────────────────────────────────────────────────────────────────────
import sys
sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/tests")
from conftest import login_with_auto_enroll, plain_login
s = login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)
print(f"admin logged in (cookies: {list(s.cookies.keys())})")

with eng.connect() as c:
    entity_id = str(c.execute(text(
        "SELECT id FROM entities WHERE name = 'SY Homes (Shrewsbury) Ltd'"
    )).scalar())

# ──────────────────────────────────────────────────────────────────────
# Project + appraisal
# ──────────────────────────────────────────────────────────────────────
r = s.post(f"{BASE_URL}/api/projects", json={
    "name": "B88P2 Demo — Pin Oak",
    "project_type": "Dev_Build",
    "primary_entity_id": entity_id,
    "land_ownership_method": "Direct_Purchase",
    "site_address": "1 Pin Oak Lane, Shrewsbury",
    "site_postcode": "SY1 8DD",
    "tenure": "Freehold",
})
assert r.status_code == 201, r.text
project = r.json()
project_id = project["id"]
print(f"project: {project_id}")

r = s.post(f"{BASE_URL}/api/v1/projects/{project_id}/appraisals", json={
    "name": "B88P2 Demo — Pin Oak (Base)",
    "land_purchase_price": "200000",
})
assert r.status_code == 201, r.text
aid = r.json()["id"]
print(f"appraisal: {aid}")

# ──────────────────────────────────────────────────────────────────────
# Cost-line set spanning Land + 4.00/4.01/4.02 + overheads
# ──────────────────────────────────────────────────────────────────────
with eng.begin() as c:
    c.execute(text("DELETE FROM appraisal_cost_lines WHERE appraisal_id=:a"),
              {"a": aid})

    def pick(prefix, n=1):
        rows = c.execute(text(
            "SELECT id FROM cost_codes WHERE prefix=:p AND status='Active' "
            "ORDER BY sequence LIMIT :n"
        ), {"p": prefix, "n": n}).fetchall()
        return [str(r.id) for r in rows]

    def pick_section(section_code, n=1):
        rows = c.execute(text("""
            SELECT cc.id FROM cost_codes cc
            JOIN cost_code_sections cs ON cs.id = cc.section_id
            WHERE cs.code = :s AND cc.status='Active'
            ORDER BY cc.sequence LIMIT :n
        """), {"s": section_code, "n": n}).fetchall()
        return [str(r.id) for r in rows]

    sub_400 = pick_section("4.00", 1)[0]
    sub_401 = pick_section("4.01", 1)[0]
    sub_402 = pick_section("4.02", 1)[0]
    acq = pick("ACQ", 1)[0]

    # Overheads / sales / professional — any non-construction, non-Land code.
    overheads = c.execute(text("""
        SELECT cc.id FROM cost_codes cc
        JOIN cost_code_sections cs ON cs.id = cc.section_id
        WHERE cs.included_in_construction_scope = false
          AND cs.code != '1'
          AND cs.parent_section_id IS NULL
          AND cc.status = 'Active'
        ORDER BY cs.display_order, cc.sequence
        LIMIT 1
    """)).scalar()
    if overheads is None:
        overheads = c.execute(text("""
            SELECT cc.id FROM cost_codes cc
            JOIN cost_code_sections cs ON cs.id = cc.section_id
            WHERE cs.included_in_construction_scope = false
              AND cs.code != '1'
              AND cc.status = 'Active'
            ORDER BY cc.sequence LIMIT 1
        """)).scalar()
    overheads = str(overheads)

    print(f"  ACQ={acq}")
    print(f"  4.00={sub_400}  4.01={sub_401}  4.02={sub_402}")
    print(f"  overheads/sales={overheads}")

    cost_seeds = [
        (acq,       "Land purchase",          "200000.00", "Acquisition"),
        (sub_400,   "Demolition + site prep", "180000.00", "Construction"),
        (sub_401,   "Substructure",           "320000.00", "Construction"),
        (sub_402,   "Superstructure frame",   "450000.00", "Construction"),
        (overheads, "Professional fees",      "75000.00",  "Professional_Fees"),
    ]
    for order, (cc_id, label, amount, cat) in enumerate(cost_seeds, start=10):
        c.execute(text("""
            INSERT INTO appraisal_cost_lines
              (id, appraisal_id, display_order, cost_code_id, label,
               category, auto_source, amount, is_locked)
            VALUES (gen_random_uuid(), :a, :o, :cc, :l, :cat, 'Manual',
                    :amt, false)
        """), {"a": aid, "o": order * 10, "cc": cc_id, "l": label,
                "cat": cat, "amt": amount})

# Add a unit so GDV is non-zero (Tier 1 allocation column will populate).
r = s.post(f"{BASE_URL}/api/v1/appraisals/{aid}/units", json={
    "unit_label": "Block A", "unit_type": "Detached",
    "tenure": "Open_Market", "quantity": 3,
    "price_per_unit": "550000",
    "build_cost_per_unit": "350000",
})
assert r.status_code == 201, r.text
print("unit added (GDV £1,650,000)")

# Submit + Approve
r = s.post(f"{BASE_URL}/api/v1/appraisals/{aid}/submit")
assert r.status_code == 200, r.text
r = s.post(f"{BASE_URL}/api/v1/appraisals/{aid}/approve")
assert r.status_code == 200, r.text
print(f"appraisal Approved")

# ──────────────────────────────────────────────────────────────────────
# Budget from appraisal + heat-map setup
# ──────────────────────────────────────────────────────────────────────
r = s.post(f"{BASE_URL}/api/v1/projects/{project_id}/budgets/from-appraisal",
           json={"source_appraisal_id": aid})
assert r.status_code == 201, r.text
budget = r.json()
budget_id = budget["id"]
print(f"budget: {budget_id}")

with eng.begin() as c:
    lines = c.execute(text("""
        SELECT bl.id, bl.current_budget, cs.code AS section_code
        FROM budget_lines bl
        JOIN cost_codes cc ON cc.id = bl.cost_code_id
        JOIN cost_code_sections cs ON cs.id = cc.section_id
        WHERE bl.budget_id = :b
        ORDER BY cs.code
    """), {"b": budget_id}).fetchall()
    print("\nseeded budget lines:")
    construction_lines = [l for l in lines if l.section_code.startswith("4")]
    for i, line in enumerate(construction_lines):
        cb = Decimal(line.current_budget)
        if i == 0:
            ffc = cb * Decimal("1.18")  # Red
            tag = "Red"
        elif i == 1:
            ffc = cb * Decimal("1.05")  # Amber
            tag = "Amber"
        else:
            ffc = cb * Decimal("0.92")  # Green (under)
            tag = "Green"
        atd = ffc * Decimal("0.6")
        ftc = ffc - atd
        var = ffc - cb
        vpct = (var / cb * Decimal("100")) if cb else Decimal("0")
        if vpct >= 10:
            status = "Red"
        elif vpct > 0:
            status = "Amber"
        else:
            status = "Green"
        c.execute(text("""
            UPDATE budget_lines
            SET actuals_to_date = :a,
                forecast_final_cost = :ffc,
                forecast_to_complete = :ftc,
                variance_value = :vv,
                variance_pct = :vp,
                variance_status = :vs,
                percentage_complete = :pc
            WHERE id = :id
        """), {"a": atd, "ffc": ffc, "ftc": ftc, "vv": var, "vp": vpct,
                "vs": status, "pc": Decimal("60"), "id": line.id})
        print(f"  [{tag:>5}] section {line.section_code}: cb=£{cb:,.0f} "
              f"→ ffc=£{ffc:,.0f} ({vpct:+.1f}%) status={status}")

    sums = c.execute(text("""
        SELECT
            COALESCE(SUM(current_budget),0) AS tb,
            COALESCE(SUM(actuals_to_date),0) AS ta,
            COALESCE(SUM(forecast_to_complete),0) AS tftc,
            COALESCE(SUM(forecast_final_cost),0) AS ffc,
            COALESCE(SUM(variance_value),0) AS vv
        FROM budget_lines WHERE budget_id = :b
    """), {"b": budget_id}).first()
    vpct = (sums.vv / sums.tb * 100) if sums.tb else 0
    c.execute(text("""
        UPDATE budgets SET
          total_budget = :tb,
          total_actuals = :ta,
          total_committed_not_invoiced = 0,
          total_forecast_to_complete = :tftc,
          forecast_final_cost = :ffc,
          variance_vs_budget = :vv,
          variance_pct = :vp,
          summary_refreshed_at = NOW()
        WHERE id = :id
    """), {"tb": sums.tb, "ta": sums.ta, "tftc": sums.tftc, "ffc": sums.ffc,
            "vv": sums.vv, "vp": vpct, "id": budget_id})

# Activate
r = s.post(f"{BASE_URL}/api/v1/budgets/{budget_id}/activate", json={})
print(f"\nactivate: {r.status_code}")
if r.status_code != 200:
    with eng.begin() as c:
        c.execute(text("UPDATE budgets SET status='Active' WHERE id = :i"),
                  {"i": budget_id})
    print("  fallback: set status='Active' directly")

print("\n" + "=" * 60)
print("DEMO SEED COMPLETE")
print("=" * 60)
print(f"Project ID: {project_id}")
print(f"Budget ID:  {budget_id}")
