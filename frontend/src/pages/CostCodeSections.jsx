import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { displayEnum } from "@/lib/format";

export default function CostCodeSections() {
    const [rows, setRows] = useState([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        api.get("/cost-code-sections")
           .then((r) => setRows(r.data))
           .finally(() => setLoading(false));
    }, []);

    return (
        <div className="space-y-6" data-testid="cc-sections-page">
            <Link to="/cost-codes"
                  className="text-sm text-slate-600 hover:text-slate-900 underline decoration-dotted">
                ← back to cost codes
            </Link>
            <h1 className="font-heading text-2xl font-bold text-slate-900">
                Cost Code Sections
            </h1>
            <p className="text-sm text-slate-600 max-w-xl">
                Read-only. Section CRUD is intentionally not exposed in the UI —
                changes route via super-admin migration only.
            </p>
            {loading
                ? <Loader2 className="w-5 h-5 animate-spin text-slate-400" />
                : (
                    <table className="w-full text-sm bg-white border border-slate-200 rounded-md">
                        <thead className="bg-slate-50 text-[11px] uppercase tracking-widest text-slate-500">
                            <tr>
                                <th className="text-left p-3 w-12">#</th>
                                <th className="text-left p-3">Code</th>
                                <th className="text-left p-3">Name</th>
                                <th className="text-left p-3">P&L category</th>
                                <th className="text-left p-3">Direct cost?</th>
                                <th className="text-right p-3">Active codes</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r) => (
                                <tr key={r.id} className="border-t border-slate-200">
                                    <td className="p-3 mono text-slate-500">{r.display_order}</td>
                                    <td className="p-3"><code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{r.code}</code></td>
                                    <td className="p-3 text-slate-800">{r.name}</td>
                                    <td className="p-3">{displayEnum(r.default_p_and_l_category)}</td>
                                    <td className="p-3">{r.is_direct_cost ? "Yes" : "No"}</td>
                                    <td className="p-3 text-right mono">{r.active_code_count}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
        </div>
    );
}
