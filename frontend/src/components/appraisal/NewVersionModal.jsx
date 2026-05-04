/**
 * NewVersionModal — used by AppraisalPage header "New version" button.
 * Submit posts /new-version then navigates to the new appraisal id (F5).
 */
import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";

import { createNewVersion } from "@/lib/api";

const REVISION_REASONS = [
    "Cost_Update", "GDV_Update", "Scope_Change", "Programme_Change",
    "Finance_Restructure", "Planning_Outcome", "Decision_Feedback", "Other",
];


export default function NewVersionModal({ open, onClose, appraisalId }) {
    const navigate = useNavigate();
    const [reason, setReason] = useState("");
    const [summary, setSummary] = useState("");
    const [busy, setBusy] = useState(false);
    const [err, setErr] = useState(null);

    useEffect(() => {
        if (open) { setReason(""); setSummary(""); setBusy(false); setErr(null); }
    }, [open]);

    const trimmed = summary.trim();
    const valid = Boolean(reason) && trimmed.length >= 10;

    const submit = async (e) => {
        e?.preventDefault?.();
        if (!valid || busy) return;
        setBusy(true);
        setErr(null);
        try {
            const r = await createNewVersion(appraisalId, {
                revision_reason: reason,
                summary_of_changes: trimmed,
            });
            const newId = r.appraisal?.id;
            toast.success(`New version v${r.appraisal?.version_number} created.`);
            onClose();
            if (newId) navigate(`/appraisals/${newId}`);
        } catch (e2) {
            setErr(e2.friendlyMessage || "Failed to create new version");
        } finally { setBusy(false); }
    };

    const onKeyDown = (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit(e);
    };

    return (
        <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
            <DialogContent data-testid="new-version-modal">
                <form onSubmit={submit} onKeyDown={onKeyDown}>
                    <DialogHeader>
                        <DialogTitle>Create new version</DialogTitle>
                        <DialogDescription>
                            Forks the current Approved appraisal into a fresh editable Draft.
                            The current version is marked Superseded.
                        </DialogDescription>
                    </DialogHeader>
                    <div className="space-y-3 py-3">
                        <div>
                            <label className="text-xs uppercase tracking-wide font-semibold text-slate-600">
                                Revision reason
                            </label>
                            <Select value={reason} onValueChange={setReason}>
                                <SelectTrigger data-testid="new-version-reason-select" className="mt-1">
                                    <SelectValue placeholder="Pick a reason" />
                                </SelectTrigger>
                                <SelectContent>
                                    {REVISION_REASONS.map((r) => (
                                        <SelectItem key={r} value={r}>
                                            {r.replace(/_/g, " ")}
                                        </SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <label className="text-xs uppercase tracking-wide font-semibold text-slate-600">
                                Summary of changes (min 10 chars)
                            </label>
                            <Textarea value={summary} onChange={(e) => setSummary(e.target.value)}
                                      rows={4}
                                      placeholder="What's changing in this revision?"
                                      data-testid="new-version-summary-textarea"
                                      className="mt-1" />
                            <div className="text-[10px] text-slate-500 text-right">
                                {trimmed.length}/10 chars
                            </div>
                        </div>
                        {err && (
                            <div className="text-xs text-rose-700 bg-rose-50 border border-rose-200 p-2 rounded"
                                 data-testid="new-version-error">{err}</div>
                        )}
                    </div>
                    <DialogFooter>
                        <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
                            Cancel
                        </Button>
                        <Button type="submit" disabled={!valid || busy}
                                data-testid="new-version-submit">
                            {busy ? <><Loader2 className="w-3 h-3 animate-spin mr-1" />Creating…</> : "Create new version"}
                        </Button>
                    </DialogFooter>
                </form>
            </DialogContent>
        </Dialog>
    );
}
