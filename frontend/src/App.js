import React from "react";
import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/lib/queryClient";

// React Query Devtools — lazy + ErrorBoundary-safe.
// Loaded only in development, and only when navigator.language is a valid
// BCP-47 tag (the devtools internally call `new Intl.Locale(navigator.language)`
// which throws in some headless preview environments where navigator.language
// is the empty string).
const ReactQueryDevtoolsLazy = React.lazy(() =>
    import("@tanstack/react-query-devtools").then((m) => ({
        default: m.ReactQueryDevtools,
    }))
);

function DevtoolsSafe() {
    const lang = (typeof navigator !== "undefined" && navigator.language) || "";
    if (process.env.NODE_ENV === "production") return null;
    if (!lang) return null;
    try {
        // eslint-disable-next-line no-new
        new Intl.Locale(lang);
    } catch {
        return null;
    }
    return (
        <React.Suspense fallback={null}>
            <ReactQueryDevtoolsLazy initialIsOpen={false} buttonPosition="bottom-right" />
        </React.Suspense>
    );
}

import { AuthProvider, ProtectedRoute, useAuth } from "@/context/AuthContext";
import AppShell from "@/components/AppShell";
import LoginPage from "@/pages/LoginPage";
import EntitiesList from "@/pages/EntitiesList";
import EntityDetail from "@/pages/EntityDetail";
import EntityNew from "@/pages/EntityNew";
import EntityEdit from "@/pages/EntityEdit";
import UsersList from "@/pages/UsersList";
import UserDetail from "@/pages/UserDetail";
import UserNew from "@/pages/UserNew";
import UserEdit from "@/pages/UserEdit";
import ProjectsList from "@/pages/ProjectsList";
import ProjectNew from "@/pages/ProjectNew";
import ProjectDetail from "@/pages/ProjectDetail";
import ProjectCostCodes from "@/pages/ProjectCostCodes";
import CostCodesList from "@/pages/CostCodesList";
import CostCodeDetail from "@/pages/CostCodeDetail";
import CostCodeSections from "@/pages/CostCodeSections";
import { RolesList, RoleDetail, PermissionsList } from "@/pages/RolesAndPermissions";
import ProfileSecurity from "@/pages/ProfileSecurity";
import ProfileSessions from "@/pages/ProfileSessions";
import AdminUserSessions from "@/pages/AdminUserSessions";
import AdminLoginHistory from "@/pages/AdminLoginHistory";
import AuditLog from "@/pages/AuditLog";
import ConfigPage from "@/pages/ConfigPage";
import NotificationsPage from "@/pages/NotificationsPage";
import SdltRatesPage from "@/pages/SdltRatesPage";
import AppraisalDefaultsPage from "@/pages/AppraisalDefaultsPage";
import AppraisalsList from "@/pages/AppraisalsList";
import AppraisalPage from "@/pages/AppraisalPage";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

function ShellRoutes() {
    return (
        <AppShell>
            <Routes>
                <Route path="/" element={<Navigate to="/entities" replace />} />
                <Route path="/entities" element={<EntitiesList />} />
                <Route path="/entities/new" element={<EntityNew />} />
                <Route path="/entities/:id" element={<EntityDetail />} />
                <Route path="/entities/:id/edit" element={<EntityEdit />} />
                <Route path="/projects" element={<ProjectsList />} />
                <Route path="/projects/new" element={<ProjectNew />} />
                <Route path="/projects/:id" element={<ProjectDetail />} />
                <Route path="/projects/:id/cost-codes" element={<ProjectCostCodes />} />
                <Route path="/projects/:id/appraisals" element={<AppraisalsList />} />
                <Route path="/appraisals/:id" element={<AppraisalPage />} />
                <Route path="/cost-codes" element={<CostCodesList />} />
                <Route path="/cost-codes/sections" element={<CostCodeSections />} />
                <Route path="/cost-codes/:id" element={<CostCodeDetail />} />
                <Route path="/users" element={<UsersList />} />
                <Route path="/users/new" element={<UserNew />} />
                <Route path="/users/:id/edit" element={<UserEdit />} />
                <Route path="/users/:id/sessions" element={<AdminUserSessions />} />
                <Route path="/users/:id/login-history" element={<AdminLoginHistory />} />
                <Route path="/users/:id" element={<UserDetail />} />
                <Route path="/roles" element={<RolesList />} />
                <Route path="/roles/:id" element={<RoleDetail />} />
                <Route path="/permissions" element={<PermissionsList />} />
                <Route path="/profile" element={<Navigate to="/profile/security" replace />} />
                <Route path="/profile/security" element={<ProfileSecurity />} />
                <Route path="/profile/sessions" element={<ProfileSessions />} />
                <Route path="/audit" element={<AuditLog />} />
                <Route path="/config" element={<ConfigPage />} />
                <Route path="/notifications" element={<NotificationsPage />} />
                <Route path="/settings/sdlt-rates" element={<SdltRatesPage />} />
                <Route path="/settings/appraisal-defaults" element={<AppraisalDefaultsPage />} />
                <Route path="*" element={
                    <div className="text-slate-600" data-testid="not-found-page">
                        <h1 className="font-heading text-2xl font-bold text-slate-900">Not found</h1>
                        <p className="text-sm mt-2">This module is not yet available in Phase 1.</p>
                    </div>
                } />
            </Routes>
        </AppShell>
    );
}

function AppRoutes() {
    return (
        <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/forgot-password" element={<ForgotPassword />} />
            <Route path="/reset-password" element={<ResetPassword />} />
            <Route path="/*" element={<ProtectedRoute><ShellRoutes /></ProtectedRoute>} />
        </Routes>
    );
}

function App() {
    return (
        <div className="App">
            <QueryClientProvider client={queryClient}>
                <BrowserRouter>
                    <AuthProvider>
                        <AppRoutes />
                    </AuthProvider>
                    <Toaster position="top-right" toastOptions={{ className: "!font-sans" }} />
                </BrowserRouter>
                <DevtoolsSafe />
            </QueryClientProvider>
        </div>
    );
}

export default App;
