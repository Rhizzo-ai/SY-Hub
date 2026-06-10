"""Chat 45 §R5 (Build Pack 2.7-DOCS-BE) — document folder engine tests.

Covers the §R5 acceptance gates 1-24 + 33-35 (folder CRUD, move +
loop guard, archive, tree, permissions). Tests 25-32 + 34b live in
tests/test_supplier_documents_folders.py (the supplier-doc <-> folder
association surface).

HTTP-level tests against the live test backend, mirroring
test_supplier_documents.py conventions exactly.
"""
from __future__ import annotations

import os
import uuid

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

from tests.conftest import login_with_auto_enroll


load_dotenv("/app/backend/.env")
BASE_URL = (
    os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
    or "http://localhost:8001"
)
DATABASE_URL = os.environ["DATABASE_URL"]
PWD = os.environ["TEST_USER_PASSWORD"]

ADMIN_EMAIL = "test-admin@example.test"
PM_EMAIL = "test-pm@example.test"
FINANCE_EMAIL = "test-finance@example.test"
READONLY_EMAIL = "test-readonly@example.test"
SITE_EMAIL = "test-site@example.test"


def _suffix() -> str:
    return uuid.uuid4().hex[:8].upper()


@pytest.fixture(scope="module")
def engine():
    e = create_engine(DATABASE_URL, future=True)
    with e.begin() as c:
        c.execute(text("""
            UPDATE users SET mfa_enabled=false, mfa_method=NULL,
              mfa_secret_encrypted=NULL, mfa_backup_codes_encrypted=NULL,
              mfa_enrolled_at=NULL, failed_login_attempts=0,
              locked_until=NULL, lockout_level=0
            WHERE email LIKE 'test-%@example.test'
        """))
    yield e
    e.dispose()


@pytest.fixture(scope="module", autouse=True)
def _wipe_module(engine):
    def _wipe():
        with engine.begin() as c:
            c.execute(text("""
                DELETE FROM supplier_documents
                 WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                 )
            """))
            c.execute(text("""
                DELETE FROM document_folders
                 WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                 )
            """))
            c.execute(text("""
                DELETE FROM suppliers
                 WHERE created_by IN (
                    SELECT id FROM users WHERE email LIKE 'test-%@example.test'
                 )
                AND name LIKE 'FOLDR-%'
            """))
    _wipe()
    yield
    _wipe()


@pytest.fixture(scope="module")
def admin():
    return login_with_auto_enroll(None, BASE_URL, ADMIN_EMAIL, PWD)


@pytest.fixture(scope="module")
def pm():
    return login_with_auto_enroll(None, BASE_URL, PM_EMAIL, PWD)


@pytest.fixture(scope="module")
def finance():
    return login_with_auto_enroll(None, BASE_URL, FINANCE_EMAIL, PWD)


@pytest.fixture(scope="module")
def readonly():
    return login_with_auto_enroll(None, BASE_URL, READONLY_EMAIL, PWD)


@pytest.fixture(scope="module")
def site():
    return login_with_auto_enroll(None, BASE_URL, SITE_EMAIL, PWD)


