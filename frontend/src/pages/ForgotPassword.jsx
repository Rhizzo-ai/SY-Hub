import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, ShieldCheck, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

/**
 * Public — /forgot-password. Always shows the same confirmation message
 * so the backend's "we never leak whether this email exists" guarantee
 * stays intact.
 */
export default function ForgotPassword() {
    const [email, setEmail] = useState("");
    const [sent, setSent] = useState(false);
    const [busy, setBusy] = useState(false);

    const onSubmit = async (e) => {
        e.preventDefault();
        setBusy(true);
        try {
            await api.post("/auth/password-reset/request", { email: email.trim().toLowerCase() });
        } catch (_) {
            // Server always returns 200 — ignoring any transport error is fine.
        } finally {
            setBusy(false);
            setSent(true);
        }
    };

    return (
        <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6" data-testid="forgot-password-page">
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
                            <h1 className="font-heading text-xl font-bold text-slate-900">Reset your password</h1>
                        </div>
                    </div>
                </header>

                {!sent ? (
                    <form onSubmit={onSubmit} className="p-8 space-y-5" data-testid="forgot-password-form">
                        <p className="text-sm text-slate-600">
                            Enter your SY Homes email. If an account exists, we'll send a reset link that's
                            valid for one hour.
                        </p>
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">
                                Email
                            </label>
                            <Input
                                type="email"
                                autoFocus
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                className="bg-white h-10 mono"
                                data-testid="forgot-password-email"
                                required
                            />
                        </div>
                        <div className="flex items-center justify-between pt-2 border-t border-slate-200 pt-4">
                            <Link to="/login" className="text-xs text-slate-600 inline-flex items-center gap-1" data-testid="forgot-back-link">
                                <ArrowLeft size={12} /> Back to sign in
                            </Link>
                            <Button type="submit" disabled={busy || !email} className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="forgot-password-submit">
                                {busy && <Loader2 size={14} className="animate-spin mr-1.5" />} Send reset link
                            </Button>
                        </div>
                    </form>
                ) : (
                    <div className="p-8 space-y-4" data-testid="forgot-password-sent">
                        <div className="text-emerald-800 bg-emerald-50 border border-emerald-200 rounded-md p-3 text-sm">
                            If <span className="mono">{email}</span> matches an active SY Homes account, a reset link is on its way.
                        </div>
                        <p className="text-sm text-slate-600">
                            The link expires in 1 hour. Check your inbox — and spam folder, just in case.
                            If you don't receive anything, speak to your administrator.
                        </p>
                        <div className="pt-4 border-t border-slate-200">
                            <Link to="/login">
                                <Button variant="outline" data-testid="forgot-return-login">Back to sign in</Button>
                            </Link>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
