"""0013 cost codes seed (133 rows from SY_Homes_Cost_Codes.xlsx)

Revision ID: 0013_cost_codes_seed
Revises: 0012_cost_code_sections_seed

Source: SY_Homes_Cost_Codes.xlsx (TSV embedded below). 18 prefixes
across 9 sections. Per-prefix counts:
  ACQ=10 PLN=9 DES=9 FAC=5 SUB=5 SUP=10 INT=6 FIT=5 SER=10 PRE=1
  EXB=3 EXT=9 PRL=16 SAL=9 FIN=5 OHD=8 ACC=8 CTG=5  → 133 total

Per-code metadata (default_entity, applies_to_*, vat_treatment,
is_vattable, is_cis_applicable, is_retention_applicable,
is_capitalisable) is DERIVED from prefix rules in §C.3 + per-code
overrides in §C.4 of the Prompt 1.6 brief.

Single audit summary row per the bulk-seed convention (§I).
"""
import json
import re
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision = "0013_cost_codes_seed"
down_revision = "0012_cost_code_sections_seed"
branch_labels = None
depends_on = None


MIGRATION_AUDIT_NAMESPACE = uuid.UUID("3a14a3e0-1f2c-4f8a-9c5d-bb1f6f3e0001")


# ---- Source data (verbatim from spreadsheet) ----------------------------