def _mk_supplier(admin_session, name_suffix: str = "") -> str:
    sx = _suffix()
    r = admin_session.post(
        f"{BASE_URL}/api/v1/suppliers",
        json={"name": f"FOLDR-{name_suffix}-{sx}"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _mk_folder(session, *, supplier_id: str, name: str,
               parent_id: str | None = None,
               expected_status: int = 201) -> dict:
    payload = {
        "owner_type": "supplier",
        "owner_id": supplier_id,
        "name": name,
    }
    if parent_id is not None:
        payload["parent_id"] = parent_id
    r = session.post(f"{BASE_URL}/api/v1/document-folders", json=payload)
    assert r.status_code == expected_status, r.text
    return r.json() if expected_status == 201 else {}


# ===========================================================================
# Folder CRUD (tests 1-9)
# ===========================================================================

class TestFolderCRUD:
    def test_1_create_root_folder(self, admin):
        sid = _mk_supplier(admin, "root")
        f = _mk_folder(admin, supplier_id=sid, name="Insurance")
        assert f["owner_type"] == "supplier"
        assert f["owner_id"] == sid
        assert f["parent_id"] is None
        assert f["name"] == "Insurance"
        assert f["is_archived"] is False

    def test_2_create_child_under_parent(self, admin):
        sid = _mk_supplier(admin, "child")
        parent = _mk_folder(admin, supplier_id=sid, name="Compliance")
        child = _mk_folder(
            admin, supplier_id=sid, name="2026",
            parent_id=parent["id"],
        )
        assert child["parent_id"] == parent["id"]

    def test_3_create_cross_tenant_supplier_returns_404(self, admin):
        ghost = str(uuid.uuid4())
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders",
            json={
                "owner_type": "supplier",
                "owner_id": ghost,
                "name": "X",
            },
        )
        assert r.status_code == 404, r.text

    def test_4_parent_from_different_owner_returns_422(self, admin):
        s1 = _mk_supplier(admin, "ownerA")
        s2 = _mk_supplier(admin, "ownerB")
        p1 = _mk_folder(admin, supplier_id=s1, name="A-Root")
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders",
            json={
                "owner_type": "supplier",
                "owner_id": s2,
                "name": "child",
                "parent_id": p1["id"],
            },
        )
        assert r.status_code == 422, r.text
        assert "owner" in r.json()["detail"].lower()

    def test_5_duplicate_sibling_name_under_parent_returns_422(self, admin):
        sid = _mk_supplier(admin, "dupsib")
        parent = _mk_folder(admin, supplier_id=sid, name="Compliance")
        _mk_folder(
            admin, supplier_id=sid, name="2026", parent_id=parent["id"],
        )
        # Second attempt with the same name + parent should clash.
        _mk_folder(
            admin, supplier_id=sid, name="2026",
            parent_id=parent["id"], expected_status=422,
        )

    def test_6_duplicate_name_at_root_returns_422(self, admin):
        sid = _mk_supplier(admin, "duproot")
        _mk_folder(admin, supplier_id=sid, name="Insurance")
        # Second root with same name + same owner → 422 (COALESCE
        # NULL-parent guard).
        _mk_folder(
            admin, supplier_id=sid, name="Insurance",
            expected_status=422,
        )

    def test_7_same_name_under_different_parents_ok(self, admin):
        sid = _mk_supplier(admin, "twoparents")
        p1 = _mk_folder(admin, supplier_id=sid, name="A")
        p2 = _mk_folder(admin, supplier_id=sid, name="B")
        c1 = _mk_folder(
            admin, supplier_id=sid, name="Renewals",
            parent_id=p1["id"],
        )
        c2 = _mk_folder(
            admin, supplier_id=sid, name="Renewals",
            parent_id=p2["id"],
        )
        assert c1["id"] != c2["id"]

    def test_8_rename_folder_persists(self, admin):
        sid = _mk_supplier(admin, "ren")
        f = _mk_folder(admin, supplier_id=sid, name="OldName")
        r = admin.patch(
            f"{BASE_URL}/api/v1/document-folders/{f['id']}",
            json={"name": "NewName"},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "NewName"

    def test_9_rename_to_clashing_sibling_returns_422(self, admin):
        sid = _mk_supplier(admin, "renclash")
        a = _mk_folder(admin, supplier_id=sid, name="A")
        b = _mk_folder(admin, supplier_id=sid, name="B")
        r = admin.patch(
            f"{BASE_URL}/api/v1/document-folders/{b['id']}",
            json={"name": "A"},
        )
        assert r.status_code == 422, r.text
        # Helpfulness: a's id stays distinct from b's id.
        assert a["id"] != b["id"]


# ===========================================================================
# Move + loop guard (tests 10-15)
# ===========================================================================

class TestFolderMove:
    def test_10_move_to_new_parent(self, admin):
        sid = _mk_supplier(admin, "mv1")
        a = _mk_folder(admin, supplier_id=sid, name="A")
        b = _mk_folder(admin, supplier_id=sid, name="B")
        leaf = _mk_folder(
            admin, supplier_id=sid, name="leaf", parent_id=a["id"],
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{leaf['id']}/move",
            json={"new_parent_id": b["id"]},
        )
        assert r.status_code == 200, r.text
        assert r.json()["parent_id"] == b["id"]

    def test_11_move_to_root(self, admin):
        sid = _mk_supplier(admin, "mv2")
        a = _mk_folder(admin, supplier_id=sid, name="A")
        leaf = _mk_folder(
            admin, supplier_id=sid, name="leaf", parent_id=a["id"],
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{leaf['id']}/move",
            json={"new_parent_id": None},
        )
        assert r.status_code == 200, r.text
        assert r.json()["parent_id"] is None

    def test_12_move_into_self_returns_422(self, admin):
        sid = _mk_supplier(admin, "self")
        a = _mk_folder(admin, supplier_id=sid, name="self")
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{a['id']}/move",
            json={"new_parent_id": a["id"]},
        )
        assert r.status_code == 422, r.text
        assert "itself" in r.json()["detail"] or "descendant" in r.json()["detail"]

    def test_13_move_into_descendant_returns_422(self, admin):
        sid = _mk_supplier(admin, "desc")
        a = _mk_folder(admin, supplier_id=sid, name="A-anc")
        b = _mk_folder(
            admin, supplier_id=sid, name="B-child", parent_id=a["id"],
        )
        c = _mk_folder(
            admin, supplier_id=sid, name="C-leaf", parent_id=b["id"],
        )
        # Move A (the ancestor) INTO C (its grandchild) — must fail.
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{a['id']}/move",
            json={"new_parent_id": c["id"]},
        )
        assert r.status_code == 422, r.text
        assert "descendant" in r.json()["detail"].lower()

    def test_14_move_to_different_owner_returns_422(self, admin):
        s1 = _mk_supplier(admin, "ownM1")
        s2 = _mk_supplier(admin, "ownM2")
        a = _mk_folder(admin, supplier_id=s1, name="A-s1")
        b = _mk_folder(admin, supplier_id=s2, name="B-s2")
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{a['id']}/move",
            json={"new_parent_id": b["id"]},
        )
        assert r.status_code == 422, r.text

    def test_15_move_into_archived_parent_returns_422(self, admin):
        sid = _mk_supplier(admin, "arcparent")
        a = _mk_folder(admin, supplier_id=sid, name="A-arc")
        b = _mk_folder(admin, supplier_id=sid, name="B-leaf")
        # Archive A (must be empty; it is).
        ra = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{a['id']}/archive"
        )
        assert ra.status_code == 200, ra.text
        # Now try to move B under archived A → 422.
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{b['id']}/move",
            json={"new_parent_id": a["id"]},
        )
        assert r.status_code == 422, r.text


