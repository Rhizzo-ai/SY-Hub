/**
 * NumberPrefixManager — Chat 24 §R5.
 *
 * Per-project number-prefix configuration: PO + Bill tabs, with one
 * "default" row per (entity_type, document_type) and optional middle
 * variants. R5 ships a read-only view + suffix/middle/next_sequence
 * edit for users with pos.edit or suppliers.edit; CRUD operations
 * complete inline.
 */
import React, { useState } from 'react';
import { useParams } from 'react-router-dom';

import { useAuth } from '@/context/AuthContext';
import {
  usePrefixes, useCreatePrefix, usePatchPrefix,
} from '@/hooks/purchaseOrders';
import { canEditPrefixes, canViewPrefixes } from '@/lib/poCapability';

const TABS = ['PO', 'Bill'];

export default function NumberPrefixManager() {
  const { id: projectId } = useParams();
  const { user } = useAuth();
  const [tab, setTab] = useState('PO');
  const canEdit = canEditPrefixes(user);

  const { data, isLoading, isError } = usePrefixes(projectId, {
    params: { document_type: tab },
  });
  const createMut = useCreatePrefix(projectId);
  const patchMut = usePatchPrefix(projectId);

  if (!canViewPrefixes(user)) {
    return <div className="p-6 text-sm" data-testid="prefix-manager-forbidden">
      You do not have permission to view number prefixes.
    </div>;
  }

  return (
    <div className="p-6 space-y-4" data-testid="prefix-manager">
      <h1 className="text-xl font-semibold">Numbering</h1>

      <nav className="flex gap-2 border-b" data-testid="prefix-manager-tabs">
        {TABS.map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 text-sm ${tab === t ? 'border-b-2 border-sy-teal-600 font-semibold' : 'text-sy-grey-700'}`}
            data-testid={`prefix-manager-tab-${t}`}
          >{t}</button>
        ))}
      </nav>

      {isLoading && <div className="text-sm">Loading…</div>}
      {isError && <div className="text-sm text-red-600">Failed to load prefixes.</div>}

      {!isLoading && !isError && (
        <table className="w-full text-sm border-collapse" data-testid="prefix-manager-table">
          <thead>
            <tr className="text-left text-xs text-sy-grey-700 border-b">
              <th className="py-2 pr-2">Entity type</th>
              <th className="py-2 pr-2 w-32">Suffix</th>
              <th className="py-2 pr-2 w-32">Middle</th>
              <th className="py-2 pr-2 w-24 text-right">Next #</th>
              <th className="py-2 pr-2 w-20">Default</th>
              <th className="py-2 pr-2 w-24"></th>
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((row) => (
              <PrefixRow
                key={row.id}
                row={row} canEdit={canEdit}
                onSave={(body) => patchMut.mutateAsync({ id: row.id, body })}
              />
            ))}
            {canEdit && (
              <NewPrefixRow
                documentType={tab}
                onSave={(body) => createMut.mutateAsync(body)}
              />
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}


function PrefixRow({ row, canEdit, onSave }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState({
    suffix: row.suffix ?? '',
    middle: row.middle ?? '',
    next_sequence: row.next_sequence ?? 1,
  });
  return (
    <tr className="border-b last:border-0" data-testid={`prefix-row-${row.id}`}>
      <td className="py-1 pr-2">{row.entity_type}</td>
      <td className="py-1 pr-2">
        {editing ? (
          <input
            className="w-full px-1 py-0.5 border rounded text-sm font-mono"
            value={form.suffix}
            onChange={(e) => setForm({ ...form, suffix: e.target.value })}
            data-testid={`prefix-row-${row.id}-suffix-input`}
          />
        ) : (
          <span className="font-mono" data-testid={`prefix-row-${row.id}-suffix`}>{row.suffix ?? '—'}</span>
        )}
      </td>
      <td className="py-1 pr-2">
        {editing ? (
          <input
            className="w-full px-1 py-0.5 border rounded text-sm font-mono"
            value={form.middle ?? ''}
            onChange={(e) => setForm({ ...form, middle: e.target.value })}
            data-testid={`prefix-row-${row.id}-middle-input`}
          />
        ) : (
          <span className="font-mono">{row.middle ?? '—'}</span>
        )}
      </td>
      <td className="py-1 pr-2 text-right tabular-nums">
        {editing ? (
          <input
            type="number" min="1"
            className="w-full px-1 py-0.5 border rounded text-sm tabular-nums text-right"
            value={form.next_sequence}
            onChange={(e) => setForm({ ...form, next_sequence: Number(e.target.value) || 1 })}
            data-testid={`prefix-row-${row.id}-next-input`}
          />
        ) : row.next_sequence}
      </td>
      <td className="py-1 pr-2">
        {row.is_default ? <span className="text-sy-teal-700">★</span> : ''}
      </td>
      <td className="py-1 pr-2">
        {canEdit && !editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            className="text-xs underline text-sy-teal-700"
            data-testid={`prefix-row-${row.id}-edit-btn`}
          >Edit</button>
        )}
        {editing && (
          <div className="flex gap-1">
            <button
              type="button"
              onClick={async () => {
                await onSave({
                  suffix: form.suffix,
                  middle: form.middle || null,
                  next_sequence: Number(form.next_sequence),
                });
                setEditing(false);
              }}
              className="text-xs underline text-sy-teal-700"
              data-testid={`prefix-row-${row.id}-save-btn`}
            >Save</button>
            <button
              type="button" onClick={() => setEditing(false)}
              className="text-xs underline"
            >Cancel</button>
          </div>
        )}
      </td>
    </tr>
  );
}


function NewPrefixRow({ documentType, onSave }) {
  const [form, setForm] = useState({
    entity_type: 'Holding_Co', suffix: '', middle: '',
    next_sequence: 1, is_default: false,
  });
  const [pending, setPending] = useState(false);

  return (
    <tr className="border-b last:border-0" data-testid="prefix-row-new">
      <td className="py-1 pr-2">
        <select
          className="w-full px-1 py-0.5 border rounded text-sm"
          value={form.entity_type}
          onChange={(e) => setForm({ ...form, entity_type: e.target.value })}
          data-testid="prefix-row-new-entity-type"
        >
          <option>Holding_Co</option>
          <option>Project_Co</option>
        </select>
      </td>
      <td className="py-1 pr-2">
        <input
          className="w-full px-1 py-0.5 border rounded text-sm font-mono"
          value={form.suffix}
          onChange={(e) => setForm({ ...form, suffix: e.target.value })}
          placeholder="PO / BILL"
          data-testid="prefix-row-new-suffix"
        />
      </td>
      <td className="py-1 pr-2">
        <input
          className="w-full px-1 py-0.5 border rounded text-sm font-mono"
          value={form.middle}
          onChange={(e) => setForm({ ...form, middle: e.target.value })}
          placeholder="(optional)"
          data-testid="prefix-row-new-middle"
        />
      </td>
      <td className="py-1 pr-2 text-right">
        <input
          type="number" min="1"
          className="w-full px-1 py-0.5 border rounded text-sm tabular-nums text-right"
          value={form.next_sequence}
          onChange={(e) => setForm({ ...form, next_sequence: Number(e.target.value) || 1 })}
          data-testid="prefix-row-new-next"
        />
      </td>
      <td className="py-1 pr-2">
        <input
          type="checkbox"
          checked={form.is_default}
          onChange={(e) => setForm({ ...form, is_default: e.target.checked })}
          data-testid="prefix-row-new-default"
        />
      </td>
      <td className="py-1 pr-2">
        <button
          type="button"
          disabled={pending || !form.suffix}
          onClick={async () => {
            setPending(true);
            try {
              await onSave({
                document_type: documentType,
                entity_type: form.entity_type,
                suffix: form.suffix,
                middle: form.middle || null,
                next_sequence: Number(form.next_sequence),
                is_default: !!form.is_default,
              });
              setForm({ entity_type: 'Holding_Co', suffix: '', middle: '', next_sequence: 1, is_default: false });
            } finally { setPending(false); }
          }}
          className="text-xs underline text-sy-teal-700 disabled:opacity-50"
          data-testid="prefix-row-new-add-btn"
        >Add</button>
      </td>
    </tr>
  );
}
