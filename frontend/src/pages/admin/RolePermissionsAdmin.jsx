/**
 * RolePermissionsAdmin — B83 §R4 (Chat 52). Route: /admin/roles.
 *
 * Buildertrend-style role × permission matrix:
 *  - Rows grouped by resource (collapsible), alphabetical by action.
 *  - Columns = roles ordered by priority then name.
 *  - Sticky header row AND sticky first column (~136 rows × 10+ cols).
 *  - super_admin column: always ticked, fully locked (D3).
 *  - Sensitive permissions: orange dot + consequence tooltip (D8/D10).
 *  - Draft + review-modal + ONE transactional batch save (D9).
 *  - Custom-role lifecycle: create / rename / delete (D5/D6).
 *  - roles.view → read-only render; roles.admin → edit affordances.
 *
 * Error discipline (Chat 51 lesson): every mutation surfaces failures
 * visibly (toast + inline) and preserves the user's draft. No silent
 * onError anywhere on this page.
 */
import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import {
  ShieldCheck, Lock, ChevronDown, ChevronRight, MoreVertical,
  Plus, RotateCcw, AlertTriangle, Info,
} from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  listRoles, getRole, listPermissions, saveRolePermissionsBatch,
  createRole, patchRole, deleteRole,
} from '@/lib/api/roles';
import RoleReviewModal from '@/components/admin/RoleReviewModal';
import {
  CreateRoleDialog, RenameRoleDialog, DeleteRoleDialog,
} from '@/components/admin/RoleLifecycleDialogs';
import { consequenceFor } from '@/components/admin/permissionConsequences';

const TEAL = '#0F6A7A';
const ORANGE = '#FC7827';
const GREY = '#CECECE';