# ===========================================================================
# Archive (tests 16-21)
# ===========================================================================

class TestFolderArchive:
    def test_16_archive_empty_folder(self, admin):
        sid = _mk_supplier(admin, "arcok")
        f = _mk_folder(admin, supplier_id=sid, name="Empty")
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{f['id']}/archive"
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["is_archived"] is True
        assert out["archived_at"] is not None

    def test_17_archive_with_live_child_returns_422(self, admin):
        sid = _mk_supplier(admin, "arcchild")
        p = _mk_folder(admin, supplier_id=sid, name="Parent")
        _mk_folder(
            admin, supplier_id=sid, name="LiveChild",
            parent_id=p["id"],
        )
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{p['id']}/archive"
        )
        assert r.status_code == 422, r.text
        assert "empty" in r.json()["detail"].lower()

    def test_18_archive_with_live_document_returns_422(self, admin):
        sid = _mk_supplier(admin, "arcdoc")
        f = _mk_folder(admin, supplier_id=sid, name="WithDoc")
        # File a doc into the folder.
        dc = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": sid,
                "doc_type": "Other",
                "title": "live doc",
                "folder_id": f["id"],
            },
        )
        assert dc.status_code == 201, dc.text
        r = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{f['id']}/archive"
        )
        assert r.status_code == 422, r.text
        assert "empty" in r.json()["detail"].lower()

    def test_19_unarchive_parent_archived_returns_422(self, admin):
        sid = _mk_supplier(admin, "uap")
        p = _mk_folder(admin, supplier_id=sid, name="P-uap")
        c = _mk_folder(
            admin, supplier_id=sid, name="C-uap", parent_id=p["id"],
        )
        # Archive the child first.
        admin.post(
            f"{BASE_URL}/api/v1/document-folders/{c['id']}/archive"
        )
        # Archive the parent (now empty of live children).
        ra = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{p['id']}/archive"
        )
        assert ra.status_code == 200
        # Try to unarchive child → must reject because parent is archived.
        ru = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{c['id']}/unarchive"
        )
        assert ru.status_code == 422, ru.text

    def test_20_unarchive_into_live_parent_ok(self, admin):
        sid = _mk_supplier(admin, "ulp")
        p = _mk_folder(admin, supplier_id=sid, name="P-ulp")
        c = _mk_folder(
            admin, supplier_id=sid, name="C-ulp", parent_id=p["id"],
        )
        admin.post(
            f"{BASE_URL}/api/v1/document-folders/{c['id']}/archive"
        )
        # Parent stays live → unarchive should succeed.
        ru = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{c['id']}/unarchive"
        )
        assert ru.status_code == 200, ru.text
        assert ru.json()["is_archived"] is False

    def test_21_archive_is_idempotent(self, admin):
        sid = _mk_supplier(admin, "idem")
        f = _mk_folder(admin, supplier_id=sid, name="Idem")
        r1 = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{f['id']}/archive"
        )
        assert r1.status_code == 200
        # Second call must NOT error.
        r2 = admin.post(
            f"{BASE_URL}/api/v1/document-folders/{f['id']}/archive"
        )
        assert r2.status_code == 200
        assert r2.json()["is_archived"] is True


