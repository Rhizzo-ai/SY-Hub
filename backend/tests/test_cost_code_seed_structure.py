"""B88 Pack 1 — Gate 4 §7.4 — canonical cost-code structure tests.

Verifies the post-seed truth shipped by
`scripts/seed_cost_code_structure.py`:

  * exactly 9 parent groups, canonical codes "1".."9"
  * Construction (parent code "4") has `allows_subgroups = True`;
    every other parent has `allows_subgroups = False`
  * exactly 10 Construction subgroups, codes "4.00".."4.09", all
    parented at Construction; the operator-resolved 4.06 / 4.07 /
    4.08 numbering is present (Prefab/MMC, Existing Buildings,
    External Works); no duplicate-4.08 collision
  * every canonical cost code (129 of them) lands at its canonical
    (sub)group; per-prefix counts match Build Pack §5.3
  * Construction-prefixed codes hang off their subgroup, NOT off "4"
  * the seed is idempotent: running it twice produces identical
    section + cost_code counts
  * extras (live ACC-04..08 on this pod) are reported by the diff
    but NOT deleted — they remain in the DB
"""
from __future__ import annotations

import os
from collections import Counter

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv("/app/backend/.env")
DATABASE_URL = os.environ["DATABASE_URL"]


# --------------------------------------------------------------------------
# Canonical truth (Build Pack §5.1, §5.2, §5.3) — kept here as a literal
# so a regression on the seed script is loud and obvious.
# --------------------------------------------------------------------------

PARENT_CODES = ["1", "2", "3", "4", "5", "6", "7", "8", "9"]
SUBGROUP_CODES = [
    "4.00", "4.01", "4.02", "4.03", "4.04",
    "4.05", "4.06", "4.07", "4.08", "4.09",
]
SUBGROUP_NAMES = {
    "4.00": "Facilitating Works",
    "4.01": "Substructure",
    "4.02": "Superstructure",
    "4.03": "Internal Finishes",
    "4.04": "Fittings & Equipment",
    "4.05": "Services",
    "4.06": "Prefab / MMC",
    "4.07": "Existing Buildings",
    "4.08": "External Works",
    "4.09": "Preliminaries",
}
PREFIX_TO_GROUP_CODE = {
    "ACQ": "1", "PLN": "2", "DES": "3",
    "FAC": "4.00", "SUB": "4.01", "SUP": "4.02", "INT": "4.03",
    "FIT": "4.04", "SER": "4.05", "PRE": "4.06", "EXB": "4.07",
    "EXT": "4.08", "PRL": "4.09",
    "SAL": "5", "FIN": "6", "OHD": "7", "ACC": "8", "CTG": "9",
}
CANONICAL_PER_PREFIX = {
    "ACQ": 10, "PLN": 9, "DES": 9,
    "FAC": 5, "SUB": 5, "SUP": 10, "INT": 6,
    "FIT": 5, "SER": 10, "PRE": 1, "EXB": 3,
    "EXT": 9, "PRL": 16,
    "SAL": 10, "FIN": 5, "OHD": 8, "ACC": 3, "CTG": 5,
}
CANONICAL_TOTAL = sum(CANONICAL_PER_PREFIX.values())  # = 129


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def db_engine():
    e = create_engine(DATABASE_URL, future=True)
    try:
        yield e
    finally:
        e.dispose()


@pytest.fixture(scope="module", autouse=True)
def _ensure_seed():
    """Run the canonical seed once before this test module starts.

    Idempotent — safe even if a previous module-level run already
    converged the DB. The idempotency test below runs the seed a
    SECOND time and asserts row-count parity.
    """
    from scripts.seed_cost_code_structure import run
    run()
    yield


def _section_id(db_engine, code: str) -> str:
    with db_engine.connect() as c:
        sid = c.execute(text(
            "SELECT id FROM cost_code_sections WHERE code = :c"
        ), {"c": code}).scalar()
    assert sid is not None, f"section {code!r} missing after seed"
    return str(sid)


# --------------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------------

class TestParentGroups:

    def test_exactly_nine_parent_groups(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code FROM cost_code_sections
                WHERE parent_section_id IS NULL
                ORDER BY display_order
            """)).fetchall()
        codes = [r.code for r in rows]
        assert codes == PARENT_CODES, codes

    def test_only_construction_allows_subgroups(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code, allows_subgroups
                FROM cost_code_sections
                WHERE parent_section_id IS NULL
                ORDER BY display_order
            """)).fetchall()
        allows = {r.code: bool(r.allows_subgroups) for r in rows}
        assert allows["4"] is True, allows
        for code in PARENT_CODES:
            if code == "4":
                continue
            assert allows[code] is False, (
                f"section {code!r} unexpectedly has allows_subgroups=True"
            )


