import React, { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Loader2, ShieldCheck, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";

export default function ResetPassword() {
    const [sp] = useSearchParams();
    const nav = useNavigate();
    const token = sp.get("token") || "";
    const [pwNew, setPwNew] = useState("");
    const [pwConfirm, setPwConfirm] = useState("");
    const [mfaCode, setMfaCode] = useState("");
    const [busy, setBusy] = useState(false);
    const [done, setDone] = useState(false);
    const [historySize, setHistorySize] = useState(5);

    useEffect(() => {
        api.get("/auth/password-policy").then((r) => setHistorySize(r.data.history_size)).catch(() => {});
    }, []);

    const checks = [
        { code: "length", label: "At least 12 characters", ok: pwNew.length >= 12 },
        { code: "uppercase", label: "At least one uppercase letter (A–Z)", ok: /[A-Z]/.test(pwNew) },
        { code: "lowercase", label: "At least one lowercase letter (a–z)", ok: /[a-z]/.test(pwNew) },
        { code: "number", label: "At least one number (0–9)", ok: /[0-9]/.test(pwNew) },
        { code: "symbol", label: "At least one symbol (! @ # $ % ^ & *)", ok: /[^A-Za-z0-9]/.test(pwNew) },
    ];
    const allOk = checks.every((c) => c.ok) && pwNew === pwConfirm && pwNew.length >= 12;

    const onSubmit = async (e) => {
        e.preventDefault();
        if (!allOk) return;
        setBusy(true);
        try {
            const body = { token, new_password: pwNew };
            if (mfaCode.trim()) body.mfa_code = mfaCode.trim();
            await api.post("/auth/password-reset/complete", body);
            setDone(true);
        } catch (err) {
            const detail = err.friendlyMessage || "Reset failed";
            if (/two-factor/i.test(detail) && !mfaCode) {
                // Force-show MFA field if server says MFA required.
                toast.info("Two-factor code required — enter it below.");
            } else {
                toast.error(detail);
            }
        } finally {
            setBusy(false);
        }
    };

    if (!token) {
        return (
            <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
                <div className="bg-white rounded-lg shadow-xl p-8 max-w-md">
                    <h1 className="font-heading text-xl font-bold">Invalid reset link</h1>
                    <p className="text-sm text-slate-600 mt-2">This page requires a reset token. If your link is missing one, request a new reset from <Link to="/forgot-password" className="underline">forgot password</Link>.</p>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6" data-testid="reset-password-page">
            <div className="w-full max-w-md bg-white rounded-lg shadow-xl overflow-hidden">
                <header className="px-8 py-6 border-b border-slate-200 bg-slate-50/60">
                    <div className="flex items-center gap-3">
                        <div className="h-10 w-10 rounded-md bg-slate-900 text-white flex items-center justify-center">
                            <ShieldCheck size={18} />
                        </div>
                        <div>
                            <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                                Account recovery
                            </div>
                            <h1 className="font-heading text-xl font-bold text-slate-900">Set a new password</h1>
                        </div>
                    </div>
                </header>
                {!done ? (
                    <form onSubmit={onSubmit} className="p-8 space-y-5" data-testid="reset-password-form">
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">New password</label>
                            <Input type="password" autoFocus value={pwNew} onChange={(e) => setPwNew(e.target.value)} className="bg-white h-10" data-testid="reset-pw-new" required />
                            <ul className="mt-2 space-y-1" data-testid="reset-password-rules">
                                {checks.map((c) => (
                                    <li
                                        key={c.code}
                                        className={`text-xs flex items-center gap-1.5 ${c.ok ? "text-emerald-700" : "text-slate-500"}`}
                                        data-testid={`reset-rule-${c.code}-${c.ok ? "ok" : "fail"}`}
                                    >
                                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${c.ok ? "bg-emerald-500" : "bg-slate-300"}`} />
                                        {c.label}
                                    </li>
                                ))}
                                <li className="text-xs flex items-center gap-1.5 text-slate-500">
                                    <span className="inline-block h-1.5 w-1.5 rounded-full bg-slate-300" />
                                    Cannot match any of your last {historySize} passwords
                                </li>
                            </ul>
                        </div>
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Confirm new password</label>
                            <Input type="password" value={pwConfirm} onChange={(e) => setPwConfirm(e.target.value)} className="bg-white h-10" data-testid="reset-pw-confirm" required />
                            {pwConfirm && pwConfirm !== pwNew && (
                                <p className="text-[11px] text-rose-600 mt-1">Passwords do not match.</p>
                            )}
                        </div>
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                                Two-factor code <span className="normal-case text-slate-400">(only if MFA is enabled)</span>
                            </label>
                            <Input
                                value={mfaCode}
                                onChange={(e) => setMfaCode(e.target.value)}
                                className="bg-white h-10 mono tracking-[0.4em] text-center"
                                placeholder="123456"
                                maxLength={8}
                                inputMode="numeric"
                                data-testid="reset-mfa-code"
                            />
                        </div>
                        <div className="flex justify-between pt-4 border-t border-slate-200">
                            <Link to="/login" className="text-xs text-slate-600 underline decoration-dotted self-center">Cancel</Link>
                            <Button type="submit" disabled={busy || !allOk} className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="reset-submit">
                                {busy && <Loader2 size={14} className="animate-spin mr-1.5" />} Set new password
                            </Button>
                        </div>
                    </form>
                ) : (
                    <div className="p-8 space-y-4" data-testid="reset-done">
                        <div className="flex items-start gap-2 text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md p-3 text-sm">
                            <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                            Password updated. All previous sessions have been signed out.
                        </div>
                        <Button onClick={() => nav("/login")} className="w-full bg-slate-900 hover:bg-slate-800 text-white" data-testid="reset-go-login">
                            Go to sign in
                        </Button>
                    </div>
                )}
            </div>
        </div>
    );
}
