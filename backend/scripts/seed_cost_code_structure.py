"""B88 Pack 1 — Gate 4 canonical cost-code structure reseed (idempotent).

Build Pack §5: reconciles the live cost_code_sections / cost_codes
tables against the canonical 9-parent / 10-Construction-subgroup /
129-code structure operator-locked in Chat 49.

Run:
    python /app/backend/scripts/seed_cost_code_structure.py

Idempotent semantics:
  * Parent groups (9): looked up by `display_order` and re-coded from
    their legacy slug values ("acquisition", "planning", ...) to the
    canonical numeric values ("1", "2", ... "9"). Construction
    (display_order=4) gets `allows_subgroups=True`; all others get
    `allows_subgroups=False`. Names re-normalised to the canonical
    Build Pack §5.1 labels.
  * Construction subgroups (10): upserted by `code` (`4.00` ... `4.09`),
    `parent_section_id` pointed at the Construction parent. Build
    Pack §5.2 numbering is honoured exactly — including the operator
    resolution of the spreadsheet's duplicate-4.08 collision
    (4.06=Prefab/MMC, 4.07=Existing Buildings, 4.08=External Works).
  * Cost codes (129 canonical): every Construction-prefixed code is
    re-pointed at its canonical subgroup. SAL-10 is created if absent
    (canonical name "Reservation Fees", buildertrend_category
    "5 Sales & Marketing"). Existing code rows are NOT renamed —
    `name`, `buildertrend_category`, `vat_treatment`, etc. are kept
    so transient probe data and historical naming variants survive.
  * Extras: live codes whose (prefix, sequence) is NOT in the canonical
    list (today: ACC-04..08, 5 rows) are NOT deleted — the script
    reports them as `extras` per Build Pack §5.3 and awaits operator
    instruction.

Run-twice proof: re-running the script after a successful first run
must produce identical row counts for `cost_code_sections` and
`cost_codes` (the test in `test_cost_code_seed_structure.py`
asserts this).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy import text  # noqa: E402

from app.db import SessionLocal  # noqa: E402


# --------------------------------------------------------------------------
# Canonical structure — Build Pack §5.1, §5.2, §5.3
# --------------------------------------------------------------------------

# Parent groups: (canonical_code, name, display_order, allows_subgroups,
#                 is_direct_cost, default_p_and_l_category)
PARENT_GROUPS = [
    ("1", "Acquisition",                       1, False, True,  "COS"),
    ("2", "Planning & Statutory",              2, False, True,  "COS"),
    ("3", "Design & Professional Fees",        3, False, True,  "COS"),
    ("4", "Construction",                      4, True,  True,  "COS"),
    ("5", "Sales, Marketing & Disposal",       5, False, True,  "COS"),
    ("6", "Finance Costs",                     6, False, False, "Finance"),
    ("7", "Company Overheads",                 7, False, False, "Overhead"),
    ("8", "Accounting & Financial Services",   8, False, False, "Tax"),
    ("9", "Contingency, Risk & Miscellaneous", 9, False, True,  "COS"),
]

# Construction subgroups (Build Pack §5.2). Parent code = "4".
# (code, name, display_order)
CONSTRUCTION_SUBGROUPS = [
    ("4.00", "Facilitating Works",  1),
    ("4.01", "Substructure",        2),
    ("4.02", "Superstructure",      3),
    ("4.03", "Internal Finishes",   4),
    ("4.04", "Fittings & Equipment", 5),
    ("4.05", "Services",            6),
    ("4.06", "Prefab / MMC",        7),
    ("4.07", "Existing Buildings",  8),
    ("4.08", "External Works",      9),
    ("4.09", "Preliminaries",      10),
]

# Prefix → canonical (sub)group code (Build Pack §5.3).
PREFIX_TO_GROUP_CODE: dict[str, str] = {
    "ACQ": "1", "PLN": "2", "DES": "3",
    "FAC": "4.00", "SUB": "4.01", "SUP": "4.02", "INT": "4.03",
    "FIT": "4.04", "SER": "4.05", "PRE": "4.06", "EXB": "4.07",
    "EXT": "4.08", "PRL": "4.09",
    "SAL": "5", "FIN": "6", "OHD": "7", "ACC": "8", "CTG": "9",
}

# Canonical sequence per prefix (Build Pack §5.3, total = 129).
CANONICAL_SEQUENCES: dict[str, list[int]] = {
    "ACQ": list(range(1, 11)),  # 10
    "PLN": list(range(1, 10)),  # 9
    "DES": list(range(1, 10)),  # 9
    "FAC": list(range(1,  6)),  # 5
    "SUB": list(range(1,  6)),  # 5
    "SUP": list(range(1, 11)),  # 10
    "INT": list(range(1,  7)),  # 6
    "FIT": list(range(1,  6)),  # 5
    "SER": list(range(1, 11)),  # 10
    "PRE": list(range(1,  2)),  # 1
    "EXB": list(range(1,  4)),  # 3
    "EXT": list(range(1, 10)),  # 9
    "PRL": list(range(1, 17)),  # 16
    "SAL": list(range(1, 11)),  # 10
    "FIN": list(range(1,  6)),  # 5
    "OHD": list(range(1,  9)),  # 8
    "ACC": list(range(1,  4)),  # 3
    "CTG": list(range(1,  6)),  # 5
}
# 10+9+9+5+5+10+6+5+10+1+3+9+16+10+5+8+3+5 = 129  ✓
CANONICAL_TOTAL = sum(len(v) for v in CANONICAL_SEQUENCES.values())
assert CANONICAL_TOTAL == 129, f"canonical math broken: {CANONICAL_TOTAL}"

# Codes that are not yet on the pod but the canonical list requires.
# Today the only one is SAL-10 (Build Pack §5.3 mandates SAL=10
# canonical; live seed migration 0013 had SAL=9). Name + BT category
# pulled from /app/SY_Homes_Data_Model.xlsx (Sales & Marketing tab).
NEW_CANONICAL_CODES: list[dict] = [
    {
        "code": "SAL-10",
        "prefix": "SAL",
        "sequence": 10,
        "name": "Reservation Fees",
        "buildertrend_category": "5 Sales & Marketing",
        # SAL profile mirrors the rest of the SAL row in seed 0013.
        "default_entity": "SPV",
        "is_vattable": True,
        "vat_treatment": "Standard",
        "status": "Active",
        "display_order": 10,
    },
]


# --------------------------------------------------------------------------
# Diff summary
# --------------------------------------------------------------------------

class Diff:
    def __init__(self) -> None:
        self.parents_recoded: list[str] = []
        self.parents_renamed: list[str] = []
        self.parents_repointed_allows_subgroups: list[str] = []
        self.subgroups_added: list[str] = []
        self.subgroups_unchanged: list[str] = []
        self.codes_repointed: list[str] = []
        self.codes_unchanged: int = 0
        self.codes_added: list[str] = []
        self.extras: list[str] = []
        self.orphans_under_construction: list[str] = []

    def print_report(self) -> None:
        line = "─" * 70
        print(line)
        print("B88 Pack 1 — Gate 4 reseed · diff summary")
        print(line)
        print(f"Parents recoded (slug → numeric)        : {len(self.parents_recoded):>4}  "
              f"{self.parents_recoded}")
        print(f"Parents renamed (name canonicalised)    : {len(self.parents_renamed):>4}  "
              f"{self.parents_renamed}")
        print(f"Parents w/ allows_subgroups flipped     : {len(self.parents_repointed_allows_subgroups):>4}  "
              f"{self.parents_repointed_allows_subgroups}")
        print(f"Construction subgroups added            : {len(self.subgroups_added):>4}  "
              f"{self.subgroups_added}")
        print(f"Construction subgroups unchanged        : {len(self.subgroups_unchanged):>4}  "
              f"{self.subgroups_unchanged}")
        print(f"Cost codes re-pointed to new section_id : {len(self.codes_repointed):>4}")
        print(f"Cost codes already on correct section   : {self.codes_unchanged:>4}")
        print(f"Cost codes added (new canonical rows)   : {len(self.codes_added):>4}  "
              f"{self.codes_added}")
        print(f"EXTRA live codes (NOT deleted)          : {len(self.extras):>4}  "
              f"{self.extras}")
        print(f"Orphans still attached to '4' directly  : {len(self.orphans_under_construction):>4}  "
              f"{self.orphans_under_construction}")
        print(line)


# --------------------------------------------------------------------------
# Steps
# --------------------------------------------------------------------------

def _reconcile_parent_groups(db, diff: Diff) -> dict[str, str]:
    """Step 1 — recode/rename the 9 parent groups.

    Matching strategy is order-of-preference:
      1. Match by canonical code ("1".."9") if the section already
         has it (post-Gate-4 runs hit this path).
      2. Else match by legacy slug ("acquisition", "planning", ...).
         The slug map is the data from migration 0012.
      3. Else match by display_order on rows whose code is NOT one
         of the subgroup codes ("4.00".."4.09" — they share the
         display_order space).

    Returns a map {canonical_code: section_id}.
    """
    SLUG_BY_CANONICAL: dict[str, str] = {
        "1": "acquisition",
        "2": "planning",
        "3": "design",
        "4": "construction",
        "5": "sales_marketing",
        "6": "finance",
        "7": "company_overheads",
        "8": "accounting",
        "9": "contingency",
    }

    all_rows = db.execute(text("""
        SELECT id, code, name, display_order, allows_subgroups,
               is_direct_cost, default_p_and_l_category,
               parent_section_id
        FROM cost_code_sections
    """)).fetchall()
    by_code = {r.code: r for r in all_rows}

    parent_ids: dict[str, str] = {}
    for canon_code, name, order, allows_sub, is_direct, pl_cat in PARENT_GROUPS:
        existing = (
            by_code.get(canon_code)
            or by_code.get(SLUG_BY_CANONICAL[canon_code])
        )
        if existing is None:
            # Last resort — match by display_order on a non-subgroup row.
            for r in all_rows:
                if r.code in SUBGROUP_CODES_LITERAL:
                    continue
                if r.display_order == order and r.code not in by_code:
                    existing = r
                    break
        if existing is None:
            new_id = db.execute(text("""
                INSERT INTO cost_code_sections
                  (code, name, display_order, allows_subgroups,
                   is_direct_cost, default_p_and_l_category)
                VALUES (:c, :n, :o, :as_, :id_, :pl)
                RETURNING id
            """), {"c": canon_code, "n": name, "o": order,
                    "as_": allows_sub, "id_": is_direct, "pl": pl_cat}
            ).scalar()
            parent_ids[canon_code] = str(new_id)
            diff.subgroups_added.append(canon_code)
            continue

        changes = {}
        if existing.code != canon_code:
            changes["code"] = canon_code
            diff.parents_recoded.append(f"{existing.code}→{canon_code}")
        if existing.name != name:
            changes["name"] = name
            diff.parents_renamed.append(
                f"{existing.code}: {existing.name!r}→{name!r}"
            )
        if bool(existing.allows_subgroups) != allows_sub:
            changes["allows_subgroups"] = allows_sub
            diff.parents_repointed_allows_subgroups.append(
                f"{canon_code}={allows_sub}"
            )

        if changes:
            set_clauses = ", ".join(f"{k} = :{k}" for k in changes)
            changes["id"] = existing.id
            db.execute(
                text(f"UPDATE cost_code_sections SET {set_clauses} WHERE id = :id"),
                changes,
            )
        parent_ids[canon_code] = str(existing.id)

    return parent_ids


# Construction subgroup codes — used to filter them out of the parent
# matcher's display-order fallback.
SUBGROUP_CODES_LITERAL: set[str] = {c for c, _n, _o in CONSTRUCTION_SUBGROUPS}


def _reconcile_construction_subgroups(
    db, construction_id: str, diff: Diff
) -> dict[str, str]:
    """Step 2 — upsert the 10 Construction subgroups (4.00 – 4.09).

    Matching strategy:
      1. Match by `code` ("4.00".."4.09") — the canonical identifier.
         If the row exists but its `parent_section_id` doesn't point
         at Construction (e.g. it became NULL via a migration round-
         trip downgrade-upgrade), re-parent it.
      2. Else INSERT a fresh row.

    Returns a map {sub_code: section_id}.
    """
    canonical_codes = [c for c, _n, _o in CONSTRUCTION_SUBGROUPS]
    existing = {
        r.code: r for r in db.execute(text("""
            SELECT id, code, name, display_order, parent_section_id,
                   allows_subgroups
            FROM cost_code_sections
            WHERE code = ANY(:codes)
        """), {"codes": canonical_codes}).fetchall()
    }

    sub_ids: dict[str, str] = {}
    for code, name, order in CONSTRUCTION_SUBGROUPS:
        row = existing.get(code)
        if row is None:
            new_id = db.execute(text("""
                INSERT INTO cost_code_sections
                  (code, name, display_order, parent_section_id,
                   allows_subgroups, is_direct_cost,
                   default_p_and_l_category)
                VALUES (:c, :n, :o, :p, false, true, 'COS')
                RETURNING id
            """), {"c": code, "n": name, "o": order, "p": construction_id}
            ).scalar()
            sub_ids[code] = str(new_id)
            diff.subgroups_added.append(code)
        else:
            updates = {}
            if row.name != name:
                updates["name"] = name
            if row.display_order != order:
                updates["display_order"] = order
            if str(row.parent_section_id or "") != construction_id:
                updates["parent_section_id"] = construction_id
            if bool(row.allows_subgroups):
                # Subgroups must NOT themselves allow subgroups
                # (no three-tier nesting). Build Pack §2.2 rule.
                updates["allows_subgroups"] = False
            if updates:
                set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
                updates["id"] = row.id
                db.execute(
                    text(f"UPDATE cost_code_sections SET {set_clauses} WHERE id = :id"),
                    updates,
                )
            sub_ids[code] = str(row.id)
            diff.subgroups_unchanged.append(code)
    return sub_ids


def _reconcile_cost_codes(
    db, parent_ids: dict[str, str], sub_ids: dict[str, str], diff: Diff
) -> None:
    """Step 3 — re-point every canonical code at its (sub)group;
    create any missing canonical code; report extras."""
    section_by_group_code: dict[str, str] = {**parent_ids, **sub_ids}

    # Bulk-load every live cost code so we can do everything in one pass.
    live_by_code = {
        r.code: r for r in db.execute(text("""
            SELECT id, code, prefix, sequence, section_id, status
            FROM cost_codes
        """)).fetchall()
    }

    canonical_codes: set[str] = set()
    for prefix, seqs in CANONICAL_SEQUENCES.items():
        target_group_code = PREFIX_TO_GROUP_CODE[prefix]
        target_section_id = section_by_group_code[target_group_code]
        for seq in seqs:
            full_code = f"{prefix}-{seq:02d}"
            canonical_codes.add(full_code)
            row = live_by_code.get(full_code)
            if row is None:
                continue  # handled in NEW_CANONICAL_CODES pass below
            if str(row.section_id) != target_section_id:
                db.execute(text("""
                    UPDATE cost_codes
                    SET section_id = :s
                    WHERE id = :i
                """), {"s": target_section_id, "i": row.id})
                diff.codes_repointed.append(full_code)
            else:
                diff.codes_unchanged += 1

    # Add new canonical rows that are missing on the pod (SAL-10 today).
    for spec in NEW_CANONICAL_CODES:
        if spec["code"] in live_by_code:
            continue
        target_section_id = section_by_group_code[
            PREFIX_TO_GROUP_CODE[spec["prefix"]]
        ]
        db.execute(text("""
            INSERT INTO cost_codes (
              code, prefix, sequence, name, section_id,
              buildertrend_category, default_entity, is_vattable,
              vat_treatment, status, display_order
            ) VALUES (
              :code, :prefix, :sequence, :name, :section_id,
              :buildertrend_category, :default_entity,
              :is_vattable, :vat_treatment, :status, :display_order
            )
        """), {**spec, "section_id": target_section_id})
        diff.codes_added.append(spec["code"])

    # Identify extras — live rows whose code is NOT canonical and whose
    # prefix is one of the canonical prefixes. We do NOT delete them —
    # Build Pack §5.3 says report only, await instruction.
    for code, row in live_by_code.items():
        if code in canonical_codes:
            continue
        if row.prefix in CANONICAL_SEQUENCES:
            diff.extras.append(code)

    # Sanity: nothing should remain attached directly to Construction
    # (parent code "4") — every Construction-prefixed code must hang off
    # one of the subgroups.
    construction_id = parent_ids["4"]
    rows = db.execute(text("""
        SELECT code FROM cost_codes
        WHERE section_id = :s
        ORDER BY code
    """), {"s": construction_id}).fetchall()
    diff.orphans_under_construction = [r.code for r in rows]


# --------------------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------------------

def run() -> Diff:
    db = SessionLocal()
    diff = Diff()
    try:
        with db.begin():
            parent_ids = _reconcile_parent_groups(db, diff)
            construction_id = parent_ids["4"]
            sub_ids = _reconcile_construction_subgroups(
                db, construction_id, diff,
            )
            _reconcile_cost_codes(db, parent_ids, sub_ids, diff)
    finally:
        db.close()
    diff.print_report()
    return diff


if __name__ == "__main__":
    run()
