/**
 * Capability helper tests — Chat 24 §R5.
 */
import {
  canApprovePO, canCreatePO, canEditIssuedPO, canEditPO, canReceiptPO,
  canViewPOs, canViewSensitivePO, canViewSensitiveSupplier, canViewSuppliers,
  canViewPrefixes, canEditPrefixes, nextActionsForStatus,
} from '@/lib/poCapability';


const readOnly =     { permissions: ['suppliers.view', 'pos.view'] };
const siteManager =  { permissions: ['suppliers.view', 'pos.view', 'pos.receipt'] };
const projectMgr =   { permissions: [
  'suppliers.view', 'suppliers.create', 'suppliers.edit',
  'pos.view', 'pos.view_sensitive', 'pos.create', 'pos.edit',
  'pos.issue', 'pos.receipt', 'pos.close', 'pos.delete',
]};
const director =     { permissions: [
  'suppliers.view', 'suppliers.view_sensitive', 'suppliers.create',
  'suppliers.edit', 'suppliers.archive',
  'pos.view', 'pos.view_sensitive', 'pos.create', 'pos.edit',
  'pos.edit_issued', 'pos.delete', 'pos.issue', 'pos.approve',
  'pos.void', 'pos.close', 'pos.receipt',
]};


describe('PO capability helpers', () => {
  test('read_only can view but cannot create/edit/approve', () => {
    expect(canViewPOs(readOnly)).toBe(true);
    expect(canViewSensitivePO(readOnly)).toBe(false);
    expect(canCreatePO(readOnly)).toBe(false);
    expect(canEditPO(readOnly)).toBe(false);
    expect(canApprovePO(readOnly)).toBe(false);
  });

  test('site_manager can receipt but not edit_issued nor approve', () => {
    expect(canReceiptPO(siteManager)).toBe(true);
    expect(canEditIssuedPO(siteManager)).toBe(false);
    expect(canApprovePO(siteManager)).toBe(false);
  });

  test('project_manager can create / edit / receipt but cannot approve', () => {
    expect(canCreatePO(projectMgr)).toBe(true);
    expect(canEditPO(projectMgr)).toBe(true);
    expect(canReceiptPO(projectMgr)).toBe(true);
    expect(canApprovePO(projectMgr)).toBe(false);
  });

  test('director can do everything', () => {
    expect(canApprovePO(director)).toBe(true);
    expect(canEditIssuedPO(director)).toBe(true);
    expect(canViewSensitivePO(director)).toBe(true);
    expect(canViewSensitiveSupplier(director)).toBe(true);
  });

  test('null user is denied everything', () => {
    expect(canViewSuppliers(null)).toBe(false);
    expect(canViewPOs(null)).toBe(false);
    expect(canCreatePO(undefined)).toBe(false);
  });

  test('prefixes view/edit derives from PO/supplier perms', () => {
    expect(canViewPrefixes(readOnly)).toBe(true);
    expect(canEditPrefixes(readOnly)).toBe(false);
    expect(canEditPrefixes(projectMgr)).toBe(true);
  });
});


describe('nextActionsForStatus', () => {
  test('draft → edit/submit/delete', () => {
    expect(nextActionsForStatus('draft')).toEqual(['edit', 'submit', 'delete']);
  });
  test('submitted → approve/reject', () => {
    expect(nextActionsForStatus('submitted')).toEqual(['approve', 'reject']);
  });
  test('issued → receipt/void/edit_issued', () => {
    expect(nextActionsForStatus('issued')).toEqual(['receipt', 'void', 'edit_issued']);
  });
  test('partially_receipted → receipt/edit_issued', () => {
    expect(nextActionsForStatus('partially_receipted')).toEqual(['receipt', 'edit_issued']);
  });
  test('receipted → close/edit_issued', () => {
    expect(nextActionsForStatus('receipted')).toEqual(['close', 'edit_issued']);
  });
  test('closed/voided → no actions', () => {
    expect(nextActionsForStatus('closed')).toEqual([]);
    expect(nextActionsForStatus('voided')).toEqual([]);
  });
  test('unknown status → no actions', () => {
    expect(nextActionsForStatus('whatever')).toEqual([]);
  });
});
