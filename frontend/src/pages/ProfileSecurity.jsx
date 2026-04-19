import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Loader2, ShieldCheck, ShieldAlert, KeyRound, LogOut, Copy } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";
import MfaEnrollDialog from "@/components/user/MfaEnrollDialog";
import { toast } from "sonner";
import { formatDateTime } from "@/lib/format";

function Section({ title, description, children, testid }) {
    return (
        <section className="bg-white border border-slate-200 rounded-lg shadow-sm overflow-hidden" data-testid={testid}>
            <header className="px-6 py-4 border-b border-slate-200 bg-slate-50/60">
                <h2 className="font-heading text-sm font-semibold uppercase tracking-widest text-slate-900">{title}</h2>
                {description && <p className="text-xs text-slate-500 mt-1">{description}</p>}
            </header>
            <div className="p-6">{children}</div>
        </section>
    );
}

export default function ProfileSecurity() {
    const { me, refresh, logout } = useAuth();
    const nav = useNavigate();
    const [showEnroll, setShowEnroll] = useState(false);
    const [showDisableConfirm, setShowDisableConfirm] = useState(false);
    const [showRegenConfirm, setShowRegenConfirm] = useState(false);
    const [regenCodes, setRegenCodes] = useState(null);
    const [busy, setBusy] = useState(false);

    // Re-auth form state — disable MFA
    const [disablePassword, setDisablePassword] = useState("");
    // Re-auth form state — regenerate backup codes
    const [regenPassword, setRegenPassword] = useState("");
    const [regenTotp, setRegenTotp] = useState("");

    // Password-change form state
    const [pwCurrent, setPwCurrent] = useState("");
    const [pwNew, setPwNew] = useState("");
    const [pwConfirm, setPwConfirm] = useState("");

    useEffect(() => { refresh(); /* eslint-disable-next-line */ }, []);

    if (!me) return <div className="flex items-center gap-2 text-slate-500"><Loader2 size={14} className="animate-spin" /> Loading…</div>;

    const resetDisableForm = () => { setDisablePassword(""); };
    const resetRegenForm = () => { setRegenPassword(""); setRegenTotp(""); };

    const onDisableMfa = async (e) => {
        e.preventDefault();
        if (!disablePassword) { toast.error("Enter your current password"); return; }
        setBusy(true);
        try {
            await api.post("/auth/mfa/disable", { current_password: disablePassword });
            toast.success("Two-factor authentication disabled");
            setShowDisableConfirm(false);
            resetDisableForm();
            setRegenCodes(null);
            await refresh();
        } catch (e) {
            toast.error(e.friendlyMessage);
        } finally { setBusy(false); }
    };

    const onRegenerate = async (e) => {
        e.preventDefault();
        if (!regenPassword || regenTotp.trim().length < 6) {
            toast.error("Password and 6-digit TOTP code required");
            return;
        }
        setBusy(true);
        try {
            const r = await api.post("/auth/mfa/backup-codes/regenerate", {
                current_password: regenPassword,
                current_totp: regenTotp.trim(),
            });
            setRegenCodes(r.data.backup_codes);
            setShowRegenConfirm(false);
            resetRegenForm();
            await refresh();
        } catch (e) {
            toast.error(e.friendlyMessage);
        } finally { setBusy(false); }
    };

    const onChangePassword = async (e) => {
        e.preventDefault();
        if (pwNew !== pwConfirm) { toast.error("New passwords do not match"); return; }
        if (pwNew.length < 12) { toast.error("New password must be at least 12 characters"); return; }
        setBusy(true);
        try {
            await api.post("/auth/password/change", { current_password: pwCurrent, new_password: pwNew });
            toast.success("Password updated");
            setPwCurrent(""); setPwNew(""); setPwConfirm("");
            await refresh();
        } catch (e) {
            toast.error(e.friendlyMessage);
        } finally { setBusy(false); }
    };

    const onSignOut = async () => { await logout(); nav("/login"); };

    return (
        <div className="space-y-6 max-w-3xl" data-testid="profile-security-page">
            <header>
                <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">Profile · Security</div>
                <h1 className="font-heading text-3xl font-bold text-slate-900 mt-1">
                    {me.display_name}
                </h1>
                <div className="mt-1 text-sm text-slate-600 mono">{me.email}</div>
                <div className="mt-3 text-xs text-slate-500">
                    {me.last_login_at && <>Last login <span className="mono tabular">{formatDateTime(me.last_login_at)}</span></>}
                </div>
            </header>

            {me.mfa_enrollment_required && (
                <div className="rounded-md border border-amber-300 bg-amber-50 px-4 py-3 text-amber-900 text-sm flex items-start gap-2" data-testid="mfa-enforcement-banner">
                    <ShieldAlert size={16} className="mt-0.5 shrink-0" />
                    <div>
                        <div className="font-semibold">
                            Two-factor authentication is required for your role
                            {me.enforced_role_name ? ` (${me.enforced_role_name})` : ""}.
                        </div>
                        <p className="text-xs mt-1">Enrol now to continue accessing SY Homes. You'll be hard-blocked on your next login otherwise.</p>
                    </div>
                </div>
            )}

            <Section
                title="Two-factor authentication"
                description="Time-based one-time password (TOTP) — use any authenticator app."
                testid="section-mfa"
            >
                <div className="flex items-start justify-between gap-4">
                    <div className="flex items-start gap-3">
                        <div className={`h-10 w-10 rounded-md flex items-center justify-center ${me.mfa_enabled ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>
                            {me.mfa_enabled ? <ShieldCheck size={18} /> : <ShieldAlert size={18} />}
                        </div>
                        <div>
                            <div className="font-medium text-slate-900" data-testid="mfa-status-text">
                                {me.mfa_enabled ? `${me.mfa_method || "TOTP"} enrolled` : "Not enrolled"}
                            </div>
                            <div className="text-xs text-slate-500 mt-0.5">
                                {me.mfa_enabled
                                    ? `${me.mfa_backup_codes_remaining} backup codes remaining`
                                    : "Add a second factor to protect this account."}
                            </div>
                        </div>
                    </div>
                    <div className="flex gap-2">
                        {me.mfa_enabled ? (
                            <>
                                <Button variant="outline" onClick={() => { resetRegenForm(); setShowRegenConfirm(true); }} disabled={busy} data-testid="mfa-regenerate-button">
                                    <KeyRound size={14} className="mr-1.5" /> New backup codes
                                </Button>
                                <Button
                                    variant="outline"
                                    className="text-rose-700 border-rose-200 hover:bg-rose-50"
                                    onClick={() => { resetDisableForm(); setShowDisableConfirm(true); }}
                                    data-testid="mfa-disable-button"
                                >
                                    Disable MFA
                                </Button>
                            </>
                        ) : (
                            <Button onClick={() => setShowEnroll(true)} className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="mfa-enable-button">
                                <ShieldCheck size={14} className="mr-1.5" /> Enable MFA
                            </Button>
                        )}
                    </div>
                </div>

                {regenCodes && (
                    <div className="mt-6 pt-6 border-t border-slate-200" data-testid="mfa-new-codes">
                        <div className="text-sm font-medium text-slate-900 mb-2">
                            New backup codes — shown once. Your previous codes are now invalid.
                        </div>
                        <ul className="grid grid-cols-2 gap-2 bg-slate-50 border border-slate-200 rounded-md p-4">
                            {regenCodes.map((c) => <li key={c} className="mono text-sm text-slate-800 tracking-wider">{c}</li>)}
                        </ul>
                        <Button variant="outline" className="mt-3" onClick={() => { navigator.clipboard.writeText(regenCodes.join("\n")); toast.success("Copied"); }}>
                            <Copy size={14} className="mr-1.5" /> Copy all
                        </Button>
                    </div>
                )}
            </Section>

            <Section title="Change password" description="Minimum 12 characters. Cannot match your previous 5 passwords." testid="section-password">
                <form onSubmit={onChangePassword} className="space-y-4 max-w-md" data-testid="password-change-form">
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Current password</label>
                        <Input type="password" value={pwCurrent} onChange={(e) => setPwCurrent(e.target.value)} className="bg-white h-9" data-testid="pw-current" required />
                    </div>
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">New password</label>
                        <Input type="password" value={pwNew} onChange={(e) => setPwNew(e.target.value)} className="bg-white h-9" data-testid="pw-new" required />
                    </div>
                    <div>
                        <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Confirm new password</label>
                        <Input type="password" value={pwConfirm} onChange={(e) => setPwConfirm(e.target.value)} className="bg-white h-9" data-testid="pw-confirm" required />
                    </div>
                    <Button type="submit" disabled={busy} className="bg-slate-900 hover:bg-slate-800 text-white" data-testid="pw-submit">
                        {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Update password
                    </Button>
                    {me.password_changed_at && (
                        <p className="text-xs text-slate-500">Last changed {formatDateTime(me.password_changed_at)}</p>
                    )}
                </form>
            </Section>

            <Section title="Session" description="Sign out of this browser." testid="section-session">
                <Button variant="outline" onClick={onSignOut} data-testid="profile-signout">
                    <LogOut size={14} className="mr-1.5" /> Sign out
                </Button>
            </Section>

            {showEnroll && (
                <MfaEnrollDialog
                    onClose={() => setShowEnroll(false)}
                    onEnrolled={refresh}
                />
            )}

            {showDisableConfirm && (
                <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-center justify-center p-4" data-testid="mfa-disable-confirm">
                    <form
                        onSubmit={onDisableMfa}
                        className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 space-y-4"
                    >
                        <h3 className="font-heading text-lg font-semibold">Disable two-factor authentication?</h3>
                        <p className="text-sm text-slate-600">
                            Your account will be protected by password only. Any unused backup codes will be invalidated.
                            Enter your current password to continue.
                        </p>
                        {me.mfa_enrollment_required && (
                            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-md px-3 py-2">
                                MFA is required for your role — you'll be hard-blocked on next login until you re-enrol.
                            </div>
                        )}
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Current password</label>
                            <Input
                                type="password"
                                autoFocus
                                value={disablePassword}
                                onChange={(e) => setDisablePassword(e.target.value)}
                                className="bg-white h-9"
                                data-testid="mfa-disable-password"
                                required
                            />
                        </div>
                        <div className="flex justify-end gap-2 pt-4 border-t border-slate-200">
                            <Button type="button" variant="outline" onClick={() => { setShowDisableConfirm(false); resetDisableForm(); }} data-testid="mfa-disable-cancel">Cancel</Button>
                            <Button type="submit" disabled={busy || !disablePassword} className="bg-rose-600 hover:bg-rose-700 text-white" data-testid="mfa-disable-confirm-btn">
                                {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Disable MFA
                            </Button>
                        </div>
                    </form>
                </div>
            )}

            {showRegenConfirm && (
                <div className="fixed inset-0 bg-slate-900/60 z-50 flex items-center justify-center p-4" data-testid="mfa-regen-confirm">
                    <form
                        onSubmit={onRegenerate}
                        className="bg-white rounded-lg shadow-xl max-w-md w-full p-6 space-y-4"
                    >
                        <h3 className="font-heading text-lg font-semibold">Regenerate backup codes?</h3>
                        <p className="text-sm text-slate-600">
                            Your previous backup codes will be invalidated immediately. Confirm with your password
                            and a fresh 6-digit code from your authenticator app.
                        </p>
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Current password</label>
                            <Input
                                type="password"
                                autoFocus
                                value={regenPassword}
                                onChange={(e) => setRegenPassword(e.target.value)}
                                className="bg-white h-9"
                                data-testid="mfa-regen-password"
                                required
                            />
                        </div>
                        <div>
                            <label className="block text-[11px] uppercase tracking-widest font-semibold text-slate-500 mb-1.5">Authenticator code</label>
                            <Input
                                value={regenTotp}
                                onChange={(e) => setRegenTotp(e.target.value)}
                                className="bg-white h-10 mono text-center tracking-[0.4em]"
                                placeholder="123456"
                                maxLength={6}
                                inputMode="numeric"
                                data-testid="mfa-regen-totp"
                                required
                            />
                        </div>
                        <div className="flex justify-end gap-2 pt-4 border-t border-slate-200">
                            <Button type="button" variant="outline" onClick={() => { setShowRegenConfirm(false); resetRegenForm(); }} data-testid="mfa-regen-cancel">Cancel</Button>
                            <Button
                                type="submit"
                                disabled={busy || !regenPassword || regenTotp.trim().length !== 6}
                                className="bg-slate-900 hover:bg-slate-800 text-white"
                                data-testid="mfa-regen-confirm-btn"
                            >
                                {busy && <Loader2 size={14} className="mr-1.5 animate-spin" />} Regenerate codes
                            </Button>
                        </div>
                    </form>
                </div>
            )}
        </div>
    );
}
