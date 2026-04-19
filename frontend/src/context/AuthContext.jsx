import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, setAuthToken, getAuthToken } from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
    // `state`: 'loading' | 'authed' | 'anon'
    const [state, setState] = useState(getAuthToken() ? "loading" : "anon");
    const [me, setMe] = useState(null);

    const fetchMe = useCallback(async () => {
        try {
            const r = await api.get("/auth/me");
            setMe(r.data);
            setState("authed");
            return r.data;
        } catch (e) {
            setAuthToken(null);
            setMe(null);
            setState("anon");
            return null;
        }
    }, []);

    useEffect(() => {
        if (state === "loading") fetchMe();
        const onUnauth = () => {
            setAuthToken(null);
            setMe(null);
            setState("anon");
        };
        window.addEventListener("syhomes:unauthorized", onUnauth);
        return () => window.removeEventListener("syhomes:unauthorized", onUnauth);
    }, [state, fetchMe]);

    const login = useCallback(async (email, password) => {
        const r = await api.post("/auth/login", { email, password });
        if (r.data.mfa_required) return { mfa_required: true, challenge: r.data.mfa_challenge_token };
        setAuthToken(r.data.access_token);
        await fetchMe();
        return { mfa_required: false };
    }, [fetchMe]);

    const submitMfa = useCallback(async (challenge, code, useBackup = false) => {
        const r = await api.post("/auth/mfa/verify", {
            challenge_token: challenge,
            code,
            use_backup_code: useBackup,
        });
        setAuthToken(r.data.access_token);
        await fetchMe();
    }, [fetchMe]);

    const logout = useCallback(async () => {
        try { await api.post("/auth/logout"); } catch (_) {}
        setAuthToken(null);
        setMe(null);
        setState("anon");
    }, []);

    const hasPerm = useCallback((code) => {
        if (!me) return false;
        return me.permissions?.includes(code);
    }, [me]);

    const hasAnyPerm = useCallback((...codes) => codes.some((c) => hasPerm(c)), [hasPerm]);

    return (
        <AuthContext.Provider value={{ state, me, login, submitMfa, logout, refresh: fetchMe, hasPerm, hasAnyPerm }}>
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
    return children;
}
