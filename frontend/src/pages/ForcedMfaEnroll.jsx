import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, LogOut, Loader2, CheckCircle2, Copy } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, setAuthToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

/**
 * Full-screen gate shown to users who hold an MFA-enforced role
 * (super_admin / director / finance) and have not yet enrolled.
 *
 * Only reachable while the authenticated token is `mfa_pending`.
 * Completing enrolment swaps the token for a full `access` token
 * and routes the user into the app.
 */
export default function ForcedMfaEnroll() {
    const { me, refresh, logout } = useAuth();
    const nav = useNavigate();
    const [step, setStep] = useState("intro"); // intro | scan | codes
    const [secret, setSecret] = useState("");
    const [qr, setQr] = useState("");
    const [code, setCode] = useState("");
    const [backupCodes, setBackupCodes] = useState([]);
    const [busy, setBusy] = useState(false);
    const [copied, setCopied] = useState(false);

    const roleName = me?.enforced_role_name || "your role";

    const onStart = async () => {
        setBusy(true);
        try {
            const r = await api.post("/auth/mfa/enroll/start");
            setSecret(r.data.secret);
            setQr(r.data.qr_data_uri);
            setStep("scan");
        } catch (e) {
            toast.error(e.friendlyMessage || "Failed to start MFA enrolment");
        } finally {
            setBusy(false);
        }
    };

    const onVerify = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const r = await api.post("/auth/mfa/enroll/confirm", {
                secret,
                code: code.trim(),
            });
            setBackupCodes(r.data.backup_codes);
            // Swap mfa_pending → full access token.
            if (r.data.access_token) setAuthToken(r.data.access_token);
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

    const finish = async () => {
        await refresh();
        nav("/entities", { replace: true });
    };

    const onSignOut = async () => {
        await logout();
        nav("/login");
    };

    return (
        <div
            className="min-h-screen bg-slate-950 flex items-center justify-center p-6"
            data-testid="forced-mfa-gate"
        >
            <div className="w-full max-w-xl bg-white rounded-lg shadow-xl overflow-hidden">
                <header className="px-8 py-6 border-b border-slate-200 bg-slate-50/60">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-md bg-slate-900 text-white flex items-center justify-center">
                            <ShieldCheck size={18} />
                        </div>
                        <div>
                            <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                                Required · Two-Factor Authentication
                            </div>
                            <h1 className="font-heading text-xl font-bold text-slate-900">
                                Set up two-factor authentication
                            </h1>
                        </div>
                    </div>
                </header>

                {step === "intro" && (
                    <div className="p-8 space-y-5" data-testid="forced-mfa-intro">
                        <p className="text-sm text-slate-700 leading-relaxed">
                            Your role (<span className="font-semibold" data-testid="forced-mfa-role">{roleName}</span>) requires
                            two-factor authentication for security. This protects SY Homes financial data,
                            your Xero connection, and your ability to approve transactions.
                        </p>
                        <p className="text-sm text-slate-700 leading-relaxed">
                            Setup takes 2 minutes. You'll need an authenticator app on your phone —
                            Google Authenticator, Microsoft Authenticator, Authy, 1Password, or Bitwarden all work.
                        </p>
                        <p className="text-sm text-slate-700 leading-relaxed">
                            You'll also be given 10 single-use backup codes to store safely, so losing your
                            phone never locks you out of the platform.
                        </p>

                        <div className="flex flex-wrap gap-2 pt-4 border-t border-slate-200">
                            <Button
                                onClick={onStart}
                                disabled={busy}
                                className="bg-slate-900 hover:bg-slate-800 text-white"
                                data-testid="forced-mfa-setup-btn"
                            >
                                {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />}
                                <ShieldCheck size={14} className="mr-1.5" /> Set up 2FA
                            </Button>
                            <Button
                                variant="outline"
                                onClick={onSignOut}
                                data-testid="forced-mfa-logout-btn"
                            >
                                <LogOut size={14} className="mr-1.5" /> Log out
                            </Button>
                        </div>
                    </div>
                )}

                {step === "scan" && (
                    <form onSubmit={onVerify} className="p-8 space-y-5" data-testid="forced-mfa-scan">
                        <div className="flex flex-col items-center gap-3">
                            <img
                                src={qr}
                                alt="MFA QR code"
                                className="w-48 h-48 border border-slate-200 rounded-md bg-white"
                                data-testid="forced-mfa-qr"
                            />
                            <details className="text-xs text-slate-500 w-full">
                                <summary className="cursor-pointer select-none">
                                    Can't scan? Enter secret manually
                                </summary>
                                <div
                                    className="mt-2 mono text-slate-700 bg-slate-50 p-2 rounded border border-slate-200 break-all"
                                    data-testid="forced-mfa-secret"
                                >
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
                                data-testid="forced-mfa-code"
                                required
                            />
                        </div>
                        <div className="flex justify-between gap-2 pt-4 border-t border-slate-200">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={onSignOut}
                                data-testid="forced-mfa-logout-mid"
                            >
                                <LogOut size={14} className="mr-1.5" /> Log out
                            </Button>
                            <Button
                                type="submit"
                                disabled={busy || code.length !== 6}
                                className="bg-slate-900 hover:bg-slate-800 text-white"
                                data-testid="forced-mfa-verify-btn"
                            >
                                {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Verify & Enable
                            </Button>
                        </div>
                    </form>
                )}

                {step === "codes" && (
                    <div className="p-8 space-y-4" data-testid="forced-mfa-codes">
                        <div className="flex items-start gap-2 text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md p-3 text-sm">
                            <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                            <span>
                                Two-factor authentication enabled. Save these backup codes now —
                                they're shown only once.
                            </span>
                        </div>
                        <ul
                            className="grid grid-cols-2 gap-2 bg-slate-50 border border-slate-200 rounded-md p-4"
                            data-testid="forced-mfa-codes-list"
                        >
                            {backupCodes.map((c) => (
                                <li key={c} className="mono text-sm text-slate-800 tracking-wider">
                                    {c}
                                </li>
                            ))}
                        </ul>
                        <Button
                            type="button"
                            variant="outline"
                            onClick={copyAll}
                            className="w-full"
                            data-testid="forced-mfa-copy"
                        >
                            <Copy size={14} className="mr-1.5" /> {copied ? "Copied!" : "Copy all to clipboard"}
                        </Button>
                        <p className="text-xs text-slate-500">
                            Each code can be used exactly once if you lose access to your authenticator app.
                        </p>
                        <div className="flex justify-end pt-4 border-t border-slate-200">
                            <Button
                                onClick={finish}
                                className="bg-slate-900 hover:bg-slate-800 text-white"
                                data-testid="forced-mfa-continue"
                            >
                                <ShieldCheck size={14} className="mr-1.5" /> Continue to platform
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