TSV = """\
section\tcode\tdescription\tbuildertrend_category
1. Acquisition\tACQ-01\tLand / site purchase price\t1 Land & Acquisition
1. Acquisition\tACQ-02\tStamp Duty Land Tax (SDLT)\t1 Land & Acquisition
1. Acquisition\tACQ-03\tAcquisition legal & conveyancing fees\t1 Land & Acquisition
1. Acquisition\tACQ-04\tEstate agent / land finder fees\t1 Land & Acquisition
1. Acquisition\tACQ-05\tTopographical & measured surveys\t1 Land & Acquisition
1. Acquisition\tACQ-06\tEnvironmental, ecological & contamination surveys\t1 Land & Acquisition
1. Acquisition\tACQ-07\tGeotechnical & soil investigation\t1 Land & Acquisition
1. Acquisition\tACQ-08\tUtility searches & enquiries\t1 Land & Acquisition
1. Acquisition\tACQ-09\tOption agreements & conditional contract costs\t1 Land & Acquisition
1. Acquisition\tACQ-10\tSite holding / carry costs (council tax, security, maintenance)\t1 Land & Acquisition
2. Planning & Statutory Approvals\tPLN-01\tPlanning application & pre-application fees\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-02\tCommunity Infrastructure Levy (CIL)\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-03\tSection 106 contributions\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-04\tBuilding Regulations application & inspection fees\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-05\tPlanning consultant / advisor fees\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-06\tLegal fees \u2013 planning agreements & appeals\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-07\tHighway authority fees, S278 & S38 agreements\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-08\tEcology / arboriculture mitigation (condition discharge)\t2 Planning & Statutory
2. Planning & Statutory Approvals\tPLN-09\tOther statutory approvals & condition discharge costs\t2 Planning & Statutory
3. Design & Professional Fees\tDES-01\tArchitect / design team fees \u2014 architectural design, planning drawings, working drawings\t3 Professional Fees
3. Design & Professional Fees\tDES-02\tStructural & civil engineer fees \u2014 structural calculations, foundation design, retaining wall design\t3 Professional Fees
3. Design & Professional Fees\tDES-03\tMechanical & electrical (M&E) consultant fees\t3 Professional Fees
3. Design & Professional Fees\tDES-04\tOther specialist consultants (acoustic, fire, SAP/EPC)\t3 Professional Fees
3. Design & Professional Fees\tDES-05\tQuantity surveyor / cost consultant fees\t3 Professional Fees
3. Design & Professional Fees\tDES-06\tProject management / employer's agent fees\t3 Professional Fees
3. Design & Professional Fees\tDES-07\tNHBC / warranty provider registration & pre-build audit\t3 Professional Fees
3. Design & Professional Fees\tDES-08\tCDM principal designer fees\t3 Professional Fees
3. Design & Professional Fees\tDES-09\tOther professional fees\t3 Professional Fees
Facilitating Works\tFAC-01\tHazardous material removal (asbestos, contamination)\t4. Facilitating Works
Facilitating Works\tFAC-02\tDemolition works\t4. Facilitating Works
Facilitating Works\tFAC-03\tSite clearance & enabling works \u2014 site strip, vegetation clearance, tree removal, site set up, temporary access\t4. Facilitating Works
Facilitating Works\tFAC-04\tSpecialist ground works (piling mats, ground improvement)\t4. Facilitating Works
Facilitating Works\tFAC-05\tTemporary diversion of services / watercourses\t4. Facilitating Works
Substructure\tSUB-01\tFoundations (strip, trench fill, pad, raft, piled) \u2014 includes concrete for foundations, rebar, formwork, excavation\t4. Substructure
Substructure\tSUB-02\tMasonry below DPC (blockwork, brickwork below damp proof course, engineering bricks below ground)\t4. Substructure
Substructure\tSUB-03\tDamp proof course, membranes & tanking \u2014 DPC, DPM, radon barrier, visqueen, tanking membrane\t4. Substructure
Substructure\tSUB-04\tGround floor slab & structure \u2014 concrete slab, ready mix concrete, oversite concrete, blinding, mesh reinforcement\t4. Substructure
Substructure\tSUB-05\tSubstructure drainage (land drains, sub-floor)\t4. Substructure
Superstructure\tSUP-01\tStructural frame (steel beams, RSJ, universal beams, steel columns, timber frame kit, glulam) \u2014 NOT fence posts or boundary walls\t4. Superstructure
Superstructure\tSUP-02\tExternal walls (facing bricks, engineering bricks, blockwork, dense/aerated blocks, cavity insulation, kingspan, celotex, dritherm, render, k-rend, wall ties, cavity trays, weep vents, lintels)\t4. Superstructure
Superstructure\tSUP-03\tUpper floor structures (joists, beams, decking)\t4. Superstructure
Superstructure\tSUP-04\tRoof structure, trusses & coverings \u2014 roof trusses, tiles, slates, ridge/hip tiles, roof felt, breather membrane, battens, lead flashing\t4. Superstructure
Superstructure\tSUP-05\tFascias, soffits, bargeboards & rainwater goods \u2014 guttering, downpipes, roofline products\t4. Superstructure
Superstructure\tSUP-06\tStairs & balustrades\t4. Superstructure
Superstructure\tSUP-07\tWindows & external doors (supply & install) \u2014 uPVC windows, composite doors, patio doors, bi-fold doors, double glazed units\t4. Superstructure
Superstructure\tSUP-08\tCarpentry first fix (studwork, partitions, noggins, door linings, boxing)\t4. Superstructure
Superstructure\tSUP-09\tCarpentry second fix (skirting, architrave, shelving, hanging doors)\t4. Superstructure
Superstructure\tSUP-10\tInternal doors, frames & ironmongery (supply)\t4. Superstructure
Internal Finishes\tINT-01\tPlastering & dry lining \u2014 plasterboard, bonding plaster, multi finish, skim coat, dry lining\t4. Internal Finishes
Internal Finishes\tINT-02\tPainting & decorating (internal) \u2014 emulsion, primer, undercoat, gloss, eggshell, decorating materials\t4. Internal Finishes
Internal Finishes\tINT-03\tWall & floor tiling\t4. Internal Finishes
Internal Finishes\tINT-04\tKitchens \u2014 supply of kitchen units, doors, worktops, handles\t4. Internal Finishes
Internal Finishes\tINT-05\tBathrooms & sanitaryware \u2014 baths, shower trays, WCs, toilets, basins, vanity units, shower screens, taps\t4. Internal Finishes
Internal Finishes\tINT-06\tCeiling finishes (boarding, coving, features)\t4. Internal Finishes
Fittings & Equipment\tFIT-01\tKitchen units, worktops & appliances\t4. Fittings & Equipment
Fittings & Equipment\tFIT-02\tBathroom sanitaryware, brassware & accessories\t4. Fittings & Equipment
Fittings & Equipment\tFIT-03\tBuilt-in joinery (wardrobes, shelving, utility units)\t4. Fittings & Equipment
Fittings & Equipment\tFIT-04\tMirrors, shower screens & bathroom furniture\t4. Fittings & Equipment
Fittings & Equipment\tFIT-05\tOther fittings & furnishings\t4. Fittings & Equipment
Services\tSER-01\tElectrical first fix \u2014 cabling, back boxes, consumer unit, earth bonding, containment\t4. Services
Services\tSER-02\tElectrical second fix \u2014 sockets, switches, light fittings, smoke detectors, CO detectors, testing\t4. Services
Services\tSER-03\tPlumbing & heating first fix \u2014 soil pipes, waste pipes, hot/cold pipework, underfloor heating loops\t4. Services
Services\tSER-04\tPlumbing & heating second fix \u2014 boiler install, radiators, towel rails, bathroom fit-out, taps, shower valves\t4. Services
Services\tSER-05\tVentilation (extract fans, MVHR, ductwork)\t4. Services
Services\tSER-06\tLifts & access \u2014 passenger lifts, platform lifts, stairlifts\t4. Services
Services\tSER-07\tData, TV, security & smart home systems\t4. Services
Services\tSER-08\tBuilder's work in connection with services (chasing, boxing, making good)\t4. Services
Services\tSER-09\tFire stopping (penetration seals, cavity barriers, intumescent strips)\t4. Services
Services\tSER-10\tLift installation (passenger, platform, stairlift)\t4. Services
Prefab / MMC\tPRE-01\tPrefabricated building units (timber frame kit, SIPs, modular, MMC)\t4. Prefab / MMC
Existing Buildings\tEXB-01\tMinor demolition & internal strip-out\t4. Existing Buildings
Existing Buildings\tEXB-02\tStructural alterations & repairs to existing\t4. Existing Buildings
Existing Buildings\tEXB-03\tDamp proofing & timber treatment to existing\t4. Existing Buildings
External Works\tEXT-01\tExternal drainage (private) \u2014 plot drainage, manholes, inspection chambers, soakaways, gullies\t4. External Works
External Works\tEXT-02\tAdoptable drainage \u2014 S104 sewers, pumping stations, attenuation tanks, surface water systems\t4. External Works
External Works\tEXT-03\tUtility service connections & metering\t4. External Works
External Works\tEXT-04\tDriveways, paths & private hard landscaping \u2014 block paving, tarmac, flagstones, kerbs, edging\t4. External Works
External Works\tEXT-05\tAdoptable roads & infrastructure (S38 roads, kerbing, street lighting)\t4. External Works
External Works\tEXT-06\tSoft landscaping, planting, turfing & topsoil \u2014 turf, grass seed, compost, shrubs, trees\t4. External Works
External Works\tEXT-07\tBoundary fencing, walls & gates \u2014 close board fencing, fence posts (timber & concrete), gravel boards, panel fences, garden walls, entrance gates, concrete posts\t4. External Works
External Works\tEXT-08\tExternal lighting & fixtures (private)\t4. External Works
External Works\tEXT-09\tMinor building works (garages, car ports, bin/cycle stores)\t4. External Works
Preliminaries\tPRL-01\tSite mobilisation & demobilisation\t4. Preliminaries
Preliminaries\tPRL-02\tTemporary welfare facilities (toilets, mess room)\t4. Preliminaries
Preliminaries\tPRL-03\tTemporary fencing, hoarding & site security \u2014 heras fencing, hoarding panels, security, CCTV hire\t4. Preliminaries
Preliminaries\tPRL-04\tScaffolding, access towers & working platforms\t4. Preliminaries
Preliminaries\tPRL-05\tSite management & supervision (site manager, foreman)\t4. Preliminaries
Preliminaries\tPRL-06\tGeneral site labour (labourers, banksmen, material handling)\t4. Preliminaries
Preliminaries\tPRL-07\tHired plant & equipment \u2014 excavators, dumpers, telehandlers, cherry pickers, rollers, compactors, generators\t4. Preliminaries
Preliminaries\tPRL-08\tTemporary services (power, water, drainage, lighting)\t4. Preliminaries
Preliminaries\tPRL-09\tHealth & safety, CDM compliance & training\t4. Preliminaries
Preliminaries\tPRL-10\tWaste management, skip hire & site tidying\t4. Preliminaries
Preliminaries\tPRL-11\tContractors all-risks & site-specific insurance\t4. Preliminaries
Preliminaries\tPRL-12\tSetting out, surveys & quality control\t4. Preliminaries
Preliminaries\tPRL-13\tWarranty / NHBC inspections during build\t4. Preliminaries
Preliminaries\tPRL-14\tFinal clean & handover (builders clean, sparkle clean)\t4. Preliminaries
Preliminaries\tPRL-15\tSnagging & remedial works (pre-handover)\t4. Preliminaries
Preliminaries\tPRL-16\tOther preliminaries\t4. Preliminaries
5. Sales, Marketing & Disposal\tSAL-01\tMarketing, brochures, website & digital advertising\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-02\tShow home setup, furnishing & staging\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-03\tSales agent commissions\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-04\tLegal fees \u2013 sales conveyancing\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-05\tStamp duty reimbursement (buyer incentive)\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-06\tSales incentives / part-exchange costs\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-07\tPhotography, CGIs, virtual tours & signage\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-08\tEPC, warranty handover packs & homeowner manual\t5 Sales & Marketing
5. Sales, Marketing & Disposal\tSAL-09\tOther sales & disposal costs\t5 Sales & Marketing
6. Finance Costs\tFIN-01\tDevelopment finance interest & arrangement fees\t6 Finance Costs
6. Finance Costs\tFIN-02\tBank / lender monitoring surveyor & valuation fees\t6 Finance Costs
6. Finance Costs\tFIN-03\tLegal fees \u2013 finance agreements\t6 Finance Costs
6. Finance Costs\tFIN-04\tBroker fees\t6 Finance Costs
6. Finance Costs\tFIN-05\tOther finance costs\t6 Finance Costs
7. Company Overheads\tOHD-01\tHead office salaries & admin\t7 Company Overheads
7. Company Overheads\tOHD-02\tOffice rent, utilities & equipment\t7 Company Overheads
7. Company Overheads\tOHD-03\tInsurance (company-wide PI, D&O, EL)\t7 Company Overheads
7. Company Overheads\tOHD-04\tGeneral corporate legal fees\t7 Company Overheads
7. Company Overheads\tOHD-05\tSoftware, subscriptions & IT\t7 Company Overheads
7. Company Overheads\tOHD-06\tTraining & professional development (CPD)\t7 Company Overheads
7. Company Overheads\tOHD-07\tMarketing (company level / brand)\t7 Company Overheads
7. Company Overheads\tOHD-08\tTravel & vehicle costs \u2014 fuel, diesel, petrol, tyres, MOT, vehicle service, mileage\t7 Company Overheads
8. Accounting & Financial Services\tACC-01\tAudit fees\t8 Accounting
8. Accounting & Financial Services\tACC-02\tTax advice & corporation tax compliance\t8 Accounting
8. Accounting & Financial Services\tACC-03\tVAT returns & reclaim processing\t8 Accounting
8. Accounting & Financial Services\tACC-04\tPayroll processing & CIS administration\t8 Accounting
8. Accounting & Financial Services\tACC-05\tBookkeeping & accounting software licences\t8 Accounting
8. Accounting & Financial Services\tACC-06\tBank charges & transaction fees\t8 Accounting
8. Accounting & Financial Services\tACC-07\tFinancial reporting & management accounts\t8 Accounting
8. Accounting & Financial Services\tACC-08\tOther accounting & financial services\t8 Accounting
9. Contingency, Risk & Miscellaneous\tCTG-01\tContingency allowance (design, construction, employer change, inflation risk)\t9 Contingency, Risk & Miscellaneous
9. Contingency, Risk & Miscellaneous\tCTG-02\tVAT (irrecoverable or partial exemption)\t9 Contingency, Risk & Miscellaneous
9. Contingency, Risk & Miscellaneous\tCTG-03\tPost-completion defects & remedial works (DLP period)\t9 Contingency, Risk & Miscellaneous
9. Contingency, Risk & Miscellaneous\tCTG-04\tPost-completion maintenance (service charges, statutory inspections \u2013 until management company takeover)\t9 Contingency, Risk & Miscellaneous
9. Contingency, Risk & Miscellaneous\tCTG-05\tOther miscellaneous / unforeseen costs\t9 Contingency, Risk & Miscellaneous
"""


