import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import ForcedMfaEnroll from "@/pages/ForcedMfaEnroll";

const AuthContext = createContext(null);

// Idle-timeout UX: warn at 55 min, force logout at 60 min. Must align with
// IDLE_TIMEOUT_MINUTES in backend app/services/sessions.py.
const IDLE_WARN_MS = 55 * 60 * 1000;
const IDLE_FORCE_MS = 60 * 60 * 1000;

/**
 * Cookies-only AuthContext (audit remediation C1, Feb 2026).
 *
 * Lifecycle:
 *   1. First mount → state="loading" → `GET /auth/me` to see if a session
 *      cookie survived a page reload. Success populates `me`; 401 drops to
 *      state="anon". This is the ONLY time we call /auth/me on boot.
 *   2. Login → `POST /auth/login` sets the cookies server-side and returns
 *      the user metadata in the body. We hydrate `me` directly from the
 *      login response — no follow-up /auth/me round-trip.
 *   3. MFA challenge → second login step via `POST /auth/mfa/verify`, same
 *      hydration pattern.
 *   4. MFA enrolment for an enforced role → `mfa_enrollment_required: true`
 *      in the login body → route to ForcedMfaEnroll. The pending JWT rides
 *      on the access_token cookie; we do NOT read a pending-token string.
 *      After /mfa/enroll/confirm, call `refresh()` to re-hydrate `me` under
 *      the rotated full-session cookie.
 *   5. Logout → `POST /auth/logout` clears cookies server-side.
 *   6. 401 mid-session → api.js interceptor attempts a silent /auth/refresh;
 *      if that also 401s it dispatches `syhomes:unauthorized` which drops
 *      us back to state="anon".
 */
export function AuthProvider({ children }) {
    // No localStorage peek: cookies are HttpOnly. We optimistically assume
    // there MAY be a session and let /auth/me decide.
    const [state, setState] = useState("loading");
    const [me, setMe] = useState(null);
    const [idleWarning, setIdleWarning] = useState(false);
    const lastActivityRef = useRef(Date.now());

    const hydrateFromMe = useCallback((data) => {
        setMe(data);
        setState(data?.token_type === "mfa_pending" ? "pending_mfa" : "authed");
    }, []);

    const fetchMe = useCallback(async () => {
        try {
            const r = await api.get("/auth/me");
            hydrateFromMe(r.data);
            return r.data;
        } catch (_) {
            setMe(null);
            setState("anon");
            return null;
        }
    }, [hydrateFromMe]);

    // Boot-time session restoration.
    useEffect(() => {
        fetchMe();
        const onUnauth = () => {
            setMe(null);
            setState("anon");
        };
        window.addEventListener("syhomes:unauthorized", onUnauth);
        return () => window.removeEventListener("syhomes:unauthorized", onUnauth);
    }, [fetchMe]);

    // --- Idle-timeout tracking (authed only) ---
    useEffect(() => {
        if (state !== "authed") return;
        const bump = () => { lastActivityRef.current = Date.now(); setIdleWarning(false); };
        const events = ["mousemove", "keydown", "click", "scroll", "touchstart"];
        events.forEach((e) => window.addEventListener(e, bump, { passive: true }));
        const interval = setInterval(() => {
            const idle = Date.now() - lastActivityRef.current;
            if (idle >= IDLE_FORCE_MS) {
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
        const body = r.data;

        if (body.mfa_required) {
            // Half-authenticated — no session cookie yet. Caller collects
            // the TOTP and routes into submitMfa().
            return { mfa_required: true, challenge: body.mfa_challenge_token };
        }
        if (body.mfa_enrollment_required) {
            // The backend has already set the mfa_pending JWT as an HttpOnly
            // `access_token` cookie. We don't read any token from the body
            // (audit C1: mfa_pending_token was removed from the response).
            // Hydrate `me` via /auth/me on the pending cookie; ProtectedRoute
            // will render the ForcedMfaEnroll gate when token_type is pending.
            await fetchMe();
            return {
                mfa_enrollment_required: true,
                enforced_role_name: body.enforced_role_name,
            };
        }

        // Normal path — cookies set, user metadata in body. Hydrate directly
        // from the login payload; skip the /auth/me round-trip.
        hydrateFromMe({
            ...body.user,
            // /auth/me returns these fields; synthesise what we can so the
            // UI doesn't flash with missing permissions. A follow-up
            // refresh() can be used by callers that need the full perm set.
            token_type: "access",
            permissions: [],
            is_super_admin: false,
            mfa_enrollment_required: false,
        });
        // Then pull /auth/me asynchronously to populate permissions +
        // is_super_admin. This is intentionally not awaited before return:
        // the caller can navigate immediately and gated UI will flip on
        // once perms arrive (very fast on a LAN or same-pod call).
        fetchMe();
        return { mfa_required: false };
    }, [fetchMe, hydrateFromMe]);

    const submitMfa = useCallback(async (challenge, code, useBackup = false, remember_me = false) => {
        await api.post("/auth/mfa/verify", {
            challenge_token: challenge,
            code,
            use_backup_code: useBackup,
            remember_me,
        });
        // Cookies rotated → full access. Hydrate `me` (includes permissions).
        await fetchMe();
    }, [fetchMe]);

    const logout = useCallback(async () => {
        try { await api.post("/auth/logout"); } catch (_) {}
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
