"""B88 Pack 1 — Gate 4 canonical cost-code structure reseed (idempotent).

Source of truth: the operator-corrected canonical master file
`BTCostCodes_20260609 (1) (3).xlsx` (uploaded mid-Gate-4). The
previous Gate 4 submission was REJECTED because it was built against
a stale code list (assumed 129 + 5 ACC extras + an invented SAL-10
"Reservation Fees"). The corrected master locks in:

    130 codes, 9 parent groups, 10 Construction subgroups.

Per-prefix authoritative counts (sum = 130):
    ACQ 10 · PLN 9 · DES 9
    FAC 5 · SUB 5 · SUP 10 · INT 6 · FIT 5 · SER 10 ·
        PRE 1 · EXB 3 · EXT 9 · PRL 16
    SAL 10 · FIN 5 · OHD 9 · ACC 3 · CTG 5

Reconciliation semantics (Build Pack §5.3 + Gate-4 operator
direction):
  * Hard-delete any non-canonical row (e.g. ACC-04..08, CTG-06 if
    present) whose code is NOT in the canonical list **when it has
    no FK references**.
  * If a non-canonical row HAS FK references (budget_line, PO line,
    appraisal_cost_line, project_cost_code, etc.), it cannot be
    safely deleted — instead set its `status` to `'Retired'` and
    record it in the diff as "retired (FK-referenced)".
  * Names are always overridden with the canonical master string —
    no preservation of historical names. The canonical file is now
    the source of truth.
  * SAL-10 is reseeded with the canonical name "Other sales &
    disposal costs" (NOT "Reservation Fees" — that was the rejected
    invention).
  * SAL-09 is renamed in-place to "Post-completion holding &
    maintenance" (it currently holds the SAL-10-canonical name and
    must shift up one slot).
  * OHD-09 is newly seeded ("HR, recruitment & employee welfare").

Run:
    python /app/backend/scripts/seed_cost_code_structure.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))
load_dotenv(BACKEND_DIR / ".env")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402

from app.db import SessionLocal  # noqa: E402


# --------------------------------------------------------------------------
# Canonical structure (operator master 2026-06-09)
# --------------------------------------------------------------------------

# Parent groups: (canonical_code, name, display_order, allows_subgroups,
#                 is_direct_cost, default_p_and_l_category)
PARENT_GROUPS = [
    ("1", "Land & Acquisition",                1, False, True,  "COS"),
    ("2", "Planning & Statutory",              2, False, True,  "COS"),
    ("3", "Professional Fees",                 3, False, True,  "COS"),
    ("4", "Construction",                      4, True,  True,  "COS"),
    ("5", "Sales & Marketing",                 5, False, True,  "COS"),
    ("6", "Finance Costs",                     6, False, False, "Finance"),
    ("7", "Company Overheads",                 7, False, False, "Overhead"),
    ("8", "Accounting",                        8, False, False, "Tax"),
    ("9", "Contingency, Risk & Miscellaneous", 9, False, True,  "COS"),
]

# Construction subgroups (parent_section_id → "4"): (code, name, order)
CONSTRUCTION_SUBGROUPS = [
    ("4.00", "Facilitating Works",   1),
    ("4.01", "Substructure",         2),
    ("4.02", "Superstructure",       3),
    ("4.03", "Internal Finishes",    4),
    ("4.04", "Fittings & Equipment", 5),
    ("4.05", "Services",             6),
    ("4.06", "Prefab / MMC",         7),
    ("4.07", "Existing Buildings",   8),
    ("4.08", "External Works",       9),
    ("4.09", "Preliminaries",       10),
]
SUBGROUP_CODES_LITERAL: set[str] = {c for c, _n, _o in CONSTRUCTION_SUBGROUPS}

# Prefix → canonical (sub)group code.
PREFIX_TO_GROUP_CODE: dict[str, str] = {
    "ACQ": "1", "PLN": "2", "DES": "3",
    "FAC": "4.00", "SUB": "4.01", "SUP": "4.02", "INT": "4.03",
    "FIT": "4.04", "SER": "4.05", "PRE": "4.06", "EXB": "4.07",
    "EXT": "4.08", "PRL": "4.09",
    "SAL": "5", "FIN": "6", "OHD": "7", "ACC": "8", "CTG": "9",
}

# Canonical (code → name). Source: operator master file 2026-06-09.
# Sum = 130 rows.  Per-prefix counts asserted at bottom of this dict.
CANONICAL_CODES: dict[str, str] = {
    # ACQ — 10
    "ACQ-01": "Land / site purchase price",
    "ACQ-02": "Stamp Duty Land Tax (SDLT)",
    "ACQ-03": "Acquisition legal & conveyancing fees",
    "ACQ-04": "Estate agent / land finder fees",
    "ACQ-05": "Topographical & measured surveys",
    "ACQ-06": "Environmental, ecological & contamination surveys",
    "ACQ-07": "Geotechnical & soil investigation",
    "ACQ-08": "Utility searches & enquiries",
    "ACQ-09": "Option agreements & conditional contract costs",
    "ACQ-10": "Site holding / carry costs (council tax, security, maintenance)",
    # PLN — 9
    "PLN-01": "Planning application & pre-application fees",
    "PLN-02": "Community Infrastructure Levy (CIL)",
    "PLN-03": "Section 106 contributions",
    "PLN-04": "Building Regulations application & inspection fees",
    "PLN-05": "Planning consultant / advisor fees",
    "PLN-06": "Legal fees – planning agreements & appeals",
    "PLN-07": "Highway authority fees, S278 & S38 agreements",
    "PLN-08": "Ecology / arboriculture mitigation (condition discharge)",
    "PLN-09": "Other statutory approvals & condition discharge costs",
    # DES — 9
    "DES-01": "Architect / design team fees",
    "DES-02": "Structural & civil engineer fees",
    "DES-03": "Mechanical & electrical (M&E) consultant fees",
    "DES-04": "Other specialist consultants (acoustic, fire, SAP/EPC)",
    "DES-05": "Quantity surveyor / cost consultant fees",
    "DES-06": "Project management / employer's agent fees",
    "DES-07": "NHBC / warranty provider registration & pre-build audit",
    "DES-08": "CDM principal designer fees",
    "DES-09": "Other professional fees",
    # FAC — 5
    "FAC-01": "Hazardous material removal (asbestos, contamination)",
    "FAC-02": "Demolition works",
    "FAC-03": "Site clearance & enabling works",
    "FAC-04": "Specialist ground works (piling mats, ground improvement)",
    "FAC-05": "Temporary diversion of services / watercourses",
    # SUB — 5
    "SUB-01": "Foundations (strip, trench fill, pad, raft, piled)",
    "SUB-02": "Masonry below DPC (blockwork, brickwork)",
    "SUB-03": "Damp proof course, membranes & tanking",
    "SUB-04": "Ground floor slab & structure",
    "SUB-05": "Substructure drainage (land drains, sub-floor)",
    # SUP — 10
    "SUP-01": "Structural frame (steel, timber frame, glulam)",
    "SUP-02": "External walls (masonry, blockwork, insulation, render, cladding)",
    "SUP-03": "Upper floor structures (joists, beams, decking)",
    "SUP-04": "Roof structure, trusses & coverings (tiles, slate, felt, lead)",
    "SUP-05": "Fascias, soffits, bargeboards & rainwater goods",
    "SUP-06": "Stairs & balustrades",
    "SUP-07": "Windows & external doors (supply & install)",
    "SUP-08": "Carpentry 1st fix (studwork, partitions, noggins, linings)",
    "SUP-09": "Carpentry second fix (skirting, architrave, shelving, hanging doors)",
    "SUP-10": "Internal doors, frames & ironmongery (supply)",
    # INT — 6
    "INT-01": "Plastering & dry lining",
    "INT-02": "Painting & decorating (internal)",
    "INT-03": "Wall & floor tiling",
    "INT-04": "Floor screeds & levelling",
    "INT-05": "Flooring (carpet, laminate, vinyl, LVT)",
    "INT-06": "Ceiling finishes (boarding, coving, features)",
    # FIT — 5
    "FIT-01": "Kitchen units, worktops & appliances",
    "FIT-02": "Bathroom sanitaryware, brassware & accessories",
    "FIT-03": "Built-in joinery (wardrobes, shelving, utility units)",
    "FIT-04": "Mirrors, shower screens & bathroom furniture",
    "FIT-05": "Other fittings & furnishings",
    # SER — 10
    "SER-01": "Electrical 1st fix (cabling, back boxes, CU, earth bonding)",
    "SER-02": "Electrical 2nd fix (sockets, switches, lights, detectors, test)",
    "SER-03": "Plumbing & heating 1st fix (soil/waste, pipework, UFH, flue)",
    "SER-04": "Plumbing & heating 2nd fix (sanitaryware, rads, taps, boiler)",
    "SER-05": "Ventilation (extract fans, MVHR, ductwork)",
    "SER-06": "Renewables & EV (solar PV, battery, ASHP, EV charger)",
    "SER-07": "Data, TV, security & smart home systems",
    "SER-08": "BWIC services (chasing, boxing, making good)",
    "SER-09": "Fire stopping (penetration seals, cavity barriers, intumescent strips)",
    "SER-10": "Lift installation (passenger, platform, stairlift)",
    # PRE — 1
    "PRE-01": "Prefabricated building units (timber frame kit, SIPs, modular, MMC)",
    # EXB — 3
    "EXB-01": "Minor demolition & internal strip-out",
    "EXB-02": "Structural alterations & repairs to existing",
    "EXB-03": "Damp proofing & timber treatment to existing",
    # EXT — 9
    "EXT-01": "External drainage – private (plot drainage, manholes, soakaways)",
    "EXT-02": "External drainage – adoptable (S104, pumping, attenuation)",
    "EXT-03": "Utility service connections & metering",
    "EXT-04": "Driveways, paths & private hard landscaping",
    "EXT-05": "Estate roads & adoptable infra (S38, kerbing, lighting)",
    "EXT-06": "Soft landscaping, planting, turfing & topsoil",
    "EXT-07": "Boundary fencing, walls & gates",
    "EXT-08": "External lighting & fixtures (private)",
    "EXT-09": "Minor building works (garages, car ports, bin/cycle stores)",
    # PRL — 16
    "PRL-01": "Site mobilisation & demobilisation",
    "PRL-02": "Temporary welfare facilities (toilets, mess room)",
    "PRL-03": "Temporary fencing, hoarding & site security",
    "PRL-04": "Scaffolding, access towers & working platforms",
    "PRL-05": "Site management & supervision (site manager, foreman)",
    "PRL-06": "General site labour (labourers, banksmen, material handling)",
    "PRL-07": "Hired plant & equipment (telehandler, excavator, dumper, crane)",
    "PRL-08": "Temporary services (power, water, drainage, lighting)",
    "PRL-09": "Health & safety, CDM compliance & training",
    "PRL-10": "Waste management, skip hire & site tidying",
    "PRL-11": "Contractors all-risks & site-specific insurance",
    "PRL-12": "Setting out, surveys & quality control",
    "PRL-13": "Warranty / NHBC inspections during build",
    "PRL-14": "Final clean & handover (builders clean, sparkle clean)",
    "PRL-15": "Snagging & remedial works (pre-handover)",
    "PRL-16": "Other preliminaries",
    # SAL — 10
    "SAL-01": "Marketing, brochures, website & digital advertising",
    "SAL-02": "Show home setup, furnishing & staging",
    "SAL-03": "Sales agent commissions",
    "SAL-04": "Legal fees – sales conveyancing",
    "SAL-05": "Stamp duty reimbursement (buyer incentive)",
    "SAL-06": "Sales incentives / part-exchange costs",
    "SAL-07": "Photography, CGIs, virtual tours & signage",
    "SAL-08": "EPC, warranty handover packs & homeowner manual",
    "SAL-09": "Post-completion holding & maintenance",
    "SAL-10": "Other sales & disposal costs",
    # FIN — 5
    "FIN-01": "Development finance interest & arrangement fees",
    "FIN-02": "Bank / lender monitoring surveyor & valuation fees",
    "FIN-03": "Legal fees – finance agreements",
    "FIN-04": "Broker fees",
    "FIN-05": "Other finance costs",
    # OHD — 9
    "OHD-01": "Head office salaries & admin",
    "OHD-02": "Office rent, utilities & equipment",
    "OHD-03": "Insurance (company-wide PI, D&O, EL)",
    "OHD-04": "General corporate legal fees",
    "OHD-05": "Software, subscriptions & IT",
    "OHD-06": "Training & professional development (CPD)",
    "OHD-07": "Marketing (company level / brand)",
    "OHD-08": "Travel & vehicle costs",
    "OHD-09": "HR, recruitment & employee welfare",
    # ACC — 3
    "ACC-01": "Accountancy fees (bookkeeping, tax, payroll, CIS, audit)",
    "ACC-02": "Bank charges & transaction fees",
    "ACC-03": "Other accounting & financial services",
    # CTG — 5
    "CTG-01": "Contingency allowance (design, construction, employer, inflation)",
    "CTG-02": "VAT (irrecoverable or partial exemption)",
    "CTG-03": "Post-completion defects & remedial works (DLP period)",
    "CTG-04": "Post-completion maintenance (service charges, inspections)",
    "CTG-05": "Other miscellaneous / unforeseen costs",
}
assert len(CANONICAL_CODES) == 130, f"canonical math broken: {len(CANONICAL_CODES)}"

# Default profile per prefix (used only when a code is being INSERTED
# fresh — existing rows keep their is_vattable / vat_treatment etc.).
DEFAULT_PROFILE_BY_PREFIX: dict[str, dict] = {
    "ACQ": {"buildertrend_category": "1 Acquisition",
            "default_entity": "SPV", "is_vattable": False,
            "vat_treatment": "Exempt"},
    "PLN": {"buildertrend_category": "2 Planning & Statutory",
            "default_entity": "SPV", "is_vattable": False,
            "vat_treatment": "Exempt"},
    "DES": {"buildertrend_category": "3 Professional Fees",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "FAC": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "SUB": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "SUP": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "INT": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "FIT": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "SER": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "PRE": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "EXB": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "EXT": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "PRL": {"buildertrend_category": "4 Construction",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "SAL": {"buildertrend_category": "5 Sales & Marketing",
            "default_entity": "SPV", "is_vattable": True,
            "vat_treatment": "Standard"},
    "FIN": {"buildertrend_category": "6 Finance Costs",
            "default_entity": "SPV", "is_vattable": False,
            "vat_treatment": "Exempt"},
    "OHD": {"buildertrend_category": "7 Company Overheads",
            "default_entity": "Parent", "is_vattable": True,
            "vat_treatment": "Standard"},
    "ACC": {"buildertrend_category": "8 Accounting",
            "default_entity": "Parent", "is_vattable": True,
            "vat_treatment": "Standard"},
    "CTG": {"buildertrend_category": "9 Contingency, Risk & Misc",
            "default_entity": "SPV", "is_vattable": False,
            "vat_treatment": "Mixed"},
}

LEGACY_SLUG_BY_CANONICAL = {
    "1": "acquisition", "2": "planning", "3": "design", "4": "construction",
    "5": "sales_marketing", "6": "finance", "7": "company_overheads",
    "8": "accounting", "9": "contingency",
}


# --------------------------------------------------------------------------
# Diff report
# --------------------------------------------------------------------------

class Diff:
    def __init__(self) -> None:
        self.parents_recoded: list[str] = []
        self.parents_renamed: list[str] = []
        self.parents_repointed_allows_subgroups: list[str] = []
        self.parents_pl_category_set: list[str] = []
        self.subgroups_added: list[str] = []
        self.subgroups_unchanged: list[str] = []
        self.codes_added: list[str] = []
        self.codes_renamed: list[str] = []
        self.codes_repointed: list[str] = []
        self.codes_deleted: list[str] = []
        self.codes_retired: list[str] = []
        self.codes_unchanged: int = 0
        self.orphans_under_construction: list[str] = []

    def print_report(self) -> None:
        line = "─" * 72
        print(line)
        print("B88 Pack 1 — Gate 4 (corrected canonical 130) · diff summary")
        print(line)
        print(f"Parents recoded (slug → numeric)         : {len(self.parents_recoded):>4}  "
              f"{self.parents_recoded}")
        print(f"Parents renamed (master file)            : {len(self.parents_renamed):>4}  "
              f"{self.parents_renamed}")
        print(f"Parents allows_subgroups flipped         : {len(self.parents_repointed_allows_subgroups):>4}  "
              f"{self.parents_repointed_allows_subgroups}")
        print(f"Parents p&l category set                 : {len(self.parents_pl_category_set):>4}  "
              f"{self.parents_pl_category_set}")
        print(f"Construction subgroups added             : {len(self.subgroups_added):>4}  "
              f"{self.subgroups_added}")
        print(f"Construction subgroups unchanged         : {len(self.subgroups_unchanged):>4}  "
              f"{self.subgroups_unchanged}")
        print(f"Cost codes ADDED (new canonical rows)    : {len(self.codes_added):>4}  "
              f"{self.codes_added}")
        print(f"Cost codes RENAMED (to canonical name)   : {len(self.codes_renamed):>4}  "
              f"{self.codes_renamed}")
        print(f"Cost codes RE-POINTED to new section     : {len(self.codes_repointed):>4}  "
              f"{self.codes_repointed}")
        print(f"Cost codes DELETED (non-canonical, safe) : {len(self.codes_deleted):>4}  "
              f"{self.codes_deleted}")
        print(f"Cost codes RETIRED (non-canonical, FK-ref): {len(self.codes_retired):>4}  "
              f"{self.codes_retired}")
        print(f"Cost codes unchanged                     : {self.codes_unchanged:>4}")
        print(f"Orphans still attached directly to '4'   : {len(self.orphans_under_construction):>4}  "
              f"{self.orphans_under_construction}")
        print(line)


# --------------------------------------------------------------------------
# Reconciliation steps
# --------------------------------------------------------------------------

def _reconcile_parent_groups(db, diff: Diff) -> dict[str, str]:
    """Upsert the 9 parent groups against the canonical master.

    Returns {canonical_code: section_id}. Matching order:
      1. code == canonical numeric ("1".."9")
      2. code == legacy slug ("acquisition"...)
      3. display_order match, excluding subgroup codes
    """
    all_rows = db.execute(text("""
        SELECT id, code, name, display_order, allows_subgroups,
               is_direct_cost, default_p_and_l_category, parent_section_id,
               included_in_construction_scope
        FROM cost_code_sections
    """)).fetchall()
    by_code = {r.code: r for r in all_rows}

    parent_ids: dict[str, str] = {}
    for canon_code, name, order, allows_sub, is_direct, pl_cat in PARENT_GROUPS:
        existing = (
            by_code.get(canon_code)
            or by_code.get(LEGACY_SLUG_BY_CANONICAL[canon_code])
        )
        if existing is None:
            for r in all_rows:
                if r.code in SUBGROUP_CODES_LITERAL:
                    continue
                if r.display_order == order and r.code not in by_code:
                    existing = r
                    break
        if existing is None:
            # B88 Pack 2 — set construction-scope flag only on insert.
            # Operator can retoggle via PATCH /cost-code-sections/{id};
            # the seed re-runs must never revert that edit (§2).
            new_id = db.execute(text("""
                INSERT INTO cost_code_sections
                  (code, name, display_order, allows_subgroups,
                   is_direct_cost, default_p_and_l_category,
                   included_in_construction_scope)
                VALUES (:c, :n, :o, :as_, :id_, :pl, :scope)
                RETURNING id
            """), {"c": canon_code, "n": name, "o": order,
                    "as_": allows_sub, "id_": is_direct, "pl": pl_cat,
                    "scope": canon_code == "4"}
            ).scalar()
            parent_ids[canon_code] = str(new_id)
            continue

        changes = {}
        if existing.code != canon_code:
            changes["code"] = canon_code
            diff.parents_recoded.append(f"{existing.code}→{canon_code}")
        if existing.name != name:
            changes["name"] = name
            diff.parents_renamed.append(
                f"{canon_code}: {existing.name!r}→{name!r}"
            )
        if bool(existing.allows_subgroups) != allows_sub:
            changes["allows_subgroups"] = allows_sub
            diff.parents_repointed_allows_subgroups.append(
                f"{canon_code}={allows_sub}"
            )
        if existing.default_p_and_l_category != pl_cat:
            changes["default_p_and_l_category"] = pl_cat
            diff.parents_pl_category_set.append(
                f"{canon_code}: {existing.default_p_and_l_category}→{pl_cat}"
            )
        # B88 Pack 2 — restore the construction-scope flag on section "4"
        # if an alembic round-trip dropped it back to the default false.
        # OTHER parents are operator-owned — never touched on re-runs.
        if canon_code == "4":
            try:
                if existing.included_in_construction_scope is False:
                    changes["included_in_construction_scope"] = True
            except AttributeError:
                pass

        if changes:
            set_clauses = ", ".join(f"{k} = :{k}" for k in changes)
            changes["id"] = existing.id
            db.execute(
                text(f"UPDATE cost_code_sections SET {set_clauses} WHERE id = :id"),
                changes,
            )
        parent_ids[canon_code] = str(existing.id)

    return parent_ids


def _reconcile_construction_subgroups(
    db, construction_id: str, diff: Diff
) -> dict[str, str]:
    """Upsert the 10 Construction subgroups. Re-parents any orphaned
    rows (e.g. parent_section_id reset by alembic round-trip)."""
    canonical_codes = [c for c, _n, _o in CONSTRUCTION_SUBGROUPS]
    existing = {
        r.code: r for r in db.execute(text("""
            SELECT id, code, name, display_order, parent_section_id,
                   allows_subgroups, included_in_construction_scope
            FROM cost_code_sections
            WHERE code = ANY(:codes)
        """), {"codes": canonical_codes}).fetchall()
    }

    sub_ids: dict[str, str] = {}
    for code, name, order in CONSTRUCTION_SUBGROUPS:
        row = existing.get(code)
        if row is None:
            # B88 Pack 2 — Construction subgroups (parent = '4') default
            # to construction-scope=true on insert. Never updated on
            # subsequent re-runs (§2 — operator owns this flag).
            new_id = db.execute(text("""
                INSERT INTO cost_code_sections
                  (code, name, display_order, parent_section_id,
                   allows_subgroups, is_direct_cost,
                   default_p_and_l_category,
                   included_in_construction_scope)
                VALUES (:c, :n, :o, :p, false, true, 'COS', true)
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
                updates["allows_subgroups"] = False
            # B88 Pack 2 — Construction subgroups are canonical construction
            # by definition. The §2 rule "seed must not touch scope flag
            # on re-runs" applies to OTHER sections (operator-owned). For
            # the construction subgroup set itself we restore the flag if
            # an alembic round-trip stripped it (column default = false).
            try:
                if row.included_in_construction_scope is False:
                    updates["included_in_construction_scope"] = True
            except AttributeError:
                pass
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


