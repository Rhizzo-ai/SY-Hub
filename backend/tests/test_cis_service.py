"""Chat 32 §R5 (Prompt 2.7) — CIS verification service-layer tests.

Acceptance gates 9-15 (append-only, status update, validation, no
update/delete path).

These tests poke services/cis directly to assert the contract that the
service module exposes — they do NOT go through HTTP.
"""
from __future__ import annotations

import inspect
import os
import uuid
from datetime import date, timedelta

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    yield e
    e.dispose()


@pytest.fixture(scope="module")
def tenant_and_user(engine):
    """Resolve a real tenant_id + super_admin user_id for direct service
    calls. These never write through HTTP so no MFA / cookie machinery."""
    with engine.connect() as c:
        row = c.execute(text(
            "SELECT t.id AS tenant_id, u.id AS user_id "
            "FROM tenants t, users u "
            "WHERE u.tenant_id = t.id "
            "  AND u.email = 'test-admin@example.test' "
            "LIMIT 1"
        )).first()
    assert row is not None, "test-admin user / tenant not seeded"
    return uuid.UUID(str(row.tenant_id)), uuid.UUID(str(row.user_id))


@pytest.fixture
def session(engine, tenant_and_user):
    """Yield a transactional Session and wipe everything we created at end."""
    tenant_id, user_id = tenant_and_user
    sess = Session(engine, future=True)
    try:
        yield sess
        sess.rollback()
    finally:
        # Hard cleanup outside the test's transaction (in case of commit).
        sess.close()
        with engine.begin() as c:
            c.execute(text(
                "DELETE FROM subcontractor_cis_verifications "
                "WHERE created_by = :uid"
            ), {"uid": str(user_id)})
            c.execute(text(
                "DELETE FROM suppliers WHERE created_by = :uid "
                "  AND name LIKE 'CISSVC-%'"
            ), {"uid": str(user_id)})


def _mk_supplier(
    sess: Session, tenant_id: uuid.UUID, user_id: uuid.UUID,
    *, supplier_type: str = "Subcontractor", name_suffix: str = "",
) -> uuid.UUID:
    from app.services.suppliers import create_supplier
    sx = uuid.uuid4().hex[:8].upper()
    row = create_supplier(
        sess, tenant_id, user_id,
        {
            "name": f"CISSVC-{name_suffix}-{sx}",
            "supplier_type": supplier_type,
            "utr": "1234567890" if supplier_type == "Subcontractor" else None,
        },
    )
    sess.commit()
    return row.id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRecordVerification:
    def test_record_creates_row_and_updates_cache(
        self, session, tenant_and_user,
    ):
        """Gate 9 + 11: record_verification creates an append-only row
        AND updates supplier.current_cis_status to the new match_status."""
        from app.services import cis as svc
        from app.models.suppliers import Supplier
        tenant_id, user_id = tenant_and_user
        sid = _mk_supplier(session, tenant_id, user_id, name_suffix="rec")
        # Initial cache state.
        s = session.get(Supplier, sid)
        assert s.current_cis_status == "Unverified"

        v = svc.record_verification(
            session, tenant_id, sid,
            verification_number="V12345",
            match_status="Gross",
            tax_rate_pct=0,
            verified_on=date.today(),
            expires_on=date.today() + timedelta(days=365 * 2),
            notes=None,
            actor_id=user_id,
        )
        session.commit()
        assert v.id is not None
        assert v.match_status == "Gross"

        session.refresh(s)
        assert s.current_cis_status == "Gross", (
            "supplier.current_cis_status must be repointed by record_verification"
        )

    def test_record_on_plain_supplier_rejected(self, session, tenant_and_user):
        """Gate 10: record_verification on a plain supplier → ValueError."""
        from app.services import cis as svc
        tenant_id, user_id = tenant_and_user
        sid = _mk_supplier(
            session, tenant_id, user_id,
            supplier_type="Supplier", name_suffix="plain",
        )
        with pytest.raises(ValueError, match="only valid for subcontractors"):
            svc.record_verification(
                session, tenant_id, sid,
                verification_number=None,
                match_status="Gross",
                tax_rate_pct=0,
                verified_on=date.today(),
                expires_on=None,
                notes=None,
                actor_id=user_id,
            )

    def test_second_verification_preserves_history(
        self, session, tenant_and_user,
    ):
        """Gate 12: a second verification creates a NEW row (history),
        prior row unchanged, current_cis_status repoints to the latest."""
        from app.services import cis as svc
        from app.models.suppliers import Supplier
        tenant_id, user_id = tenant_and_user
        sid = _mk_supplier(session, tenant_id, user_id, name_suffix="hist")

        v1 = svc.record_verification(
            session, tenant_id, sid,
            verification_number="V-OLD",
            match_status="Net", tax_rate_pct=20,
            verified_on=date(2024, 1, 1),
            expires_on=None, notes=None, actor_id=user_id,
        )
        session.commit()

        v2 = svc.record_verification(
            session, tenant_id, sid,
            verification_number="V-NEW",
            match_status="Gross", tax_rate_pct=0,
            verified_on=date(2025, 1, 1),
            expires_on=None, notes=None, actor_id=user_id,
        )
        session.commit()

        # Both rows live in the table.
        from app.models.cis import SubcontractorCISVerification
        rows = list(session.query(SubcontractorCISVerification).filter(
            SubcontractorCISVerification.supplier_id == sid,
        ).all())
        assert len(rows) == 2
        # Prior row unchanged.
        v1_reloaded = session.get(SubcontractorCISVerification, v1.id)
        assert v1_reloaded.match_status == "Net"
        assert v1_reloaded.verification_number == "V-OLD"
        # Cache repoints.
        s = session.get(Supplier, sid)
        assert s.current_cis_status == "Gross"

    def test_invalid_match_status_rejected(self, session, tenant_and_user):
        """Gate 13: match_status outside {Gross,Net,Unmatched} → ValueError."""
        from app.services import cis as svc
        tenant_id, user_id = tenant_and_user
        sid = _mk_supplier(session, tenant_id, user_id, name_suffix="bad")
        with pytest.raises(ValueError, match="match_status"):
            svc.record_verification(
                session, tenant_id, sid,
                verification_number=None,
                match_status="Bogus",
                tax_rate_pct=0,
                verified_on=date.today(),
                expires_on=None, notes=None, actor_id=user_id,
            )