class TestConstructionSubgroups:

    def test_exactly_ten_subgroups(self, db_engine):
        construction_id = _section_id(db_engine, "4")
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code, name, display_order
                FROM cost_code_sections
                WHERE parent_section_id = :p
                ORDER BY display_order
            """), {"p": construction_id}).fetchall()
        codes = [r.code for r in rows]
        assert codes == SUBGROUP_CODES, codes

    def test_subgroup_names_canonical(self, db_engine):
        construction_id = _section_id(db_engine, "4")
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code, name FROM cost_code_sections
                WHERE parent_section_id = :p
            """), {"p": construction_id}).fetchall()
        names = {r.code: r.name for r in rows}
        for code, expected_name in SUBGROUP_NAMES.items():
            assert names[code] == expected_name, (
                f"{code}: got {names[code]!r}, expected {expected_name!r}"
            )

    def test_operator_resolved_renumbering(self, db_engine):
        """Spreadsheet had a duplicate-4.08 collision; operator locked:
        4.06 = Prefab/MMC, 4.07 = Existing Buildings,
        4.08 = External Works. No collision must remain.
        """
        construction_id = _section_id(db_engine, "4")
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code, name FROM cost_code_sections
                WHERE parent_section_id = :p
            """), {"p": construction_id}).fetchall()
        m = {r.code: r.name for r in rows}
        assert m.get("4.06") == "Prefab / MMC"
        assert m.get("4.07") == "Existing Buildings"
        assert m.get("4.08") == "External Works"
        # No duplicate code at all.
        codes = [r.code for r in rows]
        assert len(codes) == len(set(codes)), (
            f"duplicate subgroup code detected: {codes}"
        )

    def test_only_construction_has_subgroups(self, db_engine):
        """Every section with parent_section_id IS NOT NULL must
        descend from Construction."""
        construction_id = _section_id(db_engine, "4")
        with db_engine.connect() as c:
            other_subgroups = c.execute(text("""
                SELECT code FROM cost_code_sections
                WHERE parent_section_id IS NOT NULL
                  AND parent_section_id != :p
            """), {"p": construction_id}).fetchall()
        assert other_subgroups == [], (
            f"non-Construction subgroups found: {other_subgroups}"
        )

    def test_subgroups_all_have_allows_subgroups_false(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code, allows_subgroups
                FROM cost_code_sections
                WHERE parent_section_id IS NOT NULL
            """)).fetchall()
        for r in rows:
            assert bool(r.allows_subgroups) is False, (
                f"subgroup {r.code} has allows_subgroups=True (3-level forbidden)"
            )


class TestCanonicalCodes:

    def test_canonical_total_is_129(self, db_engine):
        """All 129 canonical (prefix, sequence) pairs are present
        in the DB. Extras (e.g. ACC-04..08) are scoped OUT — they're
        verified separately in TestExtras.
        """
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT prefix, sequence FROM cost_codes"
            )).fetchall()
        live = {(r.prefix, r.sequence) for r in rows}
        canonical = {
            (p, s) for p, n in CANONICAL_PER_PREFIX.items() for s in range(1, n + 1)
        }
        assert len(canonical) == 129
        missing = canonical - live
        assert missing == set(), f"canonical codes missing from DB: {missing}"

    def test_per_prefix_canonical_counts(self, db_engine):
        """For each canonical prefix, the count of in-range sequences
        (1..canonical_max) matches Build Pack §5.3."""
        with db_engine.connect() as c:
            rows = c.execute(text(
                "SELECT prefix, sequence FROM cost_codes"
            )).fetchall()
        live = Counter()
        for r in rows:
            cap = CANONICAL_PER_PREFIX.get(r.prefix)
            if cap is not None and 1 <= r.sequence <= cap:
                live[r.prefix] += 1
        for prefix, expected in CANONICAL_PER_PREFIX.items():
            assert live[prefix] == expected, (
                f"{prefix}: got {live[prefix]}, expected {expected}"
            )

    def test_every_code_points_at_canonical_section(self, db_engine):
        """For every canonical code, `section_id` must match the
        section that owns its prefix (parent for non-Construction
        prefixes; subgroup for FAC/SUB/SUP/INT/FIT/SER/PRE/EXB/EXT/PRL).
        """
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT cc.code, cc.prefix, cc.sequence,
                       s.code AS section_code
                FROM cost_codes cc
                JOIN cost_code_sections s ON s.id = cc.section_id
            """)).fetchall()
        mismatches = []
        for r in rows:
            canonical_cap = CANONICAL_PER_PREFIX.get(r.prefix)
            if canonical_cap is None or r.sequence > canonical_cap:
                continue  # extra, not in canonical scope
            expected = PREFIX_TO_GROUP_CODE[r.prefix]
            if r.section_code != expected:
                mismatches.append(
                    f"{r.code} on section {r.section_code!r}, expected {expected!r}"
                )
        assert mismatches == [], mismatches

    def test_no_construction_code_attached_directly_to_parent(self, db_engine):
        """Per §2.2 rule 3: Construction-prefixed codes must hang off
        a subgroup, never directly off Construction (code '4')."""
        construction_id = _section_id(db_engine, "4")
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code FROM cost_codes
                WHERE section_id = :s ORDER BY code
            """), {"s": construction_id}).fetchall()
        assert rows == [], (
            f"cost codes still attached directly to Construction: "
            f"{[r.code for r in rows]}"
        )