export default function RolePermissionsAdmin() {
  const { me, hasPerm } = useAuth();
  const canView = hasPerm('roles.view') || me?.is_super_admin;
  const canEdit = hasPerm('roles.admin') || me?.is_super_admin;

  const [catalogue, setCatalogue] = useState([]);          // PermissionOut[]
  const [roles, setRoles] = useState([]);                  // RoleOut[]
  const [serverGrants, setServerGrants] = useState({});    // roleId -> Set(code)
  const [draftGrants, setDraftGrants] = useState({});      // roleId -> Set(code)
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);

  const [collapsed, setCollapsed] = useState(() => new Set());
  const [expandedDesc, setExpandedDesc] = useState(() => new Set());

  const [reviewOpen, setReviewOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState(null);  // RoleOut | null
  const [deleteTarget, setDeleteTarget] = useState(null);  // RoleOut | null

  const permsByCode = useMemo(
    () => Object.fromEntries(catalogue.map((p) => [p.code, p])),
    [catalogue],
  );

  const load = useCallback(async () => {
    try {
      const [perms, roleList] = await Promise.all([
        listPermissions(), listRoles(),
      ]);
      const details = await Promise.all(roleList.map((r) => getRole(r.id)));
      const grants = {};
      details.forEach((d) => {
        grants[d.id] = new Set(d.permissions.map((p) => p.code));
      });
      setCatalogue(perms);
      setRoles(roleList);
      setServerGrants(grants);
      setDraftGrants(Object.fromEntries(
        Object.entries(grants).map(([id, s]) => [id, new Set(s)]),
      ));
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Load failed';
      setLoadError(String(detail));
    } finally {
      setLoading(false);
    }
  }, []);

  // Async load-on-mount — same shape as AppraisalPage/AdminLoginHistory;
  // the sync setStates live inside the async callback, not the effect body.
  // Skipped entirely without roles.view (no point fetching a 403).
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => { if (canView) load(); }, [load, canView]);

  // ----- derived: groups + ordered roles + diffs -----

  const groups = useMemo(() => {
    const byResource = new Map();
    for (const p of catalogue) {
      if (!byResource.has(p.resource)) byResource.set(p.resource, []);
      byResource.get(p.resource).push(p);
    }
    const sorted = [...byResource.entries()]
      .sort(([a], [b]) => a.localeCompare(b));
    for (const [, list] of sorted) {
      list.sort((a, b) => a.action.localeCompare(b.action));
    }
    return sorted;
  }, [catalogue]);

  const orderedRoles = useMemo(
    () => [...roles].sort(
      (a, b) => (a.priority - b.priority) || a.name.localeCompare(b.name),
    ),
    [roles],
  );

  const diffs = useMemo(() => {
    const out = [];
    for (const role of orderedRoles) {
      if (role.code === 'super_admin') continue;
      const server = serverGrants[role.id];
      const draft = draftGrants[role.id];
      if (!server || !draft) continue;
      const adds = [...draft].filter((c) => !server.has(c)).sort();
      const removes = [...server].filter((c) => !draft.has(c)).sort();
      if (adds.length || removes.length) {
        out.push({ role, adds, removes, endsAtZero: draft.size === 0 });
      }
    }
    return out;
  }, [orderedRoles, serverGrants, draftGrants]);

  const totalChanges = diffs.reduce(
    (n, d) => n + d.adds.length + d.removes.length, 0,
  );

  // ----- interactions -----

  function toggleCell(role, code) {
    if (!canEdit || role.code === 'super_admin') return;
    setDraftGrants((prev) => {
      const next = { ...prev };
      const set = new Set(next[role.id] || []);
      if (set.has(code)) set.delete(code); else set.add(code);
      next[role.id] = set;
      return next;
    });
  }

  function toggleGroup(resource) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(resource)) next.delete(resource); else next.add(resource);
      return next;
    });
  }

  function toggleDesc(code) {
    setExpandedDesc((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code); else next.add(code);
      return next;
    });
  }

  function discardDraft() {
    setDraftGrants(Object.fromEntries(
      Object.entries(serverGrants).map(([id, s]) => [id, new Set(s)]),
    ));
    setSaveError(null);
    toast.info('Draft discarded — matrix reset to saved state.');
  }

  async function handleSave() {
    const changes = diffs.map((d) => ({
      role_id: d.role.id, add: d.adds, remove: d.removes,
    }));
    setSaving(true); setSaveError(null);
    try {
      const res = await saveRolePermissionsBatch(changes);
      const grants = { ...serverGrants };
      (res.updated || []).forEach((d) => {
        grants[d.id] = new Set(d.permissions.map((p) => p.code));
      });
      setServerGrants(grants);
      setDraftGrants(Object.fromEntries(
        Object.entries(grants).map(([id, s]) => [id, new Set(s)]),
      ));
      setReviewOpen(false);
      toast.success(`Saved — ${changes.length} role(s) updated.`);
    } catch (err) {
      // Visible everywhere; draft untouched (Chat 51 lesson — no silent onError).
      const detail = err?.response?.data?.detail || err?.message || 'Save failed';
      const msg = typeof detail === 'string' ? detail : JSON.stringify(detail);
      setSaveError(msg);
      toast.error(`Save failed — nothing was applied. ${msg}`);
    } finally {
      setSaving(false);
    }
  }

  async function handleCreateRole(values) {
    // Errors propagate to the dialog (inline) — toast here as well.
    try {
      const detail = await createRole(values);
      setRoles((prev) => [...prev, {
        id: detail.id, code: detail.code, name: detail.name,
        description: detail.description, is_system_role: detail.is_system_role,
        priority: detail.priority,
        permission_count: detail.permissions.length,
        user_count: detail.user_count,
      }]);
      const set = new Set(detail.permissions.map((p) => p.code));
      setServerGrants((prev) => ({ ...prev, [detail.id]: set }));
      setDraftGrants((prev) => ({ ...prev, [detail.id]: new Set(set) }));
      toast.success(`Role “${detail.name}” created with ${detail.permissions.length} standard permissions.`);
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Create failed';
      toast.error(`Create failed: ${msg}`);
      throw err;
    }
  }

  async function handleRenameRole(values) {
    try {
      const detail = await patchRole(renameTarget.id, values);
      setRoles((prev) => prev.map((r) => (r.id === detail.id
        ? { ...r, name: detail.name, description: detail.description }
        : r)));
      toast.success(`Role renamed to “${detail.name}”.`);
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Rename failed';
      toast.error(`Rename failed: ${msg}`);
      throw err;
    }
  }

  async function handleDeleteRole() {
    try {
      await deleteRole(deleteTarget.id);
      setRoles((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      setServerGrants((prev) => {
        const next = { ...prev }; delete next[deleteTarget.id]; return next;
      });
      setDraftGrants((prev) => {
        const next = { ...prev }; delete next[deleteTarget.id]; return next;
      });
      toast.success(`Role “${deleteTarget.name}” deleted.`);
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || 'Delete failed';
      toast.error(`Delete failed: ${msg}`);
      throw err;
    }
  }

  // ----- guards -----

  if (!canView) {
    return (
      <div className="rounded-lg border border-slate-200 bg-white p-10 text-center" data-testid="roles-admin-forbidden">
        <ShieldCheck size={28} className="mx-auto text-slate-300 mb-3" />
        <div className="text-slate-700 font-medium">You do not have permission to view roles.</div>
        <div className="text-sm text-slate-500 mt-1">Requires <span className="font-mono">roles.view</span>.</div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="p-10 text-center text-slate-500" data-testid="roles-admin-loading">
        Loading the permission matrix…
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="rounded-lg border border-rose-200 bg-rose-50 p-8 text-center" data-testid="roles-admin-load-error" role="alert">
        <AlertTriangle size={24} className="mx-auto text-rose-500 mb-2" />
        <div className="text-rose-800 font-medium">Could not load the permission matrix</div>
        <div className="text-sm text-rose-700 mt-1">{loadError}</div>
        <Button
          variant="outline" className="mt-4"
          onClick={() => { setLoading(true); setLoadError(null); load(); }}
          data-testid="roles-admin-retry"
        >
          <RotateCcw size={14} className="mr-1.5" /> Retry
        </Button>
      </div>
    );
  }

  // ----- render -----

  return (
    <div data-testid="role-permissions-admin">
      <div className="flex items-start justify-between mb-6 gap-4 flex-wrap">
        <div>
          <h1 className="font-heading text-2xl font-bold text-slate-900">
            Role Permissions
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            Grant and revoke permissions per role. Operator edits here are
            permanent — re-seeds never undo them.
            {!canEdit && (
              <span className="ml-2 inline-flex items-center gap-1 text-xs uppercase tracking-widest text-slate-400 font-semibold" data-testid="read-only-badge">
                <Lock size={11} /> read-only
              </span>
            )}
          </p>
        </div>
        {canEdit && (
          <Button
            onClick={() => setCreateOpen(true)}
            className="bg-[#0F6A7A] hover:bg-[#0c5563] text-white"
            data-testid="new-role-btn"
          >
            <Plus size={15} className="mr-1.5" /> New role
          </Button>
        )}
      </div>

      <div className="overflow-auto max-h-[68vh] rounded-lg border border-slate-200 bg-white relative" data-testid="matrix-scroll">
        <table className="border-collapse w-max min-w-full text-sm" data-testid="matrix-table">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-30 bg-white border-b border-r border-slate-200 px-4 py-3 text-left min-w-[260px] font-semibold text-slate-700">
                Permission
              </th>
              {orderedRoles.map((role) => {
                const isSA = role.code === 'super_admin';
                const isCustom = !role.is_system_role;
                return (
                  <th
                    key={role.id}
                    className={`sticky top-0 z-20 border-b border-slate-200 px-3 py-3 text-center min-w-[110px] align-bottom ${isSA ? 'bg-[#CECECE]/30' : 'bg-white'}`}
                    data-testid={`role-col-${role.code}`}
                  >
                    <div className="flex items-center justify-center gap-1">
                      <span className="font-semibold text-slate-800 text-xs leading-tight">
                        {role.name}
                      </span>
                      {isSA && (
                        <span title="Super admin always has every permission" data-testid="super-admin-lock">
                          <Lock size={12} className="text-slate-500" />
                        </span>
                      )}
                      {isCustom && canEdit && (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <button
                              className="p-0.5 rounded hover:bg-slate-100 text-slate-400"
                              data-testid={`role-kebab-${role.code}`}
                              aria-label={`Manage ${role.name}`}
                            >
                              <MoreVertical size={13} />
                            </button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => setRenameTarget(role)}
                              data-testid={`role-rename-${role.code}`}
                            >
                              Rename
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="text-rose-700 focus:text-rose-800 focus:bg-rose-50"
                              onClick={() => setDeleteTarget(role)}
                              data-testid={`role-delete-${role.code}`}
                            >
                              Delete
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      )}
                    </div>
                    <div className="font-mono text-[10px] text-slate-400 mt-0.5">{role.code}</div>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {groups.map(([resource, perms]) => {
              const isCollapsed = collapsed.has(resource);
              return (
                <React.Fragment key={resource}>
                  <tr data-testid={`group-row-${resource}`}>
                    <td
                      className="sticky left-0 z-10 bg-slate-100 border-y border-r border-slate-200 px-3 py-2 cursor-pointer select-none"
                      onClick={() => toggleGroup(resource)}
                      data-testid={`group-toggle-${resource}`}
                    >
                      <span className="inline-flex items-center gap-1.5 font-semibold text-slate-700 text-xs uppercase tracking-wider">
                        {isCollapsed
                          ? <ChevronRight size={14} />
                          : <ChevronDown size={14} />}
                        {resource}
                        <span className="text-slate-400 font-normal normal-case">({perms.length})</span>
                      </span>
                    </td>
                    <td
                      colSpan={orderedRoles.length}
                      className="bg-slate-100 border-y border-slate-200"
                    />
                  </tr>
                  {!isCollapsed && perms.map((p) => {
                    const consequence = consequenceFor(p);
                    const tooltip = consequence
                      ? `${p.description} — ${consequence}`
                      : p.description;
                    return (
                      <tr key={p.code} className="hover:bg-slate-50/70" data-testid={`perm-row-${p.code}`}>
                        <td className="sticky left-0 z-10 bg-white border-b border-r border-slate-100 px-4 py-1.5">
                          <button
                            type="button"
                            className="flex items-center gap-1.5 text-left w-full"
                            title={tooltip}
                            onClick={() => toggleDesc(p.code)}
                            data-testid={`perm-label-${p.code}`}
                          >
                            {p.is_sensitive && (
                              <span
                                className="h-2 w-2 rounded-full shrink-0"
                                style={{ backgroundColor: ORANGE }}
                                data-testid={`sensitive-dot-${p.code}`}
                              />
                            )}
                            <span className="text-slate-800">{p.action}</span>
                            <span className="font-mono text-[10px] text-slate-400">{p.code}</span>
                            <Info size={11} className="text-slate-300 shrink-0 ml-auto" />
                          </button>
                          {expandedDesc.has(p.code) && (
                            <div className="mt-1 text-xs text-slate-500 max-w-[320px]" data-testid={`perm-desc-${p.code}`}>
                              {p.description}
                              {consequence && (
                                <div className="text-[#FC7827] mt-0.5">{consequence}</div>
                              )}
                            </div>
                          )}
                        </td>
                        {orderedRoles.map((role) => {
                          const isSA = role.code === 'super_admin';
                          const draft = draftGrants[role.id];
                          const server = serverGrants[role.id];
                          const checked = isSA ? true : Boolean(draft?.has(p.code));
                          const dirty = !isSA && server && draft
                            && server.has(p.code) !== draft.has(p.code);
                          return (
                            <td
                              key={role.id}
                              className={`border-b border-slate-100 text-center px-3 py-1.5 ${isSA ? 'bg-[#CECECE]/20' : ''} ${dirty ? 'bg-[#0F6A7A]/10' : ''}`}
                            >
                              <input
                                type="checkbox"
                                className="h-4 w-4 align-middle cursor-pointer disabled:cursor-not-allowed"
                                style={{ accentColor: isSA ? GREY : TEAL }}
                                checked={checked}
                                disabled={isSA || !canEdit}
                                onChange={() => toggleCell(role, p.code)}
                                aria-label={`${role.name}: ${p.code}`}
                                data-testid={`cell-${role.code}-${p.code}`}
                              />
                            </td>
                          );
                        })}
                      </tr>
                    );
                  })}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-xs text-slate-500 italic mt-3" data-testid="matrix-footnote">
        Custom roles do not automatically receive permissions added by future
        platform updates — review new permissions here after each update.
      </p>

      {totalChanges > 0 && (
        <div
          className="fixed bottom-0 left-64 right-0 max-sm:left-0 z-40 border-t border-slate-200 bg-white/95 backdrop-blur px-8 py-3 flex items-center justify-between gap-4"
          data-testid="pending-bar"
        >
          <span className="text-sm text-slate-800">
            <strong data-testid="pending-count">{totalChanges}</strong>{' '}
            change{totalChanges === 1 ? '' : 's'} pending across{' '}
            {diffs.length} role{diffs.length === 1 ? '' : 's'}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={discardDraft}
              disabled={saving}
              data-testid="discard-draft-btn"
            >
              Discard
            </Button>
            <Button
              onClick={() => { setSaveError(null); setReviewOpen(true); }}
              className="bg-[#0F6A7A] hover:bg-[#0c5563] text-white"
              data-testid="review-save-btn"
            >
              Review & Save
            </Button>
          </div>
        </div>
      )}

      {reviewOpen && (
        <RoleReviewModal
          open
          onOpenChange={(v) => { if (!saving) setReviewOpen(v); }}
          diffs={diffs}
          permsByCode={permsByCode}
          saving={saving}
          saveError={saveError}
          onConfirm={handleSave}
        />
      )}
      {createOpen && (
        <CreateRoleDialog
          open
          onOpenChange={setCreateOpen}
          onSubmit={handleCreateRole}
        />
      )}
      {Boolean(renameTarget) && (
        <RenameRoleDialog
          open
          onOpenChange={(v) => { if (!v) setRenameTarget(null); }}
          role={renameTarget}
          onSubmit={handleRenameRole}
        />
      )}
      {Boolean(deleteTarget) && (
        <DeleteRoleDialog
          open
          onOpenChange={(v) => { if (!v) setDeleteTarget(null); }}
          role={deleteTarget}
          onSubmit={handleDeleteRole}
        />
      )}
    </div>
  );
}
