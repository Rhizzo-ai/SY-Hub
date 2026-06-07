/**
 * <FolderPicker/> — Build Pack 2.7-DOCS-FE §R4.5/§R4.7.
 *
 * Flat indented radio list of folders for the move dialogs. The
 * `excludeId` prop skips the folder + its descendants — used when
 * moving a folder so a user cannot pick the folder being moved or
 * one of its descendants (the backend would 422 anyway; this is the
 * client-side hint).
 *
 * The synthetic top entry maps to `value === null` and is what the
 * caller wires up via `labelTop` ("Move to root (no parent)" for
 * folder-move, "Unfiled (no folder)" for doc-move).
 */
import React, { useMemo } from 'react';
import { Folder } from 'lucide-react';

export default function FolderPicker({
  tree, value, onChange, testid, excludeId, labelTop,
}) {
  const items = useMemo(() => {
    const out = [];
    const walk = (list, depth) => {
      for (const n of list) {
        if (excludeId && n.id === excludeId) continue;
        out.push({ node: n, depth });
        if (n.children?.length) walk(n.children, depth + 1);
      }
    };
    walk(tree || [], 0);
    return out;
  }, [tree, excludeId]);

  return (
    <div
      data-testid={testid}
      className="border border-sy-grey-300 rounded max-h-64 overflow-auto"
    >
      <label className="flex items-center gap-2 px-2 py-1.5 text-sm cursor-pointer hover:bg-sy-grey-50">
        <input
          type="radio"
          name={`${testid}-radio`}
          checked={value === null}
          onChange={() => onChange(null)}
          data-testid={`${testid}-root`}
        />
        <span className="text-sy-grey-700">{labelTop}</span>
      </label>
      {items.length === 0 && (
        <div className="px-2 py-2 text-xs text-sy-grey-500">
          No folders available.
        </div>
      )}
      {items.map(({ node, depth }) => (
        <label
          key={node.id}
          className="flex items-center gap-2 px-2 py-1.5 text-sm cursor-pointer hover:bg-sy-grey-50"
          style={{ paddingLeft: `${depth * 14 + 8}px` }}
        >
          <input
            type="radio"
            name={`${testid}-radio`}
            checked={value === node.id}
            onChange={() => onChange(node.id)}
            data-testid={`${testid}-${node.id}`}
          />
          <Folder className="w-3.5 h-3.5 text-sy-grey-500" />
          <span className={node.is_archived ? 'opacity-60' : ''}>
            {node.name}
            {node.is_archived && (
              <span className="ml-2 text-[10px] uppercase tracking-widest text-slate-400">
                Archived
              </span>
            )}
          </span>
        </label>
      ))}
    </div>
  );
}