class TestQueryHelpers:
    def test_get_current_returns_newest_by_verified_on(
        self, session, tenant_and_user,
    ):
        """Gate 14: get_current_verification returns newest by verified_on."""
        from app.services import cis as svc
        tenant_id, user_id = tenant_and_user
        sid = _mk_supplier(session, tenant_id, user_id, name_suffix="cur")

        # Record OUT OF ORDER: oldest verified_on last.
        svc.record_verification(
            session, tenant_id, sid,
            verification_number="V-NEW", match_status="Gross",
            tax_rate_pct=0, verified_on=date(2025, 6, 1),
            expires_on=None, notes=None, actor_id=user_id,
        )
        svc.record_verification(
            session, tenant_id, sid,
            verification_number="V-OLD", match_status="Net",
            tax_rate_pct=20, verified_on=date(2024, 1, 1),
            expires_on=None, notes=None, actor_id=user_id,
        )
        session.commit()

        current = svc.get_current_verification(session, tenant_id, sid)
        assert current is not None
        assert current.verified_on == date(2025, 6, 1)
        assert current.verification_number == "V-NEW"

    def test_list_returns_none_for_supplier_with_no_history(
        self, session, tenant_and_user,
    ):
        from app.services import cis as svc
        tenant_id, user_id = tenant_and_user
        sid = _mk_supplier(session, tenant_id, user_id, name_suffix="empty")
        assert svc.get_current_verification(session, tenant_id, sid) is None
        assert svc.list_verifications(session, tenant_id, sid) == []


class TestAppendOnlyContract:
    def test_no_update_or_delete_helpers_exposed(self):
        """Gate 15: services/cis exposes NO update/delete functions.

        Append-only is enforced at the API layer (no PATCH/DELETE
        endpoints — asserted in test_cis_api) and at the service layer
        by simply not providing helpers for those verbs.
        """
        from app.services import cis as svc
        public_names = [
            n for n, m in inspect.getmembers(svc)
            if inspect.isfunction(m) and not n.startswith("_")
        ]
        forbidden = ("update", "delete", "patch", "remove")
        for name in public_names:
            lower = name.lower()
            for verb in forbidden:
                assert verb not in lower, (
                    f"services/cis must not expose a {verb!r}-style function; "
                    f"found {name!r}"
                )
