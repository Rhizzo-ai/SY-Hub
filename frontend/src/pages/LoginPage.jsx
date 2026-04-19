import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Building2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";

export default function LoginPage() {
    const { login, submitMfa, state } = useAuth();
    const nav = useNavigate();
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [mfaChallenge, setMfaChallenge] = useState(null);
    const [mfaCode, setMfaCode] = useState("");
    const [useBackup, setUseBackup] = useState(false);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (state === "authed" || state === "pending_mfa") {
            nav(state === "pending_mfa" ? "/" : "/entities", { replace: true });
        }
    }, [state, nav]);

    if (state === "authed" || state === "pending_mfa") {
        return null;
    }

    const onSubmit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            const res = await login(email.trim().toLowerCase(), password);
            if (res.mfa_required) {
                setMfaChallenge(res.challenge);
                toast.info("Enter your 6-digit code from your authenticator app");
            } else if (res.mfa_enrollment_required) {
                // AuthContext state flips to `pending_mfa`; effect above will redirect.
                nav("/", { replace: true });
            } else {
                nav("/entities", { replace: true });
            }
        } catch (e) {
            toast.error(e.friendlyMessage || "Login failed");
        } finally {
            setBusy(false);
        }
    };

    const onMfa = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            await submitMfa(mfaChallenge, mfaCode.trim(), useBackup);
            nav("/entities", { replace: true });
        } catch (e) {
            toast.error(e.friendlyMessage || "MFA verification failed");
        } finally {
            setBusy(false);
        }
    };

    return (
        <div
            className="min-h-screen grid lg:grid-cols-[1fr_520px] bg-slate-950"
            data-testid="login-page"
        >
            <div className="hidden lg:flex items-end p-12 relative overflow-hidden bg-slate-900">
                <div
                    className="absolute inset-0 bg-cover bg-center opacity-30"
                    style={{
                        backgroundImage:
                            "url('https://images.pexels.com/photos/3318582/pexels-photo-3318582.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940')",
                    }}
                />
                <div className="relative z-10 text-slate-100 max-w-md">
                    <div className="flex items-center gap-3 mb-8">
                        <div className="h-10 w-10 rounded-md bg-white text-slate-900 flex items-center justify-center font-heading font-bold">
                            SY
                        </div>
                        <div>
                            <div className="font-heading font-semibold text-lg">SY Homes</div>
                            <div className="text-xs uppercase tracking-[0.2em] text-slate-300">
                                Operations Platform
                            </div>
                        </div>
                    </div>
                    <h1 className="font-heading text-3xl font-bold leading-tight">
                        A single system of record<br />for development operations.
                    </h1>
                    <p className="mt-4 text-slate-300 text-sm leading-relaxed">
                        Entities · Users · Projects · Cost Codes · Appraisals · Budgets · Cash Flow · Programme · Documents · Compliance · Xero.
                    </p>
                    <div className="mt-10 pt-6 border-t border-slate-700 text-xs text-slate-400 mono">
                        Phase 1.2 · Users, Roles & Permissions
                    </div>
                </div>
            </div>

            <div className="flex flex-col justify-center p-10 bg-white">
                <div className="max-w-sm w-full mx-auto">
                    <div className="flex items-center gap-2 mb-8 lg:hidden">
                        <Building2 size={20} />
                        <span className="font-heading font-semibold">SY Homes Operations</span>
                    </div>
                    <h2 className="font-heading text-2xl font-bold text-slate-900 mb-1">
                        {mfaChallenge ? "Two-factor verification" : "Sign in"}
                    </h2>
                    <p className="text-sm text-slate-500 mb-8">
                        {mfaChallenge
                            ? "Enter the 6-digit code from your authenticator app, or a backup code."
                            : "Use your SY Homes operations account."}
                    </p>

                    {!mfaChallenge ? (
                        <form onSubmit={onSubmit} className="space-y-5" data-testid="login-form">
                            <div>
                                <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                                    Email
                                </label>
                                <Input
                                    type="email"
                                    autoFocus
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    className="bg-white h-10"
                                    data-testid="login-email"
                                    required
                                />
                            </div>
                            <div>
                                <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                                    Password
                                </label>
                                <Input
                                    type="password"
                                    value={password}
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="bg-white h-10"
                                    data-testid="login-password"
                                    required
                                />
                            </div>
                            <Button
                                type="submit"
                                disabled={busy}
                                className="w-full h-10 bg-slate-900 hover:bg-slate-800"
                                data-testid="login-submit"
                            >
                                {busy ? <Loader2 size={14} className="animate-spin mr-2" /> : null}
                                Sign in
                            </Button>
                        </form>
                    ) : (
                        <form onSubmit={onMfa} className="space-y-5" data-testid="mfa-form">
                            <div>
                                <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                                    {useBackup ? "Backup code" : "TOTP code"}
                                </label>
                                <Input
                                    autoFocus
                                    value={mfaCode}
                                    onChange={(e) => setMfaCode(e.target.value)}
                                    className="bg-white h-10 mono"
                                    placeholder={useBackup ? "XXXXX-XXXXX" : "123456"}
                                    data-testid="mfa-code"
                                    required
                                />
                            </div>
                            <div className="text-xs">
                                <button
                                    type="button"
                                    className="text-slate-600 underline decoration-dotted"
                                    onClick={() => setUseBackup(!useBackup)}
                                    data-testid="mfa-toggle-backup"
                                >
                                    {useBackup ? "Use TOTP code instead" : "Use a backup code instead"}
                                </button>
                            </div>
                            <Button
                                type="submit"
                                disabled={busy}
                                className="w-full h-10 bg-slate-900 hover:bg-slate-800"
                                data-testid="mfa-submit"
                            >
                                {busy ? <Loader2 size={14} className="animate-spin mr-2" /> : null}
                                Verify
                            </Button>
                        </form>
                    )}

                    <div className="mt-10 pt-6 border-t border-slate-200 text-xs text-slate-400">
                        © SY Homes · Phase 1 · All actions are audit-logged.
                    </div>
                </div>
            </div>
        </div>
    );
}