# ---- Prefix → section mapping (§C.2) ------------------------------------

PREFIX_TO_SECTION = {
    "ACQ": "acquisition",
    "PLN": "planning",
    "DES": "design",
    "FAC": "construction", "SUB": "construction", "SUP": "construction",
    "INT": "construction", "FIT": "construction", "SER": "construction",
    "PRE": "construction", "EXB": "construction", "EXT": "construction",
    "PRL": "construction",
    "SAL": "sales_marketing",
    "FIN": "finance",
    "OHD": "company_overheads",
    "ACC": "accounting",
    "CTG": "contingency",
}


# ---- Prefix-derived metadata defaults (§C.3) ----------------------------
# (default_entity, applies_parent, applies_spv, applies_construction_co,
#  vat_treatment, is_vattable, is_cis, is_retention, is_capitalisable)

PREFIX_DEFAULTS = {
    "ACQ": ("SPV", False, True, False, "Standard", True, False, False, True),
    "PLN": ("SPV", False, True, False, "Standard", True, False, False, True),
    "DES": ("Context_Dependent", False, True, True, "Standard", True, False, False, True),
    "FAC": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "SUB": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "SUP": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "INT": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "FIT": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "SER": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "PRE": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "EXB": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "EXT": ("ConstructionCo", False, False, True, "Reverse_Charge", True, True, True, True),
    "PRL": ("ConstructionCo", False, False, True, "Standard", True, False, False, True),
    "SAL": ("SPV", False, True, False, "Standard", True, False, False, False),
    "FIN": ("SPV", True, True, False, "Exempt", False, False, False, True),
    "OHD": ("Parent", True, False, False, "Standard", True, False, False, False),
    "ACC": ("Parent", True, True, True, "Standard", True, False, False, False),
    "CTG": ("Context_Dependent", False, True, True, "Standard", True, False, False, True),
}


