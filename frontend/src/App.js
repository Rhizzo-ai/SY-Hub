import React from "react";
import "@/App.css";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

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
import { RolesList, RoleDetail, PermissionsList } from "@/pages/RolesAndPermissions";
import ProfileSecurity from "@/pages/ProfileSecurity";
import ProfileSessions from "@/pages/ProfileSessions";
import AdminUserSessions from "@/pages/AdminUserSessions";
import AdminLoginHistory from "@/pages/AdminLoginHistory";
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
            <BrowserRouter>
                <AuthProvider>
                    <AppRoutes />
                </AuthProvider>
                <Toaster position="top-right" toastOptions={{ className: "!font-sans" }} />
            </BrowserRouter>
        </div>
    );
}

export default App;