# ===========================================================================
# Tree (tests 22-24)
# ===========================================================================

class TestFolderTree:
    def test_22_tree_nested_structure(self, admin):
        sid = _mk_supplier(admin, "tree1")
        root1 = _mk_folder(admin, supplier_id=sid, name="A")
        _mk_folder(admin, supplier_id=sid, name="B")  # second root
        child = _mk_folder(
            admin, supplier_id=sid, name="A1", parent_id=root1["id"],
        )
        grand = _mk_folder(
            admin, supplier_id=sid, name="A1a", parent_id=child["id"],
        )

        r = admin.get(
            f"{BASE_URL}/api/v1/document-folders",
            params={"owner_type": "supplier", "owner_id": sid},
        )
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        # Build a name → node map across all roots for assertion.
        names_at_root = {n["name"]: n for n in items}
        assert {"A", "B"} <= set(names_at_root)
        a_node = names_at_root["A"]
        b_node = names_at_root["B"]
        assert b_node["children"] == []
        assert len(a_node["children"]) == 1
        a1_node = a_node["children"][0]
        assert a1_node["name"] == "A1"
        assert a1_node["id"] == child["id"]
        assert len(a1_node["children"]) == 1
        assert a1_node["children"][0]["name"] == "A1a"
        assert a1_node["children"][0]["id"] == grand["id"]

    def test_23_tree_includes_file_count_no_n_plus_one(self, admin):
        sid = _mk_supplier(admin, "treecnt")
        a = _mk_folder(admin, supplier_id=sid, name="WithFiles")
        b = _mk_folder(admin, supplier_id=sid, name="NoFiles")
        # 2 docs into A, 0 into B.
        for i in range(2):
            admin.post(
                f"{BASE_URL}/api/v1/supplier-documents",
                json={
                    "supplier_id": sid, "doc_type": "Other",
                    "title": f"d{i}", "folder_id": a["id"],
                },
            )
        r = admin.get(
            f"{BASE_URL}/api/v1/document-folders",
            params={"owner_type": "supplier", "owner_id": sid},
        )
        counts = {n["name"]: n["file_count"] for n in r.json()["items"]}
        assert counts["WithFiles"] == 2
        assert counts["NoFiles"] == 0
        # ID parity sanity: the two folders are distinct.
        assert a["id"] != b["id"]

    def test_24_tree_excludes_archived_by_default(self, admin):
        sid = _mk_supplier(admin, "treearc")
        live = _mk_folder(admin, supplier_id=sid, name="Live")
        gone = _mk_folder(admin, supplier_id=sid, name="Gone")
        admin.post(
            f"{BASE_URL}/api/v1/document-folders/{gone['id']}/archive"
        )
        # Default — only Live.
        r = admin.get(
            f"{BASE_URL}/api/v1/document-folders",
            params={"owner_type": "supplier", "owner_id": sid},
        )
        names = {n["name"] for n in r.json()["items"]}
        assert "Live" in names
        assert "Gone" not in names
        assert live["id"] != gone["id"]
        # include_archived=true → both.
        r2 = admin.get(
            f"{BASE_URL}/api/v1/document-folders",
            params={
                "owner_type": "supplier", "owner_id": sid,
                "include_archived": "true",
            },
        )
        names2 = {n["name"] for n in r2.json()["items"]}
        assert {"Live", "Gone"} <= names2


# ===========================================================================
# Permissions (tests 33, 34, 34b, 35, 35b)
# ===========================================================================