# ---- Per-code overrides (§C.4) ------------------------------------------

PER_CODE_OVERRIDES = {
    "ACQ-01": {"vat_treatment": "Exempt", "is_vattable": False},
    "ACQ-02": {"vat_treatment": "Exempt", "is_vattable": False},
    "ACQ-09": {"vat_treatment": "Exempt", "is_vattable": False},
    "PLN-02": {"vat_treatment": "Exempt", "is_vattable": False},
    "PLN-03": {"vat_treatment": "Exempt", "is_vattable": False},
    "FIN-02": {"vat_treatment": "Standard", "is_vattable": True},
    "FIN-03": {"vat_treatment": "Standard", "is_vattable": True},
    "FIN-04": {"vat_treatment": "Standard", "is_vattable": True},
    "ACC-06": {"vat_treatment": "Exempt", "is_vattable": False},
    "CTG-02": {"vat_treatment": "Mixed", "is_vattable": False},
}


def _parse_rows():
    """Yield (code, prefix, sequence, name, description, bt_category) tuples."""
    lines = TSV.strip().splitlines()
    header = lines[0].split("\t")
    assert header == ["section", "code", "description", "buildertrend_category"], header
    out = []
    for line in lines[1:]:
        section_disp, code, description, bt_category = line.split("\t")
        m = re.match(r"^([A-Z]{3})-(\d{2})$", code)
        if not m:
            raise RuntimeError(f"Bad code format: {code!r}")
        prefix = m.group(1)
        seq = int(m.group(2))
        # name = first 100 chars of description (or full description if shorter)
        name = description if len(description) <= 100 else description[:100]
        out.append((code, prefix, seq, name, description, bt_category))
    return out


