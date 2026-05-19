/**
 * NotesCell — inline-editable cell for line.notes (Q7).
 *
 * Chat 23 R3.1 — v2 supports inline edit ONLY on the Notes column.
 * All other field edits route through LineDrawer. The full Notes
 * inline-edit behaviour (debounced autosave + optimistic + audit)
 * lands in R5; for R3.x this is a click-to-edit textarea wired to
 * the provided `onSave` callback.
 */
import { useEffect, useRef, useState } from 'react';
import { Textarea } from '@/components/ui/textarea';

export function NotesCell({ value, canEdit, onSave }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? '');
  const ref = useRef(null);

  useEffect(() => {
    if (!editing) setDraft(value ?? '');
  }, [value, editing]);

  function commit() {
    setEditing(false);
    const next = draft.trim() === '' ? null : draft;
    if (next === (value ?? null)) return;
    onSave?.(next);
  }

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
    return (
      <Textarea
        ref={ref}
        autoFocus
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            commit();
          } else if (e.key === 'Escape') {
            e.preventDefault();
            setDraft(value ?? '');
            setEditing(false);
          }
        }}
        className="min-h-[2rem] text-sm"
        data-testid="notes-cell-input"
      />
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
