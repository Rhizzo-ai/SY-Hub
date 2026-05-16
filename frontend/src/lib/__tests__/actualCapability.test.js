/**
 * Unit tests — lib/actualCapability.js (Chat 19B §R6).
 *
 * Pure-function matrix coverage: state × permission × isDesktop.
 */
import {
  canViewActuals, canCreateActual, canEditDraft, canDeleteDraft,
  canPostDraft, canMarkPaid, canVoid, canDispute, canUndispute,
  canReleaseRetention, canAttach, canDeleteAttachment, canViewSensitive,
  canViewPaymentsPage,
} from '../actualCapability';
import { makeDraftActual, makePostedActual, makePaidActual } from '../../test/mocks/fixtures';

const SUPER  = { is_super_admin: true, permissions: [] };
const VIEWER = { permissions: ['actuals.view'] };
const CREATOR = { permissions: ['actuals.view', 'actuals.create'] };
const EDITOR = { permissions: ['actuals.view', 'actuals.create', 'actuals.edit'] };
const APPROVER = {
  permissions: ['actuals.view', 'actuals.create', 'actuals.edit', 'actuals.approve'],
};
const NONE = { permissions: [] };

describe('actualCapability — view + create', () => {
  test('canViewActuals true with actuals.view, false without', () => {
    expect(canViewActuals(VIEWER)).toBe(true);
    expect(canViewActuals(NONE)).toBe(false);
  });

  test('canCreateActual mobile-allowed (Q2)', () => {
    expect(canCreateActual(CREATOR, false)).toBe(true);
    expect(canCreateActual(CREATOR, true)).toBe(true);
    expect(canCreateActual(VIEWER, true)).toBe(false);
  });
});

describe('actualCapability — edit/delete Draft', () => {
  test('canEditDraft true on Draft + edit + desktop; false on Posted; false on mobile', () => {
    const d = makeDraftActual();
    expect(canEditDraft(d, EDITOR, true)).toBe(true);
    expect(canEditDraft(makePostedActual(), EDITOR, true)).toBe(false);
    expect(canEditDraft(d, EDITOR, false)).toBe(false);
    expect(canEditDraft(d, VIEWER, true)).toBe(false);
  });

  test('canDeleteDraft mirrors canEditDraft', () => {
    const d = makeDraftActual();
    expect(canDeleteDraft(d, EDITOR, true)).toBe(true);
    expect(canDeleteDraft(d, EDITOR, false)).toBe(false);
    expect(canDeleteDraft(makePostedActual(), EDITOR, true)).toBe(false);
  });
});

describe('actualCapability — post Draft', () => {
  test('canPostDraft requires actuals.edit + Draft + desktop', () => {
    const d = makeDraftActual();
    expect(canPostDraft(d, EDITOR, true)).toBe(true);
    expect(canPostDraft(d, APPROVER, true)).toBe(true);
    expect(canPostDraft(d, VIEWER, true)).toBe(false);
    expect(canPostDraft(d, EDITOR, false)).toBe(false);
    expect(canPostDraft(makePostedActual(), EDITOR, true)).toBe(false);
  });
});

describe('actualCapability — mark Paid', () => {
  test('canMarkPaid only on Posted; not Disputed', () => {
    expect(canMarkPaid(makePostedActual(), APPROVER, true)).toBe(true);
    expect(canMarkPaid(makePostedActual({ status: 'Disputed' }), APPROVER, true)).toBe(false);
    expect(canMarkPaid(makePostedActual(), EDITOR, true)).toBe(false); // needs approve
    expect(canMarkPaid(makePostedActual(), APPROVER, false)).toBe(false); // mobile blocked
  });
});

describe('actualCapability — void', () => {
  test('canVoid true on Draft/Posted/Disputed; false on Paid (credit-note path) and Void', () => {
    expect(canVoid(makeDraftActual(), APPROVER, true)).toBe(true);
    expect(canVoid(makePostedActual(), APPROVER, true)).toBe(true);
    expect(canVoid(makePostedActual({ status: 'Disputed' }), APPROVER, true)).toBe(true);
    expect(canVoid(makePaidActual(), APPROVER, true)).toBe(false);
    expect(canVoid(makePostedActual({ status: 'Void' }), APPROVER, true)).toBe(false);
    expect(canVoid(makePostedActual(), EDITOR, true)).toBe(false); // needs approve
  });
});

