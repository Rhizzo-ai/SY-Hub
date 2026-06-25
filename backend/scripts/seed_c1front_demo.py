"""One-off demo seed for the C1-front (Chat 64) live click-through pre-check.

Creates, in the test tenant:
  Project "C1-front Demo" with an Active current budget and three lines:
    - Line A "Groundworks":  PO-DEMO-A (issued) with TWO lines on Line A
        * A1 net £10,000, one Posted linked bill £4,000  → remaining £6,000.00
        * A2 net £5,000,  fully receipted + Posted linked bill £5,000
                                                           → remaining £0.00 (fully invoiced)
    - Line B "Roofing":      PO-DEMO-B (issued) ONE line net £8,000, no bills
                                                           → remaining £8,000.00
    - Line C "Landscaping":  NO purchase orders            → empty case

Prints the project id + expectations. Idempotent-ish: each run makes a NEW
project (uuid-suffixed) so reruns never clash.
"""
import os
import sys
import uuid
from datetime import date
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
sys.path.insert(0, "/app/backend")

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.auth.permissions import UserPermissions  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.purchase_orders import PurchaseOrder, PurchaseOrderLine  # noqa: E402
from app.schemas.actuals import CreateActualRequest  # noqa: E402
from app.services import actuals as actuals_svc  # noqa: E402

engine = create_engine(os.environ["DATABASE_URL"], future=True)
Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def _perms(user):
    p = {
        "actuals.view", "actuals.view_sensitive", "actuals.create",
        "actuals.edit", "actuals.approve", "actuals.admin",
        "pos.view", "pos.view_sensitive",
    }
    return UserPermissions(
        user_id=user.id, tenant_id=user.tenant_id,
        all_permissions=set(p), all_entity_perms=set(p),
        all_project_perms=set(p), is_super_admin=True,
    )


def _po_line(po, *, budget_line_id, net, cost_code, line_number, fully_receipted=False):
    net_d = Decimal(net)
    qty = Decimal("1")
    return PurchaseOrderLine(
        purchase_order=po, budget_line_id=budget_line_id,
        cost_code=cost_code, line_number=line_number,
        description=f"Demo line {line_number}",
        quantity=qty, unit_rate=net_d, net_amount=net_d,
        vat_rate=Decimal("20.00"), vat_amount=Decimal("0"), gross_amount=net_d,
        receipted_quantity=(qty if fully_receipted else Decimal("0")),
        created_by=po.created_by, updated_by=po.updated_by,
    )


def _bill(db, *, project_id, entity_id, budget_line_id, linked, net, user, perms):
    body = CreateActualRequest(
        project_id=project_id, budget_line_id=budget_line_id, entity_id=entity_id,
        source_type="Manual_Entry", transaction_date=date.today(),
        description="Demo linked bill", net_amount=Decimal(net),
        vat_amount=Decimal("0"), vat_rate_pct=Decimal("20"),
        supplier_name_snapshot="Demo Supplier", linked_commitment_id=linked,
    )
    a = actuals_svc.create_actual(db, payload=body, user=user, perms=perms)
    db.commit()
    actuals_svc.post_actual(db, actual_id=a.id, user=user, perms=perms)
    db.commit()
    return a


