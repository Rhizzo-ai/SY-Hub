/**
 * <FolderNode/> — Build Pack 2.7-DOCS-FE §R4.2.
 *
 * Pure presentational tree node. The parent (`DocumentFolderView`)
 * owns ALL state — this component receives callbacks. Recursive: a
 * node renders its children by mapping over `node.children` and
 * rendering more `<FolderNode/>` at depth+1.
 *
 * Drop-target: when `dragDocId` is set and the user holds the cursor
 * over the row, the row glows. On drop the parent's `onDropDoc(folderId,
 * docId)` is invoked. The doc id comes from `dataTransfer` first, then
 * the in-memory `dragDocId` fallback (jsdom doesn't always honour
 * dataTransfer).
 */
import React, { useState } from 'react';
import {
  ChevronDown, ChevronRight, Folder, FolderOpen, MoreHorizontal,
} from 'lucide-react';

export const DRAG_DOC_MIME = 'application/x-sy-doc-id';

export default function FolderNode({
  node, depth, expanded, selectedId, dragDocId,
  onToggle, onSelect, onDropDoc,
  canCreateFold, canEditFold, canMove,
  onNewSubfolder, onRename, onMove, onArchive, onUnarchive,
}) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const isExpanded = expanded.has(node.id);
  const hasChildren = (node.children?.length ?? 0) > 0;
  const isSelected = selectedId === node.id;
  const canDrop = canMove && !!dragDocId && !node.is_archived;

  const rowClass = [
    'group flex items-center gap-1 px-1 py-1 rounded text-sm cursor-pointer',
    isSelected ? 'bg-sy-teal-50 text-sy-teal-800 font-medium' : 'hover:bg-sy-grey-50',
    isDragOver && canDrop ? 'ring-2 ring-sy-orange-500 bg-sy-orange-50' : '',
    node.is_archived ? 'opacity-60' : '',
  ].filter(Boolean).join(' ');

  return (
    <div data-testid={`folder-node-${node.id}`}>
      <div
        className={rowClass}
        style={{ paddingLeft: `${depth * 12 + 4}px` }}
        onClick={() => onSelect(node.id)}
        onDragOver={(e) => {
          if (!canDrop) return;
          e.preventDefault();
          if (!isDragOver) setIsDragOver(true);
        }}
        onDragEnter={(e) => {
          if (!canDrop) return;
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={(e) => {
          if (!canDrop) return;
          e.preventDefault();
          setIsDragOver(false);
          const id = e.dataTransfer?.getData?.(DRAG_DOC_MIME) || dragDocId;
          if (id) onDropDoc(node.id, id);
        }}
        data-testid={`folder-node-row-${node.id}`}
        data-dragover={isDragOver ? 'true' : 'false'}
        data-selected={isSelected ? 'true' : 'false'}
      >
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onToggle(node.id); }}
          className="w-5 h-5 flex items-center justify-center text-sy-grey-500"
          data-testid={`folder-node-toggle-${node.id}`}
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
        >
          {hasChildren && isExpanded && <ChevronDown className="w-3.5 h-3.5" />}
          {hasChildren && !isExpanded && <ChevronRight className="w-3.5 h-3.5" />}
          {!hasChildren && <span className="w-3.5 h-3.5 inline-block" />}
        </button>
        {isExpanded && hasChildren ? <FolderOpen className="w-4 h-4" /> : <Folder className="w-4 h-4" />}
        <span className="flex-1 truncate" data-testid={`folder-node-name-${node.id}`}>
          {node.name}
        </span>
        <span className="text-xs text-slate-500" data-testid={`folder-node-count-${node.id}`}>
          {node.file_count ?? 0}
        </span>

        {(canCreateFold || canEditFold) && !node.is_archived && (
          <FolderNodeMenu
            node={node}
            menuOpen={menuOpen}
            setMenuOpen={setMenuOpen}
            canCreateFold={canCreateFold}
            canEditFold={canEditFold}
            canMove={canMove}
            onNewSubfolder={onNewSubfolder}
            onRename={onRename}
            onMove={onMove}
            onArchive={onArchive}
          />
        )}
        {canEditFold && node.is_archived && (
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); onUnarchive(node); }}
            className="text-xs underline text-sy-teal-700"
            data-testid={`folder-node-unarchive-${node.id}`}
          >
            Restore
          </button>
        )}
      </div>

      {isExpanded && hasChildren && (
        <div>
          {node.children.map((c) => (
            <FolderNode
              key={c.id}
              node={c}
              depth={depth + 1}
              expanded={expanded}
              selectedId={selectedId}
              dragDocId={dragDocId}
              onToggle={onToggle}
              onSelect={onSelect}
              onDropDoc={onDropDoc}
              canCreateFold={canCreateFold}
              canEditFold={canEditFold}
              canMove={canMove}
              onNewSubfolder={onNewSubfolder}
              onRename={onRename}
              onMove={onMove}
              onArchive={onArchive}
              onUnarchive={onUnarchive}
            />
          ))}
        </div>
      )}
    </div>
  );
}


function FolderNodeMenu({
  node, menuOpen, setMenuOpen,
  canCreateFold, canEditFold, canMove,
  onNewSubfolder, onRename, onMove, onArchive,
}) {
  return (
    <div className="relative">
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setMenuOpen((v) => !v); }}
        className="opacity-0 group-hover:opacity-100 text-sy-grey-600 hover:text-sy-grey-800 px-1"
        aria-label="Folder actions"
        data-testid={`folder-node-menu-${node.id}`}
      >
        <MoreHorizontal className="w-4 h-4" />
      </button>
      {menuOpen && (
        <div
          className="absolute right-0 top-6 z-10 bg-white border border-sy-grey-300 rounded shadow-md text-xs min-w-[140px]"
          onClick={(e) => e.stopPropagation()}
          role="menu"
          data-testid={`folder-node-menu-pop-${node.id}`}
        >
          {canCreateFold && (
            <button
              type="button"
              className="block w-full text-left px-3 py-1.5 hover:bg-sy-grey-50"
              onClick={() => { setMenuOpen(false); onNewSubfolder(node); }}
              data-testid={`folder-node-new-sub-${node.id}`}
            >
              New subfolder
            </button>
          )}
          {canEditFold && (
            <button
              type="button"
              className="block w-full text-left px-3 py-1.5 hover:bg-sy-grey-50"
              onClick={() => { setMenuOpen(false); onRename(node); }}
              data-testid={`folder-node-rename-${node.id}`}
            >
              Rename
            </button>
          )}
          {canMove && canEditFold && (
            <button
              type="button"
              className="block w-full text-left px-3 py-1.5 hover:bg-sy-grey-50"
              onClick={() => { setMenuOpen(false); onMove(node); }}
              data-testid={`folder-node-move-${node.id}`}
            >
              Move…
            </button>
          )}
          {canEditFold && (
            <button
              type="button"
              className="block w-full text-left px-3 py-1.5 hover:bg-sy-grey-50 text-red-700"
              onClick={() => { setMenuOpen(false); onArchive(node); }}
              data-testid={`folder-node-archive-${node.id}`}
            >
              Archive
            </button>
          )}
        </div>
      )}
    </div>
  );
}
