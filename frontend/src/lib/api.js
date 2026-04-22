import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API_BASE,
    headers: { "Content-Type": "application/json" },
    timeout: 20000,
    withCredentials: true,
});

// ---- Auth token storage ----
const ACCESS_KEY = "syhomes_access_token";
const REFRESH_KEY = "syhomes_refresh_token";

export function setAuthToken(access) {
    if (access) localStorage.setItem(ACCESS_KEY, access);
    else localStorage.removeItem(ACCESS_KEY);
}
export function getAuthToken() {
    return localStorage.getItem(ACCESS_KEY);
}
export function setRefreshToken(refresh) {
    if (refresh) localStorage.setItem(REFRESH_KEY, refresh);
    else localStorage.removeItem(REFRESH_KEY);
}
export function getRefreshToken() {
    return localStorage.getItem(REFRESH_KEY);
}
export function setTokenPair({ access_token, refresh_token }) {
    setAuthToken(access_token);
    if (refresh_token) setRefreshToken(refresh_token);
}
export function clearTokens() {
    setAuthToken(null);
    setRefreshToken(null);
}

// ---- Request interceptor: attach access token ----
api.interceptors.request.use((config) => {
    const token = getAuthToken();
    if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// ---- Refresh-on-401 with a single in-flight promise to prevent stampedes ----
let _refreshPromise = null;

async function refreshTokens() {
    if (_refreshPromise) return _refreshPromise;
    const refresh = getRefreshToken();
    if (!refresh) return Promise.reject(new Error("no-refresh-token"));
    _refreshPromise = axios
        .post(`${API_BASE}/auth/refresh`, { refresh_token: refresh }, { withCredentials: true })
        .then((r) => {
            setTokenPair(r.data);
            return r.data.access_token;
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

        // Attempt refresh exactly once for 401s on non-auth routes.
        if (
            status === 401 &&
            original &&
            !original._retried &&
            !String(original.url || "").includes("/auth/refresh") &&
            !String(original.url || "").includes("/auth/login") &&
            getRefreshToken()
        ) {
            original._retried = true;
            try {
                const newAccess = await refreshTokens();
                original.headers = original.headers || {};
                original.headers.Authorization = `Bearer ${newAccess}`;
                return api(original);
            } catch (_) {
                clearTokens();
                if (window.location.pathname !== "/login") {
                    window.dispatchEvent(new Event("syhomes:unauthorized"));
                }
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

        if (status === 401 && window.location.pathname !== "/login") {
            clearTokens();
            window.dispatchEvent(new Event("syhomes:unauthorized"));
        }
        return Promise.reject(error);
    }
);
