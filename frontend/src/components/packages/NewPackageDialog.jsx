/**
 * NewPackageDialog — B88 Pack 3 §7. Modal launcher for creating a
 * package on a chosen project + budget.
 *
 * Backend contract:
 *   POST /v1/projects/{project_id}/packages
 *     { budget_id, title, kind: 'labour'|'materials', description? }
 *
 * Validations (server-authoritative, mirrored here for UX):
 *   - title required, kind ∈ {labour, materials}, budget_id non-terminal.
 *   - Server rejects against a terminal (Closed) budget → surfaced.
 */
import React, { useEffect, useState } from 'react';
import { X } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { api } from '@/lib/api';
import { listProjectBudgets } from '@/lib/api/budgets';
import { createPackage } from '@/lib/api/packages';
import { errorMessage } from '@/components/packages/packagesHelpers';

const TEAL = '#0F6A7A';

export default function NewPackageDialog({
  onClose, onCreated, onCreateError,
}) {
  const [projects, setProjects] = useState([]);
  const [projectId, setProjectId] = useState('');
  const [budgets, setBudgets] = useState([]);
  const [budgetId, setBudgetId] = useState('');
  const [title, setTitle] = useState('');
  const [kind, setKind] = useState('materials');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [inlineError, setInlineError] = useState(null);
  const [loadError, setLoadError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const r = await api.get('/projects', {
          params: { limit: 200, archived: false },
        });
        if (!cancelled) {
          const items = (r.data?.items || r.data || []).filter(
            (p) => !p.archived,
          );
          setProjects(items);
        }
      } catch (err) {
        if (!cancelled) setLoadError(errorMessage(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Load budgets when project changes.
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!projectId) {
      setBudgets([]);
      setBudgetId('');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const data = await listProjectBudgets(projectId);
        if (cancelled) return;
        // Only allow non-terminal budgets for new packages.
        const items = (data?.items || data || []).filter(
          (b) => b.status === 'Active' || b.status === 'Draft',
        );
        setBudgets(items);
        if (items.length === 1) setBudgetId(items[0].id);
      } catch (err) {
        if (!cancelled) setLoadError(errorMessage(err));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const canSubmit =
    projectId && budgetId && title.trim().length > 0 && !busy;

  const onSubmit = async (e) => {
    e?.preventDefault();
    if (!canSubmit) return;
    setBusy(true);
    setInlineError(null);
    try {
      const pkg = await createPackage(projectId, {
        budget_id: budgetId,
        title: title.trim(),
        kind,
        description: description.trim() || undefined,
      });
      onCreated?.(pkg);
    } catch (err) {
      const msg = errorMessage(err);
      setInlineError(msg);
      onCreateError?.(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 px-4"
      role="dialog"
      aria-modal="true"
      data-testid="new-package-dialog"
    >
      <form
        onSubmit={onSubmit}
        className="w-full max-w-lg rounded-lg bg-white shadow-xl"
      >
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h2
            className="font-heading text-lg font-semibold"
            style={{ color: TEAL }}
          >
            New package
          </h2>
          <button
            type="button"
            onClick={onClose}
            data-testid="new-package-close"
            className="rounded p-1 text-slate-500 hover:bg-slate-100"
          >
            <X size={18} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          {loadError && (
            <div
              className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"
              role="alert"
              data-testid="new-package-load-error"
            >
              {loadError}
            </div>
          )}
          <label className="block">
            <span className="block text-xs font-medium text-slate-600">
              Project
            </span>
            <select
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              data-testid="new-package-project"
              required
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
            >
              <option value="">— select —</option>
              {projects.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-slate-600">
              Budget
            </span>
            <select
              value={budgetId}
              onChange={(e) => setBudgetId(e.target.value)}
              data-testid="new-package-budget"
              required
              disabled={!projectId || budgets.length === 0}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100"
            >
              <option value="">— select —</option>
              {budgets.map((b) => (
                <option key={b.id} value={b.id}>
                  {b.label || b.title || `Budget v${b.version}`}{' '}
                  ({b.status})
                </option>
              ))}
            </select>
            {projectId && budgets.length === 0 && (
              <span className="mt-1 block text-xs text-slate-500">
                No non-terminal budgets on this project.
              </span>
            )}
          </label>
          <label className="block">
            <span className="block text-xs font-medium text-slate-600">
              Title
            </span>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
              data-testid="new-package-title"
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
              placeholder="e.g. Roofing materials — Block A"
            />
          </label>
          <fieldset>
            <legend className="block text-xs font-medium text-slate-600">
              Kind
            </legend>
            <div className="mt-1 flex gap-3">
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="kind"
                  value="materials"
                  checked={kind === 'materials'}
                  onChange={() => setKind('materials')}
                  data-testid="new-package-kind-materials"
                />
                Materials (PO)
              </label>
              <label className="flex items-center gap-1.5 text-sm">
                <input
                  type="radio"
                  name="kind"
                  value="labour"
                  checked={kind === 'labour'}
                  onChange={() => setKind('labour')}
                  data-testid="new-package-kind-labour"
                />
                Labour (Subcontract)
              </label>
            </div>
          </fieldset>
          <label className="block">
            <span className="block text-xs font-medium text-slate-600">
              Description (optional)
            </span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              data-testid="new-package-description"
              rows={2}
              className="mt-1 w-full rounded border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          {inlineError && (
            <div
              className="rounded border border-rose-200 bg-rose-50 p-3 text-sm text-rose-900"
              role="alert"
              data-testid="new-package-error"
            >
              {inlineError}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            data-testid="new-package-cancel"
          >
            Cancel
          </Button>
          <Button
            type="submit"
            disabled={!canSubmit}
            data-testid="new-package-submit"
            style={{ backgroundColor: TEAL, color: 'white' }}
          >
            {busy ? 'Creating…' : 'Create package'}
          </Button>
        </div>
      </form>
    </div>
  );
}
