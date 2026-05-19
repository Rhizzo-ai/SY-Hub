/**
 * SaveViewDialog — Chat 23 R6.3.
 *
 * Capture a new saved-view name + persist the current grid state
 * payload to /api/v1/me/preferences/{surface}/views.
 *
 * Acceptance:
 *   - Name 1-128 chars (matches the backend `min_length=1 max_length=128`
 *     from R1.4 SavedViewIn schema).
 *   - Duplicate name → 409 from backend → toast.error("Name already
 *     in use"), keep dialog open.
 *   - Successful create → toast.success, close dialog, parent's
 *     onSaved callback fires (BudgetGridToolbar refreshes the
 *     ViewPresetsDropdown via the React Query cache).
 */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useCreateSavedView } from '@/hooks/userPreferences';

const SURFACE = 'budgets.grid.v2';
const MAX_NAME = 128;

export function SaveViewDialog({ open, onOpenChange, payload, onSaved }) {
  const [name, setName] = useState('');
  const createMut = useCreateSavedView(SURFACE);

  function reset() {
    setName('');
  }
  function close() {
    reset();
    onOpenChange?.(false);
  }
  function submit(e) {
    e.preventDefault();
    const trimmed = name.trim();
    if (trimmed.length < 1 || trimmed.length > MAX_NAME) return;
    createMut.mutate(
      { name: trimmed, payload },
      {
        onSuccess: (newView) => {
          toast.success(`View "${newView.name}" saved`);
          onSaved?.(newView);
          close();
        },
        onError: (err) => {
          const status = err?.response?.status;
          if (status === 409) {
            toast.error('Name already in use', {
              description: 'Pick a different name for this saved view.',
            });
            return;
          }
          toast.error('View did not save', {
            description: err?.message ?? 'Network error.',
          });
        },
      },
    );
  }

  return (
    <Dialog open={open} onOpenChange={(v) => v ? onOpenChange?.(v) : close()}>
      <DialogContent data-testid="bg2-save-view-dialog">
        <DialogHeader>
          <DialogTitle>Save view</DialogTitle>
          <DialogDescription>
            Name this view so you can reapply this filter / sort / column
            set later.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <label className="block text-sm">
            <span className="text-slate-700">View name</span>
            <Input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Q2 review"
              maxLength={MAX_NAME}
              className="mt-1"
              data-testid="bg2-save-view-name"
            />
          </label>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={close}
                    data-testid="bg2-save-view-cancel">
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                createMut.isPending
                || name.trim().length < 1
                || name.trim().length > MAX_NAME
              }
              data-testid="bg2-save-view-submit"
            >
              {createMut.isPending ? 'Saving…' : 'Save view'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
