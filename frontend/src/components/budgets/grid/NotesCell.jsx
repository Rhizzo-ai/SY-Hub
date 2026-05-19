/**
 * NotesCell — Chat 23 R5.
 *
 * Inline-editable cell for `budget_line.notes`. The ONLY inline-edit
 * column in BudgetGridV2 (Q7); all other field edits route through
 * LineDrawer.
 *
 * R5 acceptance contract:
 *   - Click to edit → textarea takes focus, autosizes via min-h.
 *   - Type → 600ms debounced PATCH fires once.
 *   - Rapid typing coalesces to a single PATCH (the debounce
 *     `clearTimeout` discards superseded keystrokes).
 *   - Enter (no modifier)  → commit immediately (cancel debounce, fire
 *                            now). Shift+Enter inserts a newline.
 *   - Escape               → revert draft to last-committed value AND
 *                            cancel any pending debounce; exit edit mode.
 *   - Blur                 → commit immediately if draft != committed.
 *   - Network failure      → revert via the existing usePatchBudgetLine
 *                            onError rollback path AND show a sonner toast.
 *   - maxLength 500        → enforced by the textarea attribute; the
 *                            soft counter at the right hint shows
 *                            count when draft.length >= 450.
 *   - Read-only path       → unchanged for users without `canEdit`.
 *
 * Mobile: this cell IS editable on mobile (one of the few mobile-
 * editable fields per Build Pack §R5). The desktop/mobile chooser
 * in BudgetGridV2.jsx routes mobile users to BudgetGridMobileReadOnly
 * which doesn't currently expose Notes; that's an R8 follow-up.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { Textarea } from '@/components/ui/textarea';
import { usePatchBudgetLine } from '@/hooks/budgets';

const DEBOUNCE_MS = 600;
const MAX_LENGTH = 500;

export function NotesCell({ value, canEdit, lineId, budgetId }) {
  const [editing, setEditing] = useState(false);
  // `draft` is the textarea's local state. `committedRef` tracks the
  // last value we successfully PATCH'd so Escape can revert AND we can
  // skip the debounce timer when no real change happened.
  const [draft, setDraft] = useState(value ?? '');
  const committedRef = useRef(value ?? '');
  const timerRef = useRef(null);
  const textareaRef = useRef(null);

  const patchMut = usePatchBudgetLine(budgetId);

  // Keep draft + committedRef in sync if the parent's `value` changes
  // (e.g. via a successful PATCH invalidating + refetching the budget).
  useEffect(() => {
    if (!editing) {
      const next = value ?? '';
      setDraft(next);
      committedRef.current = next;
    }
    // Intentionally exclude `editing` to avoid resyncing mid-edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  // Cancel any pending debounce on unmount.
  useEffect(() => () => clearTimeout(timerRef.current), []);

  const fire = useCallback((next) => {
    clearTimeout(timerRef.current);
    timerRef.current = null;
    const normalised = next.trim() === '' ? null : next;
    const prior = committedRef.current;
    if ((normalised ?? '') === (prior ?? '')) return;
    // Optimistic update is handled inside usePatchBudgetLine.onMutate.
    // Onerror it rolls back the cached row and we show a toast.
    committedRef.current = normalised ?? '';
    patchMut.mutate(
      { lineId, body: { notes: normalised } },
      {
        onError: (err) => {
          committedRef.current = prior;
          setDraft(prior ?? '');
          toast.error('Notes did not save', {
            description: err?.message ?? 'Network error — your edit was reverted.',
          });
        },
      },
    );
  }, [lineId, patchMut]);

  const scheduleDebouncedFire = useCallback((next) => {
    clearTimeout(timerRef.current);
    timerRef.current = setTimeout(() => fire(next), DEBOUNCE_MS);
  }, [fire]);

  const cancelEdit = useCallback(() => {
    clearTimeout(timerRef.current);
    timerRef.current = null;
    setDraft(committedRef.current ?? '');
    setEditing(false);
  }, []);

  if (!canEdit) {
    return (
      <span
        className="block max-w-xs truncate text-sm text-slate-700"
        title={value ?? ''}
        data-testid="notes-cell-readonly"
      >
        {value || <span className="text-slate-400">—</span>}
      </span>
    );
  }

  if (editing) {
    const showCounter = draft.length >= 450;
    return (
      <div className="relative">
        <Textarea
          ref={textareaRef}
          autoFocus
          value={draft}
          maxLength={MAX_LENGTH}
          onChange={(e) => {
            setDraft(e.target.value);
            scheduleDebouncedFire(e.target.value);
          }}
          onBlur={() => {
            // Fire immediately on blur (cancels debounce).
            fire(draft);
            setEditing(false);
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              fire(draft);
              setEditing(false);
            } else if (e.key === 'Escape') {
              e.preventDefault();
              cancelEdit();
            }
          }}
          className="min-h-[2rem] text-sm"
          data-testid="notes-cell-input"
        />
        {showCounter && (
          <span
            className="pointer-events-none absolute bottom-1 right-2 text-[10px] text-slate-500 tabular-nums"
            data-testid="notes-cell-counter"
          >
            {draft.length} / {MAX_LENGTH}
          </span>
        )}
      </div>
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      className="block max-w-xs truncate text-left text-sm text-slate-700 hover:text-sy-teal"
      data-testid="notes-cell-trigger"
    >
      {value || <em className="text-slate-400">Click to add notes</em>}
    </button>
  );
}