def _try_hard_delete_code(db, code_id: str) -> bool:
    """Attempt a hard delete of a cost code. Pre-cleans the soft-link
    tables (cost_code_subcategories, project_cost_codes,
    cost_code_entity_mapping, cost_code_buildertrend_overrides) and
    nulls self-referential replaced_by_code_id. Returns True on
    success, False if a RESTRICT FK still blocks (budget_line,
    appraisal_cost_line, PO line, etc.) — caller will RETIRE.
    """
    sp = db.begin_nested()
    try:
        # Soft links that we own the lifecycle of:
        for sql in (
            "DELETE FROM cost_code_subcategories WHERE cost_code_id = :i",
            "DELETE FROM project_cost_codes WHERE cost_code_id = :i",
            "DELETE FROM cost_code_entity_mapping WHERE cost_code_id = :i",
            "DELETE FROM cost_code_buildertrend_overrides WHERE cost_code_id = :i",
            "UPDATE cost_codes SET replaced_by_code_id = NULL "
            "WHERE replaced_by_code_id = :i",
        ):
            try:
                db.execute(text(sql), {"i": code_id})
            except Exception:
                # Table may not exist on all heads — keep going.
                sp.rollback()
                sp = db.begin_nested()
        # Hard delete:
        db.execute(text("DELETE FROM cost_codes WHERE id = :i"),
                   {"i": code_id})
        sp.commit()
        return True
    except IntegrityError:
        sp.rollback()
        return False


