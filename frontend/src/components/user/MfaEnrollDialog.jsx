import React, { useEffect, useState } from "react";
import { Copy, Loader2, ShieldCheck, CheckCircle2 } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";

/**
 * MfaEnrollDialog — three-step TOTP enrolment.
 *
 * Step 1: Start  → backend returns { secret, qr_data_uri }
 * Step 2: Verify → user enters 6-digit code from authenticator
 * Step 3: Codes  → backend returns 10 single-use backup codes (shown once)
 */
export default function MfaEnrollDialog({ onClose, onEnrolled }) {
    const [step, setStep] = useState("loading"); // loading | verify | codes
    const [secret, setSecret] = useState("");
    const [qr, setQr] = useState("");
    const [code, setCode] = useState("");
    const [backupCodes, setBackupCodes] = useState([]);
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);

    useEffect(() => {
        api.post("/auth/mfa/enroll/start")
            .then((r) => {
                setSecret(r.data.secret);
                setQr(r.data.qr_data_uri);
                setStep("verify");
            })
            .catch((e) => {
                toast.error(e.friendlyMessage || "Failed to start MFA enrolment");
                onClose();
            });
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const onConfirm = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const r = await api.post("/auth/mfa/enroll/confirm", { secret, code: code.trim() });
            setBackupCodes(r.data.backup_codes);
            setStep("codes");
        } catch (err) {
            toast.error(err.friendlyMessage || "Invalid code — re-scan and try again");
        } finally {
            setBusy(false);
        }
    };

    const copyAll = () => {
        navigator.clipboard.writeText(backupCodes.join("\n"));
        setCopied(true);
        toast.success("Backup codes copied");
    };

    const finish = () => {
        onEnrolled();
        onClose();
    };

    return (
        <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-center justify-center p-4" data-testid="mfa-enroll-dialog">
            <div className="bg-white rounded-lg shadow-xl max-w-md w-full overflow-hidden">
                <header className="px-6 py-4 border-b border-slate-200">
                    <h2 className="font-heading text-lg font-semibold text-slate-900">Enable Two-Factor Auth</h2>
                    <p className="text-xs text-slate-500 mt-1">Use any TOTP app: 1Password, Authy, Google Authenticator, Bitwarden, etc.</p>
                </header>

                {step === "loading" && (
                    <div className="p-10 text-center text-slate-500">
                        <Loader2 size={18} className="animate-spin inline mr-2" /> Generating secret…
                    </div>
                )}

                {step === "verify" && (
                    <form onSubmit={onConfirm} className="p-6 space-y-5" data-testid="mfa-enroll-verify">
                        <div className="flex flex-col items-center gap-3">
                            <img src={qr} alt="MFA QR code" className="w-48 h-48 border border-slate-200 rounded-md bg-white" data-testid="mfa-qr" />
                            <details className="text-xs text-slate-500 w-full">
                                <summary className="cursor-pointer select-none">Can't scan? Enter secret manually</summary>
                                <div className="mt-2 mono text-slate-700 bg-slate-50 p-2 rounded border border-slate-200 break-all" data-testid="mfa-manual-secret">
                                    {secret}
                                </div>
                            </details>
                        </div>
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                                Enter the 6-digit code from your app
                            </label>
                            <Input
                                autoFocus
                                value={code}
                                onChange={(e) => setCode(e.target.value)}
                                placeholder="123456"
                                className="mono text-center text-lg tracking-[0.4em] h-11"
                                maxLength={6}
                                inputMode="numeric"
                                data-testid="mfa-enroll-code"
                                required
                            />
                        </div>
                        <div className="flex justify-end gap-2 pt-4 border-t border-slate-200">
                            <Button type="button" variant="outline" onClick={onClose} data-testid="mfa-enroll-cancel">Cancel</Button>
                            <Button type="submit" disabled={busy || code.length !== 6} className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="mfa-enroll-submit">
                                {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Verify & Enable
                            </Button>
                        </div>
                    </form>
                )}

                {step === "codes" && (
                    <div className="p-6 space-y-4" data-testid="mfa-backup-codes">
                        <div className="flex items-start gap-2 text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md p-3 text-sm">
                            <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                            <span>Two-factor authentication enabled. Save these backup codes now — they're shown only once.</span>
                        </div>
                        <ul className="grid grid-cols-2 gap-2 bg-slate-50 border border-slate-200 rounded-md p-4" data-testid="mfa-backup-codes-list">
                            {backupCodes.map((c) => (
                                <li key={c} className="mono text-sm text-slate-800 tracking-wider">{c}</li>
                            ))}
                        </ul>
                        <Button type="button" variant="outline" onClick={copyAll} className="w-full" data-testid="mfa-copy-codes">
                            <Copy size={14} className="mr-1.5" /> {copied ? "Copied!" : "Copy all to clipboard"}
                        </Button>
                        <p className="text-xs text-slate-500">
                            Each code can be used exactly once if you lose access to your authenticator app.
                        </p>
                        <div className="flex justify-end pt-4 border-t border-slate-200">
                            <Button onClick={finish} className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="mfa-done">
                                <ShieldCheck size={14} className="mr-1.5" /> Done
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
