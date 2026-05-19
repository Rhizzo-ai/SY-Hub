/**
 * POsSectionStub — Chat 23 R4.2.
 *
 * Empty-state placeholder for the per-line Purchase Orders panel.
 * Real PO list lands in Prompt 2.5 when the POs domain ships.
 */
export function POsSectionStub() {
  return (
    <div
      className="rounded border border-dashed border-slate-300 p-4 text-center text-sm text-slate-500"
      data-testid="bg2-pos-stub"
    >
      No POs raised yet — Purchase Orders ship in Prompt 2.5.
    </div>
  );
}
