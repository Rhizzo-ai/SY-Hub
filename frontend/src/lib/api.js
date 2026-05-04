import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

/**
 * Cookies-only auth transport (audit remediation C1, Feb 2026).
 *
 * The backend sets `access_token` + `refresh_token` as HttpOnly cookies on
 * `/api/auth/login`, rotates them on `/api/auth/refresh`, and clears them on
 * `/api/auth/logout`. The frontend NEVER touches token values directly —
 * they live in the cookie jar and ride every request via `withCredentials`.
 *
 * Everything previously in localStorage (access/refresh token strings) is
 * gone: a successful XSS can no longer exfiltrate a bearable token.
 */
export const api = axios.create({
    baseURL: API_BASE,
    headers: { "Content-Type": "application/json" },
    timeout: 20000,
    withCredentials: true,
});


// ---- Refresh-on-401 with a single in-flight promise to prevent stampedes ----
//
// Success path: POST /api/auth/refresh → 204 No Content + rotated Set-Cookie
// headers. Nothing to parse from the body. We resolve the shared promise so
// all queued callers retry their original request (cookies auto-refreshed).
// Failure path: 401 → reject, caller falls through to the "log out" branch.

let _refreshPromise = null;

function refreshCookies() {
    if (_refreshPromise) return _refreshPromise;
    _refreshPromise = axios
        .post(`${API_BASE}/auth/refresh`, null, { withCredentials: true })
        .then((r) => {
            // Contract: 204 on success.
            if (r.status !== 204 && r.status !== 200) {
                throw new Error(`unexpected refresh status ${r.status}`);
            }
            return true;
        })
        .finally(() => { _refreshPromise = null; });
    return _refreshPromise;
}


// ---- Response interceptor: refresh+retry on 401, friendlyMessage for UI ----
api.interceptors.response.use(
    (r) => r,
    async (error) => {
        const original = error?.config;
        const status = error?.response?.status;
        const url = String(original?.url || "");

        // Attempt refresh exactly once for 401s on non-auth routes.
        const isAuthRoute =
            url.includes("/auth/refresh") ||
            url.includes("/auth/login") ||
            url.includes("/auth/logout");

        if (status === 401 && original && !original._retried && !isAuthRoute) {
            original._retried = true;
            try {
                await refreshCookies();
                // Cookies rotated — retry the original request. The browser
                // attaches the fresh access cookie automatically.
                return api(original);
            } catch (_) {
                // Refresh failed — drop to unauth event below.
            }
        }

        const detail =
            error?.response?.data?.detail ||
            error?.response?.data?.message ||
            error?.message ||
            "Request failed";
        error.friendlyMessage =
            typeof detail === "string"
                ? detail
                : Array.isArray(detail)
                  ? detail.map((e) => (e?.msg ? e.msg : JSON.stringify(e))).join(" ")
                  : JSON.stringify(detail);

        if (status === 401 && !isAuthRoute && window.location.pathname !== "/login") {
            window.dispatchEvent(new Event("syhomes:unauthorized"));
        }
        return Promise.reject(error);
    }
);


// ---- Cookie-aware fetch wrapper for binary downloads (CSV/PDF) ----
//
// `fetch` does not honour our axios `withCredentials` default, so callers
// that stream blobs (e.g. CSV export) go via this helper instead of adding
// Authorization headers. Never read or send tokens from JS land.
export function authedFetch(url, init = {}) {
    return fetch(url, { credentials: "include", ...init });
}


// =========================================================================
// Prompt 2.3 Checkpoint 3 — Appraisal Governance endpoints
// =========================================================================

export const fetchRevisions = (appraisalId) =>
    api.get(`/v1/appraisals/${appraisalId}/revisions`).then((r) => r.data);

export const fetchProjectRevisions = (projectId) =>
    api.get(`/v1/projects/${projectId}/revisions`).then((r) => r.data);

export const createNewVersion = (appraisalId, body) =>
    api.post(`/v1/appraisals/${appraisalId}/new-version`, body).then((r) => r.data);

export const fetchGroupScenarios = (groupId) =>
    api.get(`/v1/appraisal-groups/${groupId}/scenarios`).then((r) => r.data);

export const fetchComparator = (groupId) =>
    api.get(`/v1/appraisal-groups/${groupId}/comparator`).then((r) => r.data);

export const createScenario = (baseId, body) =>
    api.post(`/v1/appraisals/${baseId}/scenarios`, body).then((r) => r.data);

export const fetchDecisions = (appraisalId) =>
    api.get(`/v1/appraisals/${appraisalId}/decisions`).then((r) => r.data);

export const logDecision = (appraisalId, body) =>
    api.post(`/v1/appraisals/${appraisalId}/decisions`, body).then((r) => r.data);

export const fetchNudge = (projectId) =>
    api.get(`/v1/projects/${projectId}/nudge`).then((r) => r.data);