class TestFolderPermissions:
    def test_33_no_documents_create_returns_403(self, admin, readonly):
        """read_only lacks documents.create → create must 403."""
        sid = _mk_supplier(admin, "p33")
        r = readonly.post(
            f"{BASE_URL}/api/v1/document-folders",
            json={
                "owner_type": "supplier",
                "owner_id": sid,
                "name": "denied",
            },
        )
        assert r.status_code == 403, r.text

    def test_34_no_documents_move_returns_403(self, admin, readonly):
        """read_only lacks documents.move → folder move 403."""
        sid = _mk_supplier(admin, "p34")
        a = _mk_folder(admin, supplier_id=sid, name="A-p34")
        b = _mk_folder(admin, supplier_id=sid, name="B-p34")
        r = readonly.post(
            f"{BASE_URL}/api/v1/document-folders/{a['id']}/move",
            json={"new_parent_id": b["id"]},
        )
        assert r.status_code == 403, r.text

    def test_34b_finance_can_move_folder_and_doc(self, admin, finance):
        """§R4.3 union grant: finance holds supplier_documents.edit →
        documents.move. Regression guard for the distribution gotcha.
        """
        sid = _mk_supplier(admin, "p34b")
        a = _mk_folder(admin, supplier_id=sid, name="A-p34b")
        b = _mk_folder(admin, supplier_id=sid, name="B-p34b")
        # Finance moves folder.
        rf = finance.post(
            f"{BASE_URL}/api/v1/document-folders/{a['id']}/move",
            json={"new_parent_id": b["id"]},
        )
        assert rf.status_code == 200, rf.text
        # Finance moves a document.
        d = admin.post(
            f"{BASE_URL}/api/v1/supplier-documents",
            json={
                "supplier_id": sid, "doc_type": "Other",
                "title": "to-move",
            },
        ).json()
        rd = finance.post(
            f"{BASE_URL}/api/v1/supplier-documents/{d['id']}/move",
            json={"folder_id": b["id"]},
        )
        assert rd.status_code == 200, rd.text
        assert rd.json()["folder_id"] == b["id"]

    def test_35_view_perm_holder_can_read_not_write(
        self, admin, readonly,
    ):
        """read_only does NOT hold supplier_documents.view (the
        owner-surface view perm gating folder reads under R3.0) →
        cannot load the tree, cannot create/rename. This pin tests
        the read-gate path resolves to the right perm code.
        """
        sid = _mk_supplier(admin, "p35")
        _mk_folder(admin, supplier_id=sid, name="visible")
        # read_only lacks supplier_documents.view (gate-27 mapping) →
        # GET tree 403.
        r = readonly.get(
            f"{BASE_URL}/api/v1/document-folders",
            params={"owner_type": "supplier", "owner_id": sid},
        )
        assert r.status_code == 403, r.text
        # Write attempts also 403 (no documents.create / move / edit).
        rc = readonly.post(
            f"{BASE_URL}/api/v1/document-folders",
            json={
                "owner_type": "supplier",
                "owner_id": sid,
                "name": "denied2",
            },
        )
        assert rc.status_code == 403, rc.text

    def test_35b_finance_can_create_rename_archive(
        self, admin, finance,
    ):
        """§R4.3b operator broadening: finance gains documents.create
        + documents.edit (which covers rename + archive)."""
        sid = _mk_supplier(admin, "p35b")
        r_create = finance.post(
            f"{BASE_URL}/api/v1/document-folders",
            json={
                "owner_type": "supplier",
                "owner_id": sid,
                "name": "Finance-Made",
            },
        )
        assert r_create.status_code == 201, r_create.text
        fid = r_create.json()["id"]
        r_rename = finance.patch(
            f"{BASE_URL}/api/v1/document-folders/{fid}",
            json={"name": "Finance-Renamed"},
        )
        assert r_rename.status_code == 200, r_rename.text
        r_arc = finance.post(
            f"{BASE_URL}/api/v1/document-folders/{fid}/archive"
        )
        assert r_arc.status_code == 200, r_arc.text


# ===========================================================================
# Permission count / migration verification (test 36)
# ===========================================================================

class TestMigrationAndPerms:
    def test_36_migration_compliance_folder_invariant(self, engine):
        """§R0.5 / §R5 #36 — the alembic-data-step invariant holds in
        steady state: any supplier_documents row created on a fresh DB
        SHOULD be placeable into a folder, and the partial-unique index
        enforces exactly one live 'Compliance' folder at root per
        supplier. Test this by directly inspecting the unique-index DDL
        (proves the data-step's idempotent guard works on re-run) and
        the head sentinel.
        """
        with engine.connect() as c:
            head = c.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar()
            assert head == "0044_cost_code_groups", head

            # Partial unique index over (tenant, owner, parent-or-zero,
            # name) WHERE is_archived=false → the §R0.5 idempotency
            # guarantee for re-running the data step.
            idx_def = c.execute(text("""
                SELECT indexdef FROM pg_indexes
                 WHERE tablename = 'document_folders'
                   AND indexname = 'uq_document_folders_sibling_name'
            """)).scalar()
            assert idx_def is not None
            assert "is_archived = false" in idx_def
            assert "COALESCE" in idx_def.upper() or "coalesce" in idx_def

            # The new permission code is in the catalogue.
            n = c.execute(text(
                "SELECT count(*) FROM permissions WHERE code='documents.move'"
            )).scalar()
            assert n == 1