class TestSAL10Added:
    """SAL-10 was missing on this pod's seed (live had SAL=9; canonical
    wants SAL=10). The seed creates it with the canonical name +
    BT category — covering Build Pack §5.3 'set name = description
    from the sheet, buildertrend_category = the BT column'."""

    def test_sal_10_exists(self, db_engine):
        with db_engine.connect() as c:
            row = c.execute(text("""
                SELECT name, buildertrend_category, status
                FROM cost_codes WHERE code = 'SAL-10'
            """)).first()
        assert row is not None, "SAL-10 not seeded"
        assert row.name == "Reservation Fees", row.name
        assert row.buildertrend_category == "5 Sales & Marketing"
        assert row.status == "Active"


class TestExtras:
    """Build Pack §5.3 rule: do NOT delete live codes that aren't in
    the canonical list — report them as 'extras' and await operator
    instruction. On this pod the extras are ACC-04..08 (live had
    ACC=8; canonical wants ACC=3).
    """

    def test_extras_still_present_not_deleted(self, db_engine):
        with db_engine.connect() as c:
            rows = c.execute(text("""
                SELECT code FROM cost_codes
                WHERE prefix = 'ACC' AND sequence > 3
                ORDER BY code
            """)).fetchall()
        codes = [r.code for r in rows]
        # 5 extras present pre-seed; the seed must NOT have deleted them.
        # Operator decides their fate in a separate follow-up.
        assert codes == ["ACC-04", "ACC-05", "ACC-06", "ACC-07", "ACC-08"], (
            f"extras unexpectedly mutated: {codes}"
        )


class TestIdempotency:
    """Running the seed twice must converge — second run reports zero
    changes and the absolute row counts are identical."""

    def test_seed_is_idempotent(self, db_engine):
        from scripts.seed_cost_code_structure import run

        with db_engine.connect() as c:
            sections_before = c.execute(text(
                "SELECT COUNT(*) FROM cost_code_sections"
            )).scalar()
            codes_before = c.execute(text(
                "SELECT COUNT(*) FROM cost_codes"
            )).scalar()

        diff = run()

        with db_engine.connect() as c:
            sections_after = c.execute(text(
                "SELECT COUNT(*) FROM cost_code_sections"
            )).scalar()
            codes_after = c.execute(text(
                "SELECT COUNT(*) FROM cost_codes"
            )).scalar()

        assert sections_before == sections_after, (
            f"section count drifted: {sections_before} → {sections_after}"
        )
        assert codes_before == codes_after, (
            f"cost_code count drifted: {codes_before} → {codes_after}"
        )
        # And nothing should have been touched on the second run.
        assert diff.parents_recoded == []
        assert diff.parents_renamed == []
        assert diff.parents_repointed_allows_subgroups == []
        assert diff.subgroups_added == []
        assert diff.codes_repointed == []
        assert diff.codes_added == []

    def test_reconciliation_repoints_a_misplaced_code(self, db_engine):
        """Move a canonical Construction-prefixed code off its
        canonical subgroup onto the Construction PARENT directly; the
        next seed run must repoint it back, NOT leave it broken."""
        # Pick a stable canonical code that we know is FAC → 4.00.
        with db_engine.connect() as c:
            target_id = c.execute(text(
                "SELECT id FROM cost_codes WHERE code = 'FAC-01'"
            )).scalar()
            construction_id = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code = '4'"
            )).scalar()
            canonical_subgroup_id = c.execute(text(
                "SELECT id FROM cost_code_sections WHERE code = '4.00'"
            )).scalar()

        # Detune: point FAC-01 directly at Construction.
        with db_engine.begin() as c:
            c.execute(text(
                "UPDATE cost_codes SET section_id = :s WHERE id = :i"
            ), {"s": construction_id, "i": target_id})

        # Run seed — should reconcile back to 4.00.
        from scripts.seed_cost_code_structure import run
        diff = run()
        assert "FAC-01" in diff.codes_repointed

        with db_engine.connect() as c:
            now_section = c.execute(text(
                "SELECT section_id FROM cost_codes WHERE id = :i"
            ), {"i": target_id}).scalar()
        assert str(now_section) == str(canonical_subgroup_id)
