/**
 * Unit tests — lib/budgetCapability.js (Build Pack §R8.4 TestStateMachineUI).
 *
 * Pure functions, no provider wiring. Eight tests cover the
 * status×permission matrix for Activate / Lock / Unlock / Close /
 * NewVersion + the line-edit and status-only helpers.
 */
import {
  canActivate, canLock, canUnlock, canClose, canCreateNewVersion,
  canEditLines, isBudgetEditable, isCostCodeMutable, canRefreshAttention,
} from '../budgetCapability';

const PM      = { permissions: ['budgets.view', 'budgets.edit', 'budgets.view_sensitive'] };
const ADMIN   = { permissions: ['budgets.view', 'budgets.edit', 'budgets.admin', 'budgets.view_sensitive'] };
const READER  = { permissions: ['budgets.view'] };

describe('budgetCapability — Activate', () => {
  test('canActivate true only when Draft AND budgets.edit', () => {
    expect(canActivate(PM, 'Draft')).toBe(true);
    expect(canActivate(PM, 'Active')).toBe(false);
    expect(canActivate(READER, 'Draft')).toBe(false);
  });
});

describe('budgetCapability — Lock', () => {
  test('canLock true only when Active AND budgets.edit', () => {
    expect(canLock(PM, 'Active')).toBe(true);
    expect(canLock(PM, 'Draft')).toBe(false);
    expect(canLock(READER, 'Active')).toBe(false);
  });
});

describe('budgetCapability — Unlock', () => {
  test('canUnlock requires Locked AND budgets.admin (not budgets.edit)', () => {
    expect(canUnlock(ADMIN, 'Locked')).toBe(true);
    // PM has budgets.edit but not budgets.admin — must NOT see Unlock.
    expect(canUnlock(PM, 'Locked')).toBe(false);
    expect(canUnlock(ADMIN, 'Active')).toBe(false);
  });
});

describe('budgetCapability — Close', () => {
  test('canClose true for Active or Locked with budgets.edit', () => {
    expect(canClose(PM, 'Active')).toBe(true);
    expect(canClose(PM, 'Locked')).toBe(true);
    expect(canClose(PM, 'Draft')).toBe(false);
    expect(canClose(PM, 'Closed')).toBe(false);
    expect(canClose(READER, 'Active')).toBe(false);
  });
});

describe('budgetCapability — NewVersion', () => {
  test('canCreateNewVersion true for Active/Locked/Closed with budgets.edit', () => {
    expect(canCreateNewVersion(PM, 'Active')).toBe(true);
    expect(canCreateNewVersion(PM, 'Locked')).toBe(true);
    expect(canCreateNewVersion(PM, 'Closed')).toBe(true);
    expect(canCreateNewVersion(PM, 'Draft')).toBe(false);
    expect(canCreateNewVersion(PM, 'Superseded')).toBe(false);
  });
});

describe('budgetCapability — line edits', () => {
  test('canEditLines true for Draft/Active with budgets.edit only', () => {
    expect(canEditLines(PM, 'Draft')).toBe(true);
    expect(canEditLines(PM, 'Active')).toBe(true);
    expect(canEditLines(PM, 'Locked')).toBe(false);
    expect(canEditLines(PM, 'Closed')).toBe(false);
    expect(canEditLines(READER, 'Draft')).toBe(false);
  });
});

describe('budgetCapability — status helpers', () => {
  test('isBudgetEditable matches Draft + Active', () => {
    expect(isBudgetEditable('Draft')).toBe(true);
    expect(isBudgetEditable('Active')).toBe(true);
    expect(isBudgetEditable('Locked')).toBe(false);
    expect(isBudgetEditable('Closed')).toBe(false);
    expect(isBudgetEditable('Superseded')).toBe(false);
  });

  test('isCostCodeMutable only Draft', () => {
    expect(isCostCodeMutable('Draft')).toBe(true);
    expect(isCostCodeMutable('Active')).toBe(false);
    expect(isCostCodeMutable('Locked')).toBe(false);
  });
});

describe('budgetCapability — refresh-attention admin gate', () => {
  test('canRefreshAttention requires budgets.admin', () => {
    expect(canRefreshAttention(ADMIN)).toBe(true);
    expect(canRefreshAttention(PM)).toBe(false);
    expect(canRefreshAttention(null)).toBe(false);
  });
});