def upgrade() -> None:
    bind = op.get_bind()
    rows = _parse_rows()
    if len(rows) != 133:
        raise RuntimeError(f"Expected 133 cost codes, got {len(rows)}")

    # Resolve section ids
    section_rows = bind.execute(sa.text(
        "SELECT code, id FROM cost_code_sections"
    )).fetchall()
    section_ids = {r[0]: r[1] for r in section_rows}

    inserted = 0
    for code, prefix, seq, name, description, bt_category in rows:
        section_code = PREFIX_TO_SECTION[prefix]
        section_id = section_ids[section_code]
        defaults = PREFIX_DEFAULTS[prefix]
        meta = {
            "default_entity": defaults[0],
            "applies_to_parent": defaults[1],
            "applies_to_spv": defaults[2],
            "applies_to_construction_co": defaults[3],
            "vat_treatment": defaults[4],
            "is_vattable": defaults[5],
            "is_cis_applicable": defaults[6],
            "is_retention_applicable": defaults[7],
            "is_capitalisable": defaults[8],
        }
        meta.update(PER_CODE_OVERRIDES.get(code, {}))

        bind.execute(sa.text("""
            INSERT INTO cost_codes (
              id, code, prefix, sequence, name, description,
              section_id, buildertrend_category,
              applies_to_parent, applies_to_spv, applies_to_construction_co,
              default_entity, is_vattable, vat_treatment,
              is_cis_applicable, is_retention_applicable, is_capitalisable,
              status, display_order
            ) VALUES (
              gen_random_uuid(), :code, :prefix, :seq, :name, :description,
              :section_id, :bt,
              :applies_parent, :applies_spv, :applies_cc,
              :default_entity, :is_vattable, :vat_treatment,
              :is_cis, :is_ret, :is_cap,
              'Active', :seq
            )
            ON CONFLICT (code) DO NOTHING
        """), {
            "code": code, "prefix": prefix, "seq": seq,
            "name": name, "description": description,
            "section_id": section_id, "bt": bt_category,
            "applies_parent": meta["applies_to_parent"],
            "applies_spv": meta["applies_to_spv"],
            "applies_cc": meta["applies_to_construction_co"],
            "default_entity": meta["default_entity"],
            "is_vattable": meta["is_vattable"],
            "vat_treatment": meta["vat_treatment"],
            "is_cis": meta["is_cis_applicable"],
            "is_ret": meta["is_retention_applicable"],
            "is_cap": meta["is_capitalisable"],
        })
        inserted += 1

    rev_uuid = uuid.uuid5(MIGRATION_AUDIT_NAMESPACE, revision)
    bind.execute(sa.text("""
        INSERT INTO audit_log
            (id, action, resource_type, resource_id, field_changes,
             metadata_json, created_at)
        VALUES (gen_random_uuid(), 'Create', 'migration', :rid,
                CAST('[]' AS jsonb), CAST(:meta AS jsonb), :now)
    """), {
        "rid": str(rev_uuid),
        "meta": json.dumps({
            "kind": "seed_run", "revision": revision,
            "target": "cost_codes", "rows_seeded": inserted,
            "source": "SY_Homes_Cost_Codes.xlsx (TSV embedded)",
            "louise_to_review": [
                "vat_treatment defaults by prefix",
                "is_cis_applicable defaults",
                "is_retention_applicable defaults",
                "is_capitalisable defaults",
                "default_entity routing",
            ],
        }),
        "now": datetime.now(timezone.utc),
    })


def downgrade() -> None:
    op.execute("DELETE FROM cost_codes")
