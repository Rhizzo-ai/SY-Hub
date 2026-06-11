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
import CostCodeAdmin from "@/pages/CostCodeAdmin";
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
import ActualsList from "@/pages/projects/ActualsList";
import ActualNew from "@/pages/projects/ActualNew";
import ActualDetail from "@/pages/projects/ActualDetail";
import PaymentsView from "@/pages/payments/PaymentsView";
import ForgotPassword from "@/pages/ForgotPassword";
import ResetPassword from "@/pages/ResetPassword";

// Chat 19C §R8 Q9 mitigation: lazy-load AI Capture pages so the
// review surface (incl. heavy PromoteForm + RHF/zod payload) is
// pulled out of the main bundle. Tight head-room (419.72 → ≤436.72 kB).
const AICaptureInbox = React.lazy(() => import("@/pages/AICaptureInbox"));
const CaptureJobDetail = React.lazy(() => import("@/pages/CaptureJobDetail"));
// Chat 20 §R4.1 (B38) — Cost dashboard. recharts code-split into its
// own chunk via the webpackChunkName magic comment. Main bundle delta
// must stay under +3 kB gz (PASS 2 M4, gate 1).
const AICaptureCosts = React.lazy(() =>
    import(/* webpackChunkName: "ai-capture-costs" */ "@/pages/AICaptureCosts")
);
// Chat 23 §R2.2 — lazy-load the budgets pages so BudgetGrid v2's
// TanStack Table + dnd-kit footprint lands in its own chunk. Buys
// headroom against the 437 kB main-bundle cap before Grid v2 ships
// in §R3.
const BudgetsList = React.lazy(() =>
    import(/* webpackChunkName: "budgets" */ "@/pages/projects/BudgetsList")
);
const BudgetDetail = React.lazy(() =>
    import(/* webpackChunkName: "budgets" */ "@/pages/projects/BudgetDetail")
);

// Chat 24 §R5 — lazy-load the supplier directory + PO surface so the
// new pages land in their own chunk and protect the main bundle gz
// budget (437 kB cap, ~395 kB at R4 close).
const SupplierList = React.lazy(() =>
    import(/* webpackChunkName: "suppliers-po" */ "@/pages/SupplierList")
);
const SupplierDetail = React.lazy(() =>
    import(/* webpackChunkName: "suppliers-po" */ "@/pages/SupplierDetail")
);
const SupplierForm = React.lazy(() =>
    import(/* webpackChunkName: "suppliers-po" */ "@/pages/SupplierForm")
);
const PurchaseOrderList = React.lazy(() =>
    import(/* webpackChunkName: "suppliers-po" */ "@/pages/projects/PurchaseOrderList")
);
const PurchaseOrderForm = React.lazy(() =>
    import(/* webpackChunkName: "suppliers-po" */ "@/pages/projects/PurchaseOrderForm")
);
const PurchaseOrderDetail = React.lazy(() =>
    import(/* webpackChunkName: "suppliers-po" */ "@/pages/projects/PurchaseOrderDetail")
);
const NumberPrefixManager = React.lazy(() =>
    import(/* webpackChunkName: "suppliers-po" */ "@/pages/projects/NumberPrefixManager")
);

// Prompt 2.6-FE §R1 — lazy-load BCR detail in its own chunk so the
// surface lands without inflating the main bundle. The Changes /
// Change Log tabs on BudgetDetail import their components directly
// from the budgets chunk (small enough not to need a third chunk).
const BudgetChangeDetail = React.lazy(() =>
    import(/* webpackChunkName: "budgets" */ "@/pages/projects/BudgetChangeDetail")
);

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
                <Route
                    path="/projects/:projectId/budgets"
                    element={
                        <React.Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
                            <BudgetsList />
                        </React.Suspense>
                    }
                />
                <Route
                    path="/projects/:projectId/budgets/:budgetId"
                    element={
                        <React.Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
                            <BudgetDetail />
                        </React.Suspense>
                    }
                />
                {/* Chat 19B §R2.1 — Actuals (flat siblings; ProjectDetail is NOT an Outlet) */}
                <Route path="/projects/:projectId/actuals" element={<ActualsList />} />
                <Route path="/projects/:projectId/actuals/new" element={<ActualNew />} />
                <Route path="/projects/:projectId/actuals/:actualId" element={<ActualDetail />} />
                {/* Louise's global cross-project payments view */}
                <Route path="/payments" element={<PaymentsView />} />
                {/* Chat 19C §R2 — AI Capture review surface (top-level siblings) */}
                <Route
                    path="/ai-capture"
                    element={
                        <React.Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
                            <AICaptureInbox />
                        </React.Suspense>
                    }
                />
                {/* Chat 20 §R4.1 — Cost dashboard route MUST precede :jobId so
                    the literal "cost" segment is never matched as a jobId. */}
                <Route
                    path="/ai-capture/cost"
                    element={
                        <React.Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
                            <AICaptureCosts />
                        </React.Suspense>
                    }
                />
                <Route
                    path="/ai-capture/:jobId"
                    element={
                        <React.Suspense fallback={<div className="p-6 text-sm text-slate-500">Loading…</div>}>
                            <CaptureJobDetail />
                        </React.Suspense>
                    }
                />
                <Route path="/appraisals/:id" element={<AppraisalPage />} />
                <Route path="/cost-codes" element={<CostCodesList />} />
                <Route path="/cost-codes/admin" element={<CostCodeAdmin />} />
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
                {/* Chat 24 §R5 — Suppliers + Purchase Orders + Numbering */}
                <Route path="/suppliers" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <SupplierList />
                    </React.Suspense>
                } />
                <Route path="/suppliers/new" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <SupplierForm />
                    </React.Suspense>
                } />
                <Route path="/suppliers/:id" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <SupplierDetail />
                    </React.Suspense>
                } />
                <Route path="/suppliers/:id/edit" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <SupplierForm />
                    </React.Suspense>
                } />
                <Route path="/projects/:id/purchase-orders" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <PurchaseOrderList />
                    </React.Suspense>
                } />
                <Route path="/projects/:id/purchase-orders/new" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <PurchaseOrderForm />
                    </React.Suspense>
                } />
                <Route path="/projects/:id/purchase-orders/:po_id" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <PurchaseOrderDetail />
                    </React.Suspense>
                } />
                <Route path="/projects/:id/settings/numbering" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <NumberPrefixManager />
                    </React.Suspense>
                } />
                {/* Prompt 2.6-FE §R1 — BCR detail (Surface B). The
                    standalone cross-project queue at /budget-changes
                    is deferred (backend gap B51). */}
                <Route path="/budget-changes/:bcrId" element={
                    <React.Suspense fallback={<div className="p-6 text-sm">Loading…</div>}>
                        <BudgetChangeDetail />
                    </React.Suspense>
                } />
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
