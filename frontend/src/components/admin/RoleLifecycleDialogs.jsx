/**
 * Custom-role lifecycle dialogs — B83 §R4 (D5/D6).
 *
 * Controlled dialogs; the page owns the API call via `onSubmit` (async,
 * throws on failure). Every error is surfaced INLINE here AND as a toast
 * at the call site — no silent onError (Chat 51 lesson). User input is
 * preserved on failure. Dialogs go full-screen on small viewports.
 */
import React, { useState } from 'react';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { AlertTriangle } from 'lucide-react';

const FULLSCREEN_SM =
  'max-sm:h-full max-sm:max-h-full max-sm:w-full max-sm:max-w-full max-sm:rounded-none';

function InlineError({ children, testid }) {
  if (!children) return null;
  return (
    <div
      className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800"
      data-testid={testid}
      role="alert"
    >
      <AlertTriangle size={15} className="mt-0.5 shrink-0" />
      <span>{children}</span>
    </div>
  );
}

function validateName(name) {
  const trimmed = (name || '').trim();
  if (trimmed.length < 3 || trimmed.length > 100) {
    return 'Name must be 3\u2013100 characters.';
  }
  return null;
}

function validateDescription(desc) {
  const trimmed = (desc || '').trim();
  if (trimmed.length < 1 || trimmed.length > 500) {
    return 'Description is required (max 500 characters).';
  }
  return null;
}

export function CreateRoleDialog({ open, onOpenChange, onSubmit }) {
  // Mounted fresh on each open (parent renders conditionally) — initial
  // state IS the reset.
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const v = validateName(name) || validateDescription(description);
    if (v) { setError(v); return; }
    setBusy(true); setError(null);
    try {
      await onSubmit({ name: name.trim(), description: description.trim() });
      onOpenChange(false);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Create failed';
      setError(String(detail)); // inputs preserved
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={FULLSCREEN_SM} data-testid="create-role-dialog">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>New custom role</DialogTitle>
            <DialogDescription>
              New roles start with all standard permissions ticked — sensitive
              and destructive permissions (delete / admin / void) start
              unticked. Add those deliberately in the matrix afterwards.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="new-role-name">Role name</Label>
            <Input
              id="new-role-name" value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Quantity Surveyor"
              data-testid="create-role-name"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="new-role-desc">Description</Label>
            <Textarea
              id="new-role-desc" value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What this role is for"
              rows={3}
              data-testid="create-role-description"
            />
          </div>
          <InlineError testid="create-role-error">{error}</InlineError>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="submit" disabled={busy}
              className="bg-[#0F6A7A] hover:bg-[#0c5563] text-white"
              data-testid="create-role-submit"
            >
              {busy ? 'Creating\u2026' : 'Create role'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function RenameRoleDialog({ open, onOpenChange, role, onSubmit }) {
  // Mounted fresh per role (parent renders conditionally).
  const [name, setName] = useState(role?.name || '');
  const [description, setDescription] = useState(role?.description || '');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    const v = validateName(name) || validateDescription(description);
    if (v) { setError(v); return; }
    setBusy(true); setError(null);
    try {
      await onSubmit({ name: name.trim(), description: description.trim() });
      onOpenChange(false);
    } catch (err) {
      const detail = err?.response?.data?.detail || err?.message || 'Rename failed';
      setError(String(detail));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={FULLSCREEN_SM} data-testid="rename-role-dialog">
        <form onSubmit={handleSubmit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>Rename role</DialogTitle>
            <DialogDescription>
              The role code <span className="font-mono">{role?.code}</span> is
              immutable — renaming never changes it.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="rename-role-name">Role name</Label>
            <Input
              id="rename-role-name" value={name}
              onChange={(e) => setName(e.target.value)}
              data-testid="rename-role-name"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="rename-role-desc">Description</Label>
            <Textarea
              id="rename-role-desc" value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              data-testid="rename-role-description"
            />
          </div>
          <InlineError testid="rename-role-error">{error}</InlineError>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
              Cancel
            </Button>
            <Button
              type="submit" disabled={busy}
              className="bg-[#0F6A7A] hover:bg-[#0c5563] text-white"
              data-testid="rename-role-submit"
            >
              {busy ? 'Saving\u2026' : 'Save'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export function DeleteRoleDialog({ open, onOpenChange, role, onSubmit }) {
  // Mounted fresh on each open (parent renders conditionally).
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleDelete() {
    setBusy(true); setError(null);
    try {
      await onSubmit();
      onOpenChange(false);
    } catch (err) {
      // 409 guard messages (assignments / system role) shown VERBATIM.
      const detail = err?.response?.data?.detail || err?.message || 'Delete failed';
      setError(String(detail));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={FULLSCREEN_SM} data-testid="delete-role-dialog">
        <DialogHeader>
          <DialogTitle>Delete role</DialogTitle>
          <DialogDescription>
            Permanently delete <strong>{role?.name}</strong>
            {' '}(<span className="font-mono">{role?.code}</span>)? Its grants
            and overrides are removed with it. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <InlineError testid="delete-role-error">{error}</InlineError>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button
            type="button" variant="destructive" onClick={handleDelete} disabled={busy}
            data-testid="delete-role-confirm"
          >
            {busy ? 'Deleting\u2026' : 'Delete role'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
