import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API_BASE,
    headers: { "Content-Type": "application/json" },
    timeout: 20000,
    withCredentials: true,
});

// ---- Auth token injection ----
const TOKEN_KEY = "syhomes_access_token";

export function setAuthToken(token) {
    if (token) {
        localStorage.setItem(TOKEN_KEY, token);
    } else {
        localStorage.removeItem(TOKEN_KEY);
    }
}

export function getAuthToken() {
    return localStorage.getItem(TOKEN_KEY);
}

api.interceptors.request.use((config) => {
    const token = getAuthToken();
    if (token) {
        config.headers = config.headers || {};
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Global error interceptor returns the server's `detail` message for UI toasts.
api.interceptors.response.use(
    (r) => r,
    (error) => {
        const detail =
            error?.response?.data?.detail ||
            error?.response?.data?.message ||
            error?.message ||
            "Request failed";
        error.friendlyMessage =
            typeof detail === "string"
                ? detail
                : Array.isArray(detail)
                  ? detail
                        .map((e) => (e?.msg ? e.msg : JSON.stringify(e)))
                        .join(" ")
                  : JSON.stringify(detail);
        if (error?.response?.status === 401) {
            const path = window.location.pathname;
            if (path !== "/login") {
                setAuthToken(null);
                // Soft redirect — let AuthContext handle re-mount
                window.dispatchEvent(new Event("syhomes:unauthorized"));
            }
        }
        return Promise.reject(error);
    }
);