def main():
    db = Session()
    admin = db.execute(text(
        "SELECT id, tenant_id FROM users WHERE email='test-admin@example.test'"
    )).first()
    user = db.get(User, admin.id)
    perms = _perms(user)
    entity_id = db.execute(text(
        "SELECT id FROM entities WHERE tenant_id=:t ORDER BY created_at LIMIT 1"
    ), {"t": admin.tenant_id}).scalar()
    cc = db.execute(text(
        "SELECT id, code FROM cost_codes ORDER BY code LIMIT 1"
    )).first()
    cc_rows = db.execute(text(
        "SELECT id, code FROM cost_codes ORDER BY code LIMIT 3"
    )).all()
    if len(cc_rows) < 3:
        raise SystemExit("need >= 3 cost codes seeded")
    cc_by_line = {"Groundworks": cc_rows[0], "Roofing": cc_rows[1], "Landscaping": cc_rows[2]}

    sfx = uuid.uuid4().hex[:6]
    pid = uuid.uuid4()
    db.execute(text("""
        INSERT INTO projects (id, project_code, name, primary_entity_id,
          project_type, land_ownership_method, status, tenure, current_stage,
          stage_entered_at, site_address, site_postcode, implementation_required,
          created_by_user_id)
        VALUES (:id, :code, :name, :ent, 'Dev_Build', 'Direct_Purchase',
                'Active', 'Freehold', 'Lead', NOW(), '1 Demo Way', 'SY1 1AA',
                false, :u)
    """), {"id": pid, "code": f"C1F-{sfx}", "name": f"C1-front Demo {sfx}",
           "ent": entity_id, "u": admin.id})

    ap = uuid.uuid4()
    db.execute(text("""
        INSERT INTO appraisals (id, project_id, name, reference_date,
          created_by_user_id, appraisal_group_id, scenario, is_current, status,
          version_number)
        VALUES (:id, :pid, 'Demo Base', CURRENT_DATE, :u, :g, 'Base', true,
                'Approved', 1)
    """), {"id": ap, "pid": pid, "u": admin.id, "g": uuid.uuid4()})

    bid = uuid.uuid4()
    db.execute(text("""
        INSERT INTO budgets (id, project_id, source_appraisal_id, version_number,
          version_label, is_current, status, created_from_appraisal_at,
          total_budget, total_actuals, total_committed_not_invoiced,
          total_forecast_to_complete, forecast_final_cost, variance_vs_budget,
          variance_pct, summary_refreshed_at, created_by_user_id)
        VALUES (:id, :pid, :ap, 1, 'v1', true, 'Active', NOW(),
                1000000, 0, 0, 1000000, 1000000, 0, 0, NOW(), :u)
    """), {"id": bid, "pid": pid, "ap": ap, "u": admin.id})

    lines = {}
    for name, order in [("Groundworks", 1), ("Roofing", 2), ("Landscaping", 3)]:
        lid = uuid.uuid4()
        db.execute(text("""
            INSERT INTO budget_lines (id, budget_id, cost_code_id, display_order,
              line_description, entity_id, ftc_method, original_budget,
              approved_changes, current_budget, actuals_to_date, committed_value,
              invoiced_against_commitment, committed_not_invoiced,
              forecast_to_complete, forecast_final_cost, variance_value,
              variance_pct, variance_status, is_locked, requires_attention)
            VALUES (:id, :bid, :cc, :ord, :ld, :ent, 'Manual',
                    500000, 0, 500000, 0, 0, 0, 0, 500000, 500000, 0, 0,
                    'Green', false, false)
        """), {"id": lid, "bid": bid, "cc": cc_by_line[name].id, "ord": order,
               "ld": name, "ent": entity_id})
        lines[name] = lid
    db.commit()

    def _po(num, line_specs):
        total = sum(Decimal(s["net"]) for s in line_specs)
        po = PurchaseOrder(
            tenant_id=admin.tenant_id, project_id=pid,
            po_number=f"PO-{num}-{sfx}", supplier_id=None,  # set below
            budget_id=bid, status="issued",
            subtotal_amount=total, vat_amount=Decimal("0"), total_amount=total,
            created_by=admin.id, updated_by=admin.id,
        )
        return po

    # supplier
    supplier_id = uuid.uuid4()
    db.execute(text("""
        INSERT INTO suppliers (id, tenant_id, name, created_by, updated_by)
        VALUES (:id, :t, 'Demo Supplier', :u, :u)
    """), {"id": supplier_id, "t": admin.tenant_id, "u": admin.id})
    db.commit()

    # PO-DEMO-A: two lines on Groundworks
    poA = _po("DEMO-A", [{"net": "10000"}, {"net": "5000"}])
    poA.supplier_id = supplier_id
    a1 = _po_line(poA, budget_line_id=lines["Groundworks"], net="10000",
                  cost_code=cc.code, line_number=1)
    a2 = _po_line(poA, budget_line_id=lines["Groundworks"], net="5000",
                  cost_code=cc.code, line_number=2, fully_receipted=True)
    db.add(poA); db.add(a1); db.add(a2)
    db.commit(); db.refresh(a1); db.refresh(a2)

    # PO-DEMO-B: one line on Roofing
    poB = _po("DEMO-B", [{"net": "8000"}])
    poB.supplier_id = supplier_id
    b1 = _po_line(poB, budget_line_id=lines["Roofing"], net="8000",
                  cost_code=cc.code, line_number=1)
    db.add(poB); db.add(b1)
    db.commit(); db.refresh(b1)

    # Bills: A1 ← £4,000 Posted (remaining 6,000); A2 ← £5,000 Posted (remaining 0)
    _bill(db, project_id=pid, entity_id=entity_id, budget_line_id=lines["Groundworks"],
          linked=a1.id, net="4000", user=user, perms=perms)
    _bill(db, project_id=pid, entity_id=entity_id, budget_line_id=lines["Groundworks"],
          linked=a2.id, net="5000", user=user, perms=perms)

    print("SEED_OK")
    print(f"PROJECT_ID={pid}")
    print(f"NEW_ACTUAL_PATH=/projects/{pid}/actuals/new")
    print(f"LINE_Groundworks={lines['Groundworks']}  (2 PO lines: £6,000.00 remaining of £10,000.00; one fully invoiced £0.00)")
    print(f"LINE_Roofing={lines['Roofing']}  (1 PO line: £8,000.00 remaining of £8,000.00)")
    print(f"LINE_Landscaping={lines['Landscaping']}  (NO POs → empty/standalone case)")
    print(f"PO_LINE_A1={a1.id}  PO_LINE_A2={a2.id}  PO_LINE_B1={b1.id}")
    db.close()


if __name__ == "__main__":
    main()
