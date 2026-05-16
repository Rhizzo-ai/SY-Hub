/**
 * CreateActualSheet (Chat 19B §R2 stub; full impl in §R3.3).
 *
 * On desktop, this is the side-Sheet entry from the ActualsList page.
 * §R3 fills in the form body, attachments uploader, and BudgetLinePicker.
 * For now it renders nothing (no-op when closed) so §R2 STOP gate 2 can
 * verify the list page renders without crash.
 */
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet';

export function CreateActualSheet({ open, onOpenChange, projectId: _projectId }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full max-w-xl">
        <SheetHeader>
          <SheetTitle>Create actual</SheetTitle>
        </SheetHeader>
        <div
          data-testid="create-actual-sheet-placeholder"
          className="mt-6 rounded-md border border-dashed border-slate-300 p-6 text-sm text-slate-500"
        >
          The create form lands in §R3 — stub for §R2 STOP gate 2.
        </div>
      </SheetContent>
    </Sheet>
  );
}