def _reconcile_cost_codes(
    db, parent_ids: dict[str, str], sub_ids: dict[str, str], diff: Diff
) -> None:
    """Authoritative reconciliation:
      * Insert any missing canonical (prefix, sequence) row.
      * Update existing canonical rows' name / section_id.
      * Delete any non-canonical row whose prefix IS in the canonical
        prefix set. If a RESTRICT FK blocks deletion, retire (set
        status='Retired') instead.
    """
    section_by_group_code: dict[str, str] = {**parent_ids, **sub_ids}

    live_by_code = {
        r.code: r for r in db.execute(text("""
            SELECT id, code, prefix, sequence, section_id, status, name
            FROM cost_codes
        """)).fetchall()
    }

    # Pass 1 — upsert canonical rows.
    for canon_code, canon_name in CANONICAL_CODES.items():
        prefix, seq_s = canon_code.split("-")
        sequence = int(seq_s)
        target_section_id = section_by_group_code[PREFIX_TO_GROUP_CODE[prefix]]

        row = live_by_code.get(canon_code)
        if row is None:
            profile = DEFAULT_PROFILE_BY_PREFIX[prefix]
            db.execute(text("""
                INSERT INTO cost_codes (
                  code, prefix, sequence, name, section_id,
                  buildertrend_category, default_entity, is_vattable,
                  vat_treatment, status, display_order
                ) VALUES (
                  :code, :prefix, :sequence, :name, :section_id,
                  :buildertrend_category, :default_entity,
                  :is_vattable, :vat_treatment, 'Active', :display_order
                )
            """), {
                "code": canon_code, "prefix": prefix, "sequence": sequence,
                "name": canon_name, "section_id": target_section_id,
                "display_order": sequence,
                **profile,
            })
            diff.codes_added.append(canon_code)
            continue

        # Existing row — reconcile name + section_id + status.
        updates = {}
        if row.name != canon_name:
            updates["name"] = canon_name
            diff.codes_renamed.append(f"{canon_code}: {row.name!r}→{canon_name!r}")
        if str(row.section_id) != target_section_id:
            updates["section_id"] = target_section_id
            diff.codes_repointed.append(canon_code)
        if row.status != "Active":
            updates["status"] = "Active"
        # Canonical Active codes must NOT carry retire metadata or
        # point at a replacement (B88 corrected master 2026-06-09:
        # SER-10 is Active 'Lift installation', not retired into
        # SER-06 as the legacy 0016_audit_remediation_patch_3
        # migration left it).
        retire_meta_to_clear = db.execute(text("""
            SELECT replaced_by_code_id, retired_at, retired_reason
            FROM cost_codes WHERE id = :i
        """), {"i": row.id}).first()
        if retire_meta_to_clear and (
            retire_meta_to_clear.replaced_by_code_id is not None
            or retire_meta_to_clear.retired_at is not None
            or retire_meta_to_clear.retired_reason is not None
        ):
            updates["replaced_by_code_id"] = None
            updates["retired_at"] = None
            updates["retired_reason"] = None
        if updates:
            set_clauses = ", ".join(f"{k} = :{k}" for k in updates)
            updates["id"] = row.id
            db.execute(
                text(f"UPDATE cost_codes SET {set_clauses} WHERE id = :id"),
                updates,
            )
        else:
            diff.codes_unchanged += 1

    # Pass 2 — remove non-canonical rows whose prefix is canonical.
    canonical_set = set(CANONICAL_CODES.keys())
    canonical_prefixes = set(PREFIX_TO_GROUP_CODE.keys())
    for code, row in list(live_by_code.items()):
        if code in canonical_set:
            continue
        if row.prefix not in canonical_prefixes:
            continue
        if _try_hard_delete_code(db, str(row.id)):
            diff.codes_deleted.append(code)
        else:
            db.execute(text(
                "UPDATE cost_codes SET status='Retired' WHERE id = :i"
            ), {"i": row.id})
            diff.codes_retired.append(code)

    # Sanity — nothing must hang directly off Construction parent "4".
    construction_id = parent_ids["4"]
    rows = db.execute(text("""
        SELECT code FROM cost_codes
        WHERE section_id = :s ORDER BY code
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
