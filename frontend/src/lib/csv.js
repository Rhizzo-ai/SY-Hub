/**
 * Chat 23 §R7.4 — Inline RFC-4180 CSV builder.
 *
 * Locked decision (Build Pack A): NO papaparse dependency. This is the
 * canonical 5-line `toCsv` exactly as the Build Pack specifies.
 *
 * Quoting rule: a cell is quoted iff it contains `,`, `"`, `\n`, or `\r`.
 * Inner double-quotes are escaped by doubling (`"` → `""`). Row separator
 * is CRLF (`\r\n`) per RFC-4180.
 *
 *   toCsv([[1, 'a,b', 'c"d'], [2, '', null]])
 *     → `1,"a,b","c""d"\r\n2,,`
 */
export function toCsv(rows) {
  return rows.map((row) =>
    row.map((cell) => {
      const s = String(cell ?? '');
      return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    }).join(','),
  ).join('\r\n');
}

/**
 * Trigger a browser download for `text` as `filename`. Uses Blob + an
 * ephemeral object URL — no third-party dependency. Returns the
 * filename actually used (caller can log it).
 */
export function downloadCsv(text, filename) {
  const blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  return filename;
}
