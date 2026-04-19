import React from "react";
import { NavLink, Link, useNavigate } from "react-router-dom";
import {
    Building2, Users, Layers, Calculator, LineChart, Wallet,
    CalendarDays, FileText, ShieldCheck, Landmark, Link2, LogOut, KeyRound,
} from "lucide-react";
import { useAuth } from "@/context/AuthContext";

const NAV = [
    { label: "Entities", to: "/entities", icon: Building2, enabled: true, testid: "nav-entities" },
    { label: "Users", to: "/users", icon: Users, enabled: true, testid: "nav-users" },
    { label: "Roles", to: "/roles", icon: ShieldCheck, enabled: true, testid: "nav-roles" },
    { label: "Permissions", to: "/permissions", icon: KeyRound, enabled: true, testid: "nav-permissions" },
    { label: "Projects", to: "/projects", icon: Layers, enabled: false, testid: "nav-projects" },
    { label: "Cost Codes", to: "/cost-codes", icon: Calculator, enabled: false, testid: "nav-cost-codes" },
    { label: "Appraisals", to: "/appraisals", icon: LineChart, enabled: false, testid: "nav-appraisals" },
    { label: "Budgets", to: "/budgets", icon: Wallet, enabled: false, testid: "nav-budgets" },
    { label: "Cash Flow", to: "/cash-flow", icon: Landmark, enabled: false, testid: "nav-cash-flow" },
    { label: "Programme", to: "/programme", icon: CalendarDays, enabled: false, testid: "nav-programme" },
    { label: "Documents", to: "/documents", icon: FileText, enabled: false, testid: "nav-documents" },
    { label: "Compliance", to: "/compliance", icon: ShieldCheck, enabled: false, testid: "nav-compliance" },
    { label: "Xero", to: "/xero", icon: Link2, enabled: false, testid: "nav-xero" },
];

export default function AppShell({ children }) {
    const { me, logout } = useAuth();
    const nav = useNavigate();
    const initials = (me?.display_name || me?.email || "??")
        .split(/[ .@]/).filter(Boolean).slice(0, 2).map((s) => s[0]?.toUpperCase()).join("");

    return (
        <div className="min-h-screen bg-slate-50" data-testid="app-shell">
            <aside className="fixed inset-y-0 left-0 w-64 border-r border-slate-200 bg-white flex flex-col z-40" data-testid="app-sidebar">
                <div className="h-16 px-6 flex items-center border-b border-slate-200">
                    <Link to="/entities" className="flex items-center gap-2" data-testid="sidebar-logo">
                        <div className="h-8 w-8 rounded-md bg-slate-900 flex items-center justify-center">
                            <span className="font-heading font-bold text-white text-sm tracking-tight">SY</span>
                        </div>
                        <div className="leading-tight">
                            <div className="font-heading text-sm font-semibold text-slate-900">SY Homes</div>
                            <div className="text-[11px] uppercase tracking-widest text-slate-500">Operations</div>
                        </div>
                    </Link>
                </div>
                <nav className="flex-1 overflow-y-auto py-4 px-3 space-y-0.5">
                    <div className="px-3 pt-2 pb-1 text-[10px] uppercase tracking-widest text-slate-400 font-semibold">Modules</div>
                    {NAV.map((item) => {
                        const Icon = item.icon;
                        if (!item.enabled) {
                            return (
                                <div key={item.label} className="flex items-center gap-3 px-3 py-2 rounded-md text-slate-400 cursor-not-allowed select-none" data-testid={item.testid} title="Coming in a later phase">
                                    <Icon size={16} strokeWidth={1.5} />
                                    <span className="text-sm">{item.label}</span>
                                    <span className="ml-auto text-[10px] uppercase tracking-widest text-slate-300">Soon</span>
                                </div>
                            );
                        }
                        return (
                            <NavLink key={item.label} to={item.to} data-testid={item.testid}
                                className={({ isActive }) => ["flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-colors",
                                    isActive ? "bg-slate-900 text-white font-medium" : "text-slate-700 hover:bg-slate-100"].join(" ")}>
                                <Icon size={16} strokeWidth={1.5} />
                                <span>{item.label}</span>
                            </NavLink>
                        );
                    })}
                </nav>
                <div className="border-t border-slate-200 px-5 py-4 text-xs text-slate-500" data-testid="sidebar-footer">
                    <div className="uppercase tracking-widest text-[10px] text-slate-400 mb-1">Phase</div>
                    <div className="font-mono text-slate-700">1.2 · Users & RBAC</div>
                </div>
            </aside>

            <div className="pl-64">
                <header className="h-16 border-b border-slate-200 bg-white sticky top-0 z-30 px-8 flex items-center justify-between" data-testid="app-topbar">
                    <div className="flex items-center gap-4">
                        <span className="text-xs uppercase tracking-widest text-slate-500">Tenant</span>
                        <span className="font-heading text-sm font-semibold text-slate-900" data-testid="topbar-tenant-name">SY Homes</span>
                    </div>
                    <div className="flex items-center gap-4">
                        {me && (
                            <div className="text-right leading-tight hidden sm:block" data-testid="topbar-user">
                                <div className="text-sm font-medium text-slate-900">{me.display_name}</div>
                                <div className="text-[11px] mono text-slate-500">{me.email}</div>
                            </div>
                        )}
                        <div className="h-8 w-8 rounded-full bg-slate-900 flex items-center justify-center text-white text-xs font-semibold" data-testid="topbar-user-avatar">
                            {initials || "SU"}
                        </div>
                        <button onClick={async () => { await logout(); nav("/login"); }} className="text-slate-500 hover:text-slate-900" data-testid="logout-button" title="Sign out">
                            <LogOut size={16} />
                        </button>
                    </div>
                </header>
                <main className="p-8 max-w-[1600px] mx-auto" data-testid="app-main">{children}</main>
            </div>
        </div>
    );
}
