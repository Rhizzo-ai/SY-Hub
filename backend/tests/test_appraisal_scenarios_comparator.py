"""C4-tail — scenario comparator must not show RLV on a non-converged solve.

`get_group_comparator` previously surfaced `rlv_computed_land_value` regardless
of whether the solve converged. The router writes that column on EVERY solve
(including £0 / best-probe values for unreachable solves), so a failed solve
showed a misleading land figure on the side-by-side comparison screen.

These tests pin the display-honesty rule:
  - residual_land_value is non-null ONLY when a value exists AND rlv_converged is True.
  - rlv_converged is surfaced explicitly (True/False with a current appraisal,
    None when the scenario has no current appraisal).

Pure-DB, mirroring test_appraisal_scenarios_cascade.py (create_engine +
engine.begin() raw-SQL setup, then call the service through a Session).
"""
from __future__ import annotations

import os
import uuid
from decimal import Decimal

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models.appraisals import Appraisal
from app.services.appraisal_scenarios import get_group_comparator


load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]
_engine = create_engine(DATABASE_URL, future=True)
_Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def _seed_base_scenario(*, rlv_value, rlv_converged):
    """Create project → current 'Base' appraisal → scenario row.

    `rlv_value` is a Decimal or None; `rlv_converged` is True/False/None.
    Returns (project_id, appraisal_group_id, appraisal_id).
    """
    project_id = uuid.uuid4()
    appraisal_id = uuid.uuid4()
    appraisal_group_id = uuid.uuid4()
    scenario_id = uuid.uuid4()
    project_code = f"CMP-{uuid.uuid4().hex[:8].upper()}"

    with _engine.begin() as c:
        entity_id = c.execute(text(
            "SELECT id FROM entities ORDER BY name LIMIT 1"
        )).scalar()
        assert entity_id is not None, "no seeded entity — bootstrap likely broken"
        user_id = c.execute(text(
            "SELECT id FROM users WHERE email = :e"
        ), {"e": os.environ["BOOTSTRAP_ADMIN_EMAIL"]}).scalar()
        assert user_id is not None, "bootstrap admin user missing"

        c.execute(text("""
            INSERT INTO projects (
                id, project_code, name, project_type,
                primary_entity_id, land_ownership_method,
                site_address, site_postcode, created_by_user_id
            ) VALUES (
                :id, :code, :name, 'Dev_Build',
                :entity, 'Direct_Purchase',
                '1 Comparator Way', 'SY1 1AA', :uid
            )
        """), {"id": project_id, "code": project_code,
               "name": f"Comparator {project_code}", "entity": entity_id,
               "uid": user_id})

        # Current 'Base' appraisal with the RLV state under test.
        c.execute(text("""
            INSERT INTO appraisals (
                id, project_id, name, reference_date,
                created_by_user_id, appraisal_group_id, scenario,
                is_current, status, version_number,
                rlv_computed_land_value, rlv_converged
            ) VALUES (
                :id, :pid, :name, CURRENT_DATE,
                :uid, :gid, 'Base',
                true, 'Draft', 1,
                :rlv, :conv
            )
        """), {"id": appraisal_id, "pid": project_id, "name": "Comparator Base",
               "uid": user_id, "gid": appraisal_group_id,
               "rlv": rlv_value, "conv": rlv_converged})

        c.execute(text("""
            INSERT INTO appraisal_scenarios (
                id, appraisal_group_id, scenario_appraisal_id,
                parent_scenario_appraisal_id,
                scenario_label, scenario_description, created_by_user_id
            ) VALUES (
                :id, :gid, :sid, NULL,
                'Base', 'C4-tail comparator test base scenario.', :uid
            )
        """), {"id": scenario_id, "gid": appraisal_group_id,
               "sid": appraisal_id, "uid": user_id})

    return project_id, appraisal_group_id, appraisal_id


def _cleanup(project_id, appraisal_id):
    with _engine.begin() as c:
        # Deleting the appraisal cascades to its scenario row (FK 0023).
        c.execute(text("DELETE FROM appraisals WHERE id = :id"), {"id": appraisal_id})
        c.execute(text("DELETE FROM projects WHERE id = :id"), {"id": project_id})


def _base_row(group_id):
    db = _Session()
    try:
        payload = get_group_comparator(db, group_id)
    finally:
        db.close()
    base = [s for s in payload["scenarios"] if s["scenario_label"] == "Base"]
    assert base, "Base scenario missing from comparator payload"
    return base[0]


def test_comparator_hides_rlv_when_not_converged():
    """Non-converged solve with a stored land value → residual hidden."""
    pid, gid, aid = _seed_base_scenario(
        rlv_value=Decimal("123456.78"), rlv_converged=False,
    )
    try:
        row = _base_row(gid)
        assert row["residual_land_value"] is None
        assert row["rlv_converged"] is False
    finally:
        _cleanup(pid, aid)


def test_comparator_shows_rlv_when_converged():
    """Converged solve → residual shown as the string of the stored value."""
    pid, gid, aid = _seed_base_scenario(
        rlv_value=Decimal("123456.78"), rlv_converged=True,
    )
    try:
        row = _base_row(gid)
        db = _Session()
        try:
            stored = db.get(Appraisal, aid).rlv_computed_land_value
        finally:
            db.close()
        assert row["residual_land_value"] == str(stored)
        assert row["rlv_converged"] is True
    finally:
        _cleanup(pid, aid)


def test_comparator_rlv_none_when_never_run():
    """RLV never run (value None, converged None) → residual hidden, not 'True'."""
    pid, gid, aid = _seed_base_scenario(
        rlv_value=None, rlv_converged=None,
    )
    try:
        row = _base_row(gid)
        assert row["residual_land_value"] is None
        # bool(None) coerces to False per R2 — assert it is NOT True.
        assert row["rlv_converged"] is not True
    finally:
        _cleanup(pid, aid)
