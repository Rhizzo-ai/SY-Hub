"""Regression test for migration 0023 — appraisal_scenarios cascade delete.

Proves the FK cascade actually works through the ORM/DB session, not just
that pg_constraint says it should. Creates a minimal projects → appraisals
→ appraisal_scenarios chain via raw SQL, deletes the appraisal, asserts the
scenario row was cascade-deleted.

Pure-DB by design — the smoke test (test_c3_governance_smoke.py) is
HTTP-only and lives in a separate work stream. This file follows the
direct-DB pattern from test_appraisal_governance.py (create_engine +
engine.begin()).
"""
from __future__ import annotations

import os
import uuid

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


def test_deleting_appraisal_cascades_to_scenarios():
    """ON DELETE CASCADE on appraisal_scenarios.scenario_appraisal_id FK
    means deleting an appraisal must remove its linked scenario row."""
    eng = create_engine(DATABASE_URL, future=True)

    project_id = uuid.uuid4()
    appraisal_id = uuid.uuid4()
    appraisal_group_id = uuid.uuid4()
    scenario_id = uuid.uuid4()
    project_code = f"CASC-{uuid.uuid4().hex[:8].upper()}"

    try:
        with eng.begin() as c:
            # Reuse a seeded entity + the bootstrap admin user — both are
            # invariant fixtures created by `python -m app.bootstrap` and
            # asserted by verify.super_admin_user / verify.tenant invariants.
            entity_id = c.execute(text(
                "SELECT id FROM entities ORDER BY name LIMIT 1"
            )).scalar()
            assert entity_id is not None, "no seeded entity — bootstrap likely broken"

            user_id = c.execute(text(
                "SELECT id FROM users WHERE email = :e"
            ), {"e": os.environ["BOOTSTRAP_ADMIN_EMAIL"]}).scalar()
            assert user_id is not None, "bootstrap admin user missing"

            # 1. Minimal project.
            c.execute(text("""
                INSERT INTO projects (
                    id, project_code, name, project_type,
                    primary_entity_id, land_ownership_method,
                    site_address, site_postcode, created_by_user_id
                ) VALUES (
                    :id, :code, :name, 'Dev_Build',
                    :entity, 'Direct_Purchase',
                    '1 Cascade Test Way', 'SY1 1AA', :uid
                )
            """), {
                "id": project_id,
                "code": project_code,
                "name": f"Cascade Regression {project_code}",
                "entity": entity_id,
                "uid": user_id,
            })

            # 2. Minimal appraisal. appraisal_group_id is application-managed
            # (one group per (project, scenario_chain)), not auto-defaulted.
            c.execute(text("""
                INSERT INTO appraisals (
                    id, project_id, name, reference_date,
                    created_by_user_id, appraisal_group_id, scenario
                ) VALUES (
                    :id, :pid, :name, CURRENT_DATE,
                    :uid, :gid, 'Base'
                )
            """), {
                "id": appraisal_id,
                "pid": project_id,
                "name": "Cascade Base",
                "uid": user_id,
                "gid": appraisal_group_id,
            })

            # 3. Scenario row pointing at that appraisal. scenario_label='Base'
            # so parent_scenario_appraisal_id can be NULL (XOR check
            # ck_appraisal_scenarios_base_parent_xor).
            c.execute(text("""
                INSERT INTO appraisal_scenarios (
                    id, appraisal_group_id, scenario_appraisal_id,
                    parent_scenario_appraisal_id,
                    scenario_label, scenario_description, created_by_user_id
                ) VALUES (
                    :id, :gid, :sid, NULL,
                    'Base', 'Cascade regression test base scenario row.',
                    :uid
                )
            """), {
                "id": scenario_id,
                "gid": appraisal_group_id,
                "sid": appraisal_id,
                "uid": user_id,
            })

        # Sanity: the scenario row exists before delete.
        with eng.connect() as c:
            pre = c.execute(text(
                "SELECT 1 FROM appraisal_scenarios WHERE id = :id"
            ), {"id": scenario_id}).scalar()
            assert pre == 1, "setup failure: scenario row not inserted"

        # 4. Delete the appraisal — RESTRICT (pre-0023) would block this;
        # CASCADE (0023+) should cascade to delete the scenario row.
        with eng.begin() as c:
            c.execute(text(
                "DELETE FROM appraisals WHERE id = :id"
            ), {"id": appraisal_id})

        # 5. Assert the scenario row is gone (cascade fired).
        with eng.connect() as c:
            post = c.execute(text(
                "SELECT 1 FROM appraisal_scenarios WHERE id = :id"
            ), {"id": scenario_id}).scalar()
            assert post is None, (
                "cascade did NOT fire: scenario row still present after "
                "deleting parent appraisal"
            )

    finally:
        # Clean up the project we created (and any rows still hanging off it,
        # though after the assertion above none should remain). Run as a
        # best-effort sweep so a mid-test failure doesn't leak rows.
        with eng.begin() as c:
            c.execute(text(
                "DELETE FROM appraisal_scenarios WHERE id = :id"
            ), {"id": scenario_id})
            c.execute(text(
                "DELETE FROM appraisals WHERE id = :id"
            ), {"id": appraisal_id})
            c.execute(text(
                "DELETE FROM projects WHERE id = :id"
            ), {"id": project_id})
        eng.dispose()
