import React, { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Bell } from "lucide-react";
import { api } from "@/lib/api";
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

const POLL_INTERVAL_MS = 30_000;
const PRIORITY_DOT = {
    Critical: "bg-rose-500",
    High: "bg-amber-500",
    Normal: "bg-slate-400",
    Low: "bg-slate-300",
};

function formatRelative(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    const diff = (Date.now() - d.getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
    return `${Math.floor(diff / 86400)}d`;
}

export default function NotificationBell() {
    const nav = useNavigate();
    const [count, setCount] = useState(0);
    const [open, setOpen] = useState(false);
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(false);
    const pollRef = useRef(null);

    const refreshCount = async () => {
        try {
            const r = await api.get("/v1/notifications/unread-count");
            setCount(r.data.count || 0);
        } catch {
            // Silent — bell is best-effort.
        }
    };

    useEffect(() => {
        refreshCount();
        pollRef.current = setInterval(refreshCount, POLL_INTERVAL_MS);
        return () => { if (pollRef.current) clearInterval(pollRef.current); };
    }, []);

    const loadPanel = async () => {
        setLoading(true);
        try {
            const r = await api.get("/v1/notifications/unread", { params: { limit: 10 } });
            setItems(r.data.items || []);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => { if (open) loadPanel(); }, [open]);

    const markAllRead = async () => {
        try {
            await api.post("/v1/notifications/mark-all-read");
            setCount(0); setItems([]);
        } catch { /* noop */ }
    };

    const onClickItem = async (entry) => {
        if (entry.kind === "single") {
            const n = entry.notification;
            try {
                await api.patch(`/v1/notifications/${n.id}/read`);
            } catch { /* noop */ }
            if (n.action_url) {
                setOpen(false);
                nav(n.action_url);
            }
        }
        refreshCount();
    };

    const renderEntry = (entry, idx) => {
        if (entry.kind === "group") {
            return (
                <div
                    key={`g-${idx}`}
                    className="px-4 py-3 hover:bg-slate-50 cursor-pointer border-b border-slate-100"
                    onClick={() => { setOpen(false); nav("/notifications"); }}
                    data-testid={`bell-group-${entry.notification_type}`}
                >
                    <div className="flex items-start gap-2">
                        <span className={`mt-1.5 h-2 w-2 rounded-full ${PRIORITY_DOT[entry.highest_priority] || PRIORITY_DOT.Normal}`} />
                        <div className="flex-1">
                            <div className="text-sm font-medium text-slate-900">
                                {entry.count} × {entry.notification_type.replace(/_/g, " ")}
                            </div>
                            <div className="text-xs text-slate-600 line-clamp-1 mt-0.5">
                                Latest: {entry.title_sample}
                            </div>
                            <div className="text-[11px] text-slate-400 mt-1">
                                {formatRelative(entry.latest_created_at)}
                            </div>
                        </div>
                    </div>
                </div>
            );
        }
        const n = entry.notification;
        return (
            <div
                key={n.id}
                className="px-4 py-3 hover:bg-slate-50 cursor-pointer border-b border-slate-100"
                onClick={() => onClickItem(entry)}
                data-testid={`bell-item-${n.id}`}
            >
                <div className="flex items-start gap-2">
                    <span className={`mt-1.5 h-2 w-2 rounded-full ${PRIORITY_DOT[n.priority] || PRIORITY_DOT.Normal}`} />
                    <div className="flex-1">
                        <div className="text-sm font-medium text-slate-900">{n.title}</div>
                        <div className="text-xs text-slate-600 line-clamp-2 mt-0.5">{n.body}</div>
                        <div className="text-[11px] text-slate-400 mt-1">
                            {formatRelative(n.created_at)} · {n.notification_type.replace(/_/g, " ")}
                        </div>
                    </div>
                </div>
            </div>
        );
    };

    return (
        <DropdownMenu open={open} onOpenChange={setOpen}>
            <DropdownMenuTrigger asChild>
                <button
                    className="relative h-9 w-9 rounded-md hover:bg-slate-100 flex items-center justify-center"
                    aria-label="Notifications"
                    data-testid="notification-bell"
                >
                    <Bell size={18} className="text-slate-700" />
                    {count > 0 && (
                        <span
                            className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-rose-600 text-white text-[10px] font-semibold flex items-center justify-center"
                            data-testid="notification-bell-count"
                        >
                            {count > 99 ? "99+" : count}
                        </span>
                    )}
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent
                align="end"
                className="w-96 max-h-[500px] overflow-y-auto p-0"
                data-testid="notification-bell-panel"
            >
                <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between bg-slate-50">
                    <span className="font-heading text-sm font-semibold text-slate-900">Notifications</span>
                    <div className="flex items-center gap-3 text-xs">
                        <button
                            onClick={markAllRead}
                            disabled={count === 0}
                            className="text-slate-600 hover:text-slate-900 disabled:opacity-40"
                            data-testid="notification-mark-all-read"
                        >Mark all read</button>
                        <button
                            onClick={() => { setOpen(false); nav("/notifications"); }}
                            className="text-slate-600 hover:text-slate-900"
                            data-testid="notification-view-all"
                        >View all</button>
                    </div>
                </div>
                {loading ? (
                    <div className="px-4 py-6 text-sm text-slate-500 text-center">Loading…</div>
                ) : items.length === 0 ? (
                    <div className="px-4 py-6 text-sm text-slate-500 text-center" data-testid="notification-empty">
                        You're all caught up.
                    </div>
                ) : (
                    <div>{items.map(renderEntry)}</div>
                )}
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
