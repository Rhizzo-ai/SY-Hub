/**
 * exportCostCodesCsv — B88 Pack 2 §7.3 / D8.
 *
 * Pure unit tests of the CSV-builder helper (no DOM download flow).
 */
import { exportCostCodesCsv } from '@/pages/CostCodeAdmin';

function makeTree() {
  return [
    {
      id: 'sec-4', code: '4', name: 'Construction',
      subgroups: [
        { id: 'sub-400', code: '4.00', name: 'Facilitating Works' },
      ],
    },
    {
      id: 'sec-1', code: '1', name: 'Land & Acquisition',
      subgroups: [],
    },
  ];
}

function makeCodes() {
  return [
    { id: 'cc-1', code: 'SUB-01', name: 'Demolition',
      section_id: 'sub-400', status: 'Active',
      nrm_reference: '5.3.1', xero_nominal_code: '5000' },
    { id: 'cc-2', code: 'ACQ-01', name: 'Land cost',
      section_id: 'sec-1', status: 'Active',
      nrm_reference: '', xero_nominal_code: '' },
    { id: 'cc-3', code: 'SUB-02', name: 'Site clearance, "extra"',
      section_id: 'sub-400', status: 'Retired',
      nrm_reference: null, xero_nominal_code: null },
  ];
}

describe('exportCostCodesCsv', () => {
  let createdAnchor;

  beforeEach(() => {
    // Stub URL + anchor DOM so we can capture the CSV without a real download.
    global.URL.createObjectURL = jest.fn(() => 'blob:mock-url');
    global.URL.revokeObjectURL = jest.fn();
    createdAnchor = null;
    const realCreate = document.createElement.bind(document);
    jest.spyOn(document, 'createElement').mockImplementation((tag) => {
      const el = realCreate(tag);
      if (tag === 'a') {
        createdAnchor = el;
        el.click = jest.fn();
      }
      return el;
    });
  });
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test('builds the canonical header + BOM + sorted rows', async () => {
    // Capture the CSV by re-implementing Blob to read the text on construct.
    let capturedCsv = '';
    const RealBlob = global.Blob;
    global.Blob = jest.fn().mockImplementation((parts, opts) => {
      capturedCsv = parts.join('');
      return new RealBlob(parts, opts);
    });

    exportCostCodesCsv(makeTree(), makeCodes());

    expect(global.Blob).toHaveBeenCalled();
    // Starts with UTF-8 BOM so Excel opens it cleanly.
    expect(capturedCsv.charCodeAt(0)).toBe(0xFEFF);
    const lines = capturedCsv.replace(/^\uFEFF/, '').split('\r\n');
    expect(lines[0]).toBe(
      'group_code,group_name,subgroup_code,subgroup_name,code,name,'
      + 'status,nrm_reference,xero_nominal_code',
    );
    // Sort is group → subgroup → code; '1' < '4'.
    expect(lines[1].startsWith('1,Land & Acquisition,,,ACQ-01,Land cost,Active'))
      .toBe(true);
    // Quoted cell for the value containing a comma + a quote.
    expect(lines.find((l) => l.includes('SUB-02')))
      .toMatch(/"Site clearance, ""extra"""/);

    // Anchor download attribute carries today's date.
    expect(createdAnchor).not.toBeNull();
    expect(createdAnchor.getAttribute('download'))
      .toMatch(/^SY_cost_codes_\d{8}\.csv$/);
    expect(createdAnchor.click).toHaveBeenCalled();

    global.Blob = RealBlob;
  });

  test('handles empty cost-codes list gracefully', () => {
    expect(() => exportCostCodesCsv(makeTree(), [])).not.toThrow();
  });
});
