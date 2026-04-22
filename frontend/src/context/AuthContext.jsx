import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api, setTokenPair, clearTokens, getAuthToken } from "@/lib/api";
import ForcedMfaEnroll from "@/pages/ForcedMfaEnroll";

const AuthContext = createContext(null);

// Idle-timeout UX: warn at 55 min, force logout at 60 min. Must align with
// IDLE_TIMEOUT_MINUTES in backend app/services/sessions.py.
const IDLE_WARN_MS = 55 * 60 * 1000;
const IDLE_FORCE_MS = 60 * 60 * 1000;

export function AuthProvider({ children }) {
    const [state, setState] = useState(getAuthToken() ? "loading" : "anon");
    const [me, setMe] = useState(null);
    const [idleWarning, setIdleWarning] = useState(false);
    const lastActivityRef = useRef(Date.now());

    const fetchMe = useCallback(async () => {
        try {
            const r = await api.get("/auth/me");
            setMe(r.data);
            setState(r.data?.token_type === "mfa_pending" ? "pending_mfa" : "authed");
            return r.data;
        } catch (e) {
            clearTokens();
            setMe(null);
            setState("anon");
            return null;
        }
    }, []);

    useEffect(() => {
        if (state === "loading") fetchMe();
        const onUnauth = () => {
            clearTokens();
            setMe(null);
            setState("anon");
        };
        window.addEventListener("syhomes:unauthorized", onUnauth);
        return () => window.removeEventListener("syhomes:unauthorized", onUnauth);
    }, [state, fetchMe]);

    // --- Idle-timeout tracking (authed only) ---
    useEffect(() => {
        if (state !== "authed") return;
        const bump = () => { lastActivityRef.current = Date.now(); setIdleWarning(false); };
        const events = ["mousemove", "keydown", "click", "scroll", "touchstart"];
        events.forEach((e) => window.addEventListener(e, bump, { passive: true }));
        const interval = setInterval(() => {
            const idle = Date.now() - lastActivityRef.current;
            if (idle >= IDLE_FORCE_MS) {
                // Force-logout
                clearTokens();
                setMe(null);
                setState("anon");
            } else if (idle >= IDLE_WARN_MS && !idleWarning) {
                setIdleWarning(true);
            }
        }, 30000);
        return () => {
            events.forEach((e) => window.removeEventListener(e, bump));
            clearInterval(interval);
        };
    }, [state, idleWarning]);

    const login = useCallback(async (email, password, remember_me = false) => {
        const r = await api.post("/auth/login", { email, password, remember_me });
        if (r.data.mfa_required) {
            return { mfa_required: true, challenge: r.data.mfa_challenge_token };
        }
        if (r.data.mfa_enrollment_required && r.data.mfa_pending_token) {
            // mfa_pending tokens are one-shot JWTs, no refresh rotation.
            setTokenPair({ access_token: r.data.mfa_pending_token, refresh_token: null });
            await fetchMe();
            return {
                mfa_enrollment_required: true,
                enforced_role_name: r.data.enforced_role_name,
            };
        }
        setTokenPair(r.data);
        await fetchMe();
        return { mfa_required: false };
    }, [fetchMe]);

    const submitMfa = useCallback(async (challenge, code, useBackup = false, remember_me = false) => {
        const r = await api.post("/auth/mfa/verify", {
            challenge_token: challenge, code,
            use_backup_code: useBackup, remember_me,
        });
        setTokenPair(r.data);
        await fetchMe();
    }, [fetchMe]);

    const logout = useCallback(async () => {
        try { await api.post("/auth/logout"); } catch (_) {}
        clearTokens();
        setMe(null);
        setState("anon");
    }, []);

    const hasPerm = useCallback((code) => {
        if (!me) return false;
        return me.permissions?.includes(code);
    }, [me]);

    const hasAnyPerm = useCallback((...codes) => codes.some((c) => hasPerm(c)), [hasPerm]);

    return (
        <AuthContext.Provider
            value={{
                state, me, login, submitMfa, logout, refresh: fetchMe, hasPerm, hasAnyPerm,
                idleWarning, dismissIdleWarning: () => setIdleWarning(false),
            }}
        >
            {children}
        </AuthContext.Provider>
    );
}

export function useAuth() {
    const ctx = useContext(AuthContext);
    if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
    return ctx;
}

export function ProtectedRoute({ children }) {
    const { state } = useAuth();
    if (state === "loading") {
        return (
            <div className="min-h-screen flex items-center justify-center text-slate-500 font-mono text-sm">
                Loading…
            </div>
        );
    }
    if (state === "anon") {
        window.location.replace("/login");
        return null;
    }
    if (state === "pending_mfa") {
        return <ForcedMfaEnroll />;
    }
    return children;
}
