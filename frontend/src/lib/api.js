import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_BASE = `${BACKEND_URL}/api`;

export const api = axios.create({
    baseURL: API_BASE,
    headers: { "Content-Type": "application/json" },
    timeout: 20000,
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
                : JSON.stringify(detail);
        return Promise.reject(error);
    }
);
