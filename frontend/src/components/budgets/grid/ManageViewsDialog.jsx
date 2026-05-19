/**
 * ManageViewsDialog — Chat 23 R6.4.
 *
 * Lists saved views for the current surface and allows rename + delete.
 * Rename = "delete + create" against the backend because the R1.4
 * endpoints don't expose a PUT-name path (only PUT-payload-by-name).
 * That's fine: rename is uncommon enough that the slight non-atomicity
 * is acceptable; if the create half fails, we restore the original
 * via a follow-up create using the captured payload.
 *
 * Delete asks confirmation. No double-step "Confirm?" button here
 * because the dialog itself is already a confirmation surface.
 */
import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Pencil, Trash2 } from 'lucide-react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  useUserPreferences, useUpdateSavedView, useDeleteSavedView,
  useCreateSavedView,
} from '@/hooks/userPreferences';

const SURFACE = 'budgets.grid.v2';

function Row({ view, onRename, onDelete, busy }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(view.name);

  function submitRename() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === view.name) {
      setEditing(false);
      setDraft(view.name);
      return;
    }
    onRename(view, trimmed);
    setEditing(false);
  }

  return (
    <li
      className="flex items-center justify-between gap-2 border-b border-slate-100 py-2"
      data-testid={`bg2-mv-row-${view.name}`}
    >
      {editing ? (
        <Input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') { e.preventDefault(); submitRename(); }
            else if (e.key === 'Escape') {
              setDraft(view.name); setEditing(false);
            }
          }}
          onBlur={submitRename}
          className="h-7 text-sm"
          maxLength={128}
          data-testid={`bg2-mv-rename-input-${view.name}`}
        />
      ) : (
        <span
          className="flex-1 truncate text-sm text-slate-800"
          title={view.name}
        >
          {view.name}
        </span>
      )}
      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => setEditing(true)}
          disabled={busy || editing}
          aria-label={`Rename ${view.name}`}
          className="rounded p-1 text-slate-500 hover:bg-slate-100 hover:text-slate-700 disabled:opacity-40"
          data-testid={`bg2-mv-rename-${view.name}`}
        >
          <Pencil size={14} />
        </button>
        <button
          type="button"
          onClick={() => onDelete(view)}
          disabled={busy}
          aria-label={`Delete ${view.name}`}
          className="rounded p-1 text-slate-500 hover:bg-rose-50 hover:text-rose-600 disabled:opacity-40"
          data-testid={`bg2-mv-delete-${view.name}`}
        >
          <Trash2 size={14} />
        </button>
      </div>
    </li>
  );
}

export function ManageViewsDialog({ open, onOpenChange }) {
  const { data, isLoading } = useUserPreferences(SURFACE, { enabled: !!open });
  const createMut = useCreateSavedView(SURFACE);
  const updateMut = useUpdateSavedView(SURFACE);
  const deleteMut = useDeleteSavedView(SURFACE);

  // Rename = delete-then-create. Capture the source payload BEFORE
  // delete so we can recreate if the second half fails.
  async function rename(view, newName) {
    const payload = view.payload;
    try {
      await deleteMut.mutateAsync(view.name);
      await createMut.mutateAsync({ name: newName, payload });
      toast.success(`Renamed to "${newName}"`);
    } catch (err) {
      // Recovery: re-create the original. If THAT fails too the user
      // loses the view; surface a clearer toast.
      try {
        await createMut.mutateAsync({ name: view.name, payload });
        toast.error('Rename failed', {
          description: 'Original view restored.',
        });
      } catch {
        toast.error('Rename failed', {
          description:
            `View "${view.name}" was lost during rename — recreate manually.`,
        });
      }
      throw err;
    }
  }

  function doDelete(view) {
    deleteMut.mutate(view.name, {
      onSuccess: () => toast.success(`Deleted "${view.name}"`),
      onError: (err) => toast.error('Delete failed', {
        description: err?.message ?? 'Network error.',
      }),
    });
  }

  const busy = createMut.isPending || updateMut.isPending || deleteMut.isPending;
  const views = data?.views ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="bg2-manage-views-dialog">
        <DialogHeader>
          <DialogTitle>Manage saved views</DialogTitle>
          <DialogDescription>
            Rename or delete your saved budget-grid views.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="py-6 text-center text-sm text-slate-500"
               data-testid="bg2-mv-loading">
            Loading…
          </div>
        ) : views.length === 0 ? (
          <div className="py-6 text-center text-sm text-slate-500"
               data-testid="bg2-mv-empty">
            No saved views yet. Save one from the Views menu first.
          </div>
        ) : (
          <ul className="max-h-72 overflow-y-auto"
              data-testid="bg2-mv-list">
            {views.map((view) => (
              <Row
                key={view.id}
                view={view}
                onRename={rename}
                onDelete={doDelete}
                busy={busy}
              />
            ))}
          </ul>
        )}
        <DialogFooter>
          <Button type="button" onClick={() => onOpenChange?.(false)}
                  data-testid="bg2-mv-close">
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