describe('actualCapability — dispute / undispute', () => {
  test('canDispute only on Posted', () => {
    expect(canDispute(makePostedActual(), EDITOR, true)).toBe(true);
    expect(canDispute(makeDraftActual(), EDITOR, true)).toBe(false);
    expect(canDispute(makePostedActual({ status: 'Disputed' }), EDITOR, true)).toBe(false);
  });

  test('canUndispute only on Disputed', () => {
    expect(canUndispute(makePostedActual({ status: 'Disputed' }), EDITOR, true)).toBe(true);
    expect(canUndispute(makePostedActual(), EDITOR, true)).toBe(false);
  });
});

describe('actualCapability — retention release', () => {
  test('canReleaseRetention only Posted/Paid AND not already released', () => {
    expect(canReleaseRetention(makePostedActual(), APPROVER, true)).toBe(true);
    expect(canReleaseRetention(makePaidActual(), APPROVER, true)).toBe(true);
    expect(canReleaseRetention(makeDraftActual(), APPROVER, true)).toBe(false);
    expect(
      canReleaseRetention(makePostedActual({ retention_released: true }), APPROVER, true),
    ).toBe(false);
  });
});

describe('actualCapability — attach / delete-attachment', () => {
  test('canAttach false on Void; true elsewhere with edit + desktop', () => {
    expect(canAttach(makePostedActual({ status: 'Void' }), EDITOR, true)).toBe(false);
    expect(canAttach(makePostedActual(), EDITOR, true)).toBe(true);
    expect(canAttach(makeDraftActual(), EDITOR, true)).toBe(true);
    expect(canAttach(makePostedActual(), EDITOR, false)).toBe(false);
  });

  test('canDeleteAttachment mirrors canAttach', () => {
    expect(canDeleteAttachment(makePostedActual({ status: 'Void' }), EDITOR, true)).toBe(false);
    expect(canDeleteAttachment(makePostedActual(), EDITOR, true)).toBe(true);
  });
});

describe('actualCapability — sensitive + payments page', () => {
  test('canViewSensitive', () => {
    expect(canViewSensitive({ permissions: ['actuals.view_sensitive'] })).toBe(true);
    expect(canViewSensitive(VIEWER)).toBe(false);
  });

  test('canViewPaymentsPage true with actuals.view', () => {
    expect(canViewPaymentsPage(VIEWER)).toBe(true);
    expect(canViewPaymentsPage(NONE)).toBe(false);
  });
});

describe('actualCapability — super_admin + mobile floor', () => {
  test('super_admin bypasses all permission checks where state allows', () => {
    expect(canPostDraft(makeDraftActual(), SUPER, true)).toBe(true);
    expect(canMarkPaid(makePostedActual(), SUPER, true)).toBe(true);
    expect(canVoid(makePostedActual(), SUPER, true)).toBe(true);
    expect(canReleaseRetention(makePostedActual(), SUPER, true)).toBe(true);
    // State machine still rules — Paid cannot be voided even for super_admin.
    expect(canVoid(makePaidActual(), SUPER, true)).toBe(false);
  });

  test('mobile-floor blocks all desktop-only actions for any user', () => {
    expect(canEditDraft(makeDraftActual(), SUPER, false)).toBe(false);
    expect(canPostDraft(makeDraftActual(), SUPER, false)).toBe(false);
    expect(canMarkPaid(makePostedActual(), SUPER, false)).toBe(false);
    expect(canVoid(makePostedActual(), SUPER, false)).toBe(false);
    expect(canDispute(makePostedActual(), SUPER, false)).toBe(false);
    expect(canUndispute(makePostedActual({ status: 'Disputed' }), SUPER, false)).toBe(false);
    expect(canReleaseRetention(makePostedActual(), SUPER, false)).toBe(false);
    expect(canAttach(makePostedActual(), SUPER, false)).toBe(false);
  });
});
