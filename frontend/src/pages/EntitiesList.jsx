import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams, Link, useNavigate } from "react-router-dom";
import { Plus, Search, ChevronUp, ChevronDown, X, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useEnums } from "@/hooks/useTenant";
import { formatCompaniesHouse, formatVATNumber, formatYearEnd, displayEnum } from "@/lib/format";
import EntityStatusBadge from "@/components/entity/EntityStatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const COLUMNS = [
    { key: "name", label: "Name", sortable: true, className: "w-[28%]" },
    { key: "entity_type", label: "Type", sortable: true, className: "w-[14%]" },
    { key: "companies_house_number", label: "Companies House", sortable: true, className: "w-[16%]" },
    { key: "vat_number", label: "VAT", sortable: true, className: "w-[18%]" },
    { key: "status", label: "Status", sortable: true, className: "w-[12%]" },
    { key: "year_end", label: "Year End", sortable: true, className: "w-[12%]" },
];

export default function EntitiesList() {
    const [params, setParams] = useSearchParams();
    const navigate = useNavigate();
    const enums = useEnums();

    const q = params.get("q") ?? "";
    const type = params.get("type") ?? "";
    const status = params.get("status") ?? "";
    const sort = params.get("sort") ?? "name";
    const dir = params.get("dir") ?? "asc";
    const page = parseInt(params.get("page") ?? "1", 10);
    const pageSize = 50;

    const [searchValue, setSearchValue] = useState(q);
    const [data, setData] = useState({ items: [], total: 0 });
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        setSearchValue(q);
    }, [q]);

    useEffect(() => {
        let alive = true;
        setLoading(true);
        const query = {
            q: q || undefined,
            entity_type: type || undefined,
            status: status || undefined,
            sort,
            dir,
            page,
            page_size: pageSize,
        };
        api
            .get("/entities", { params: query })
            .then((r) => {
                if (alive) setData(r.data);
            })
            .finally(() => {
                if (alive) setLoading(false);
            });
        return () => {
            alive = false;
        };
    }, [q, type, status, sort, dir, page]);

    const setParam = (key, value) => {
        const next = new URLSearchParams(params);
        if (!value) next.delete(key);
        else next.set(key, value);
        if (key !== "page") next.set("page", "1");
        setParams(next);
    };

    const toggleSort = (col) => {
        if (sort === col) {
            setParam("dir", dir === "asc" ? "desc" : "asc");
        } else {
            const next = new URLSearchParams(params);
            next.set("sort", col);
            next.set("dir", "asc");
            next.set("page", "1");
            setParams(next);
        }
    };

    const onSearchSubmit = (e) => {
        e.preventDefault();
        setParam("q", searchValue.trim());
    };

    const totalPages = Math.max(1, Math.ceil(data.total / pageSize));
    const filterChips = useMemo(
        () => [
            type && { key: "type", label: `Type: ${displayEnum(type)}` },
            status && { key: "status", label: `Status: ${displayEnum(status)}` },
            q && { key: "q", label: `Search: "${q}"` },
        ].filter(Boolean),
        [type, status, q]
    );

    return (
        <div className="space-y-6" data-testid="entities-list-page">
            <header className="flex items-start justify-between gap-4">
                <div>
                    <div className="text-xs uppercase tracking-widest text-slate-500 font-semibold">
                        Module 01
                    </div>
                    <h1 className="font-heading text-3xl font-bold tracking-tight text-slate-900 mt-1">
                        Entities
                    </h1>
                    <p className="text-sm text-slate-600 mt-1 max-w-xl">
                        Legal entities within the SY Homes group — Parent, SPVs, ConstructionCos and JV vehicles.
                    </p>
                </div>
                <Button
                    onClick={() => navigate("/entities/new")}
                    className="bg-slate-900 hover:bg-slate-800 text-white"
                    data-testid="new-entity-button"
                >
                    <Plus size={16} strokeWidth={1.75} className="mr-1.5" />
                    New Entity
                </Button>
            </header>

            <section className="bg-white border border-slate-200 rounded-lg shadow-sm">
                {/* Filter bar */}
                <div className="px-6 py-4 border-b border-slate-200 bg-slate-50/60 flex flex-wrap items-center gap-3">
                    <form
                        onSubmit={onSearchSubmit}
                        className="relative flex-1 min-w-[240px] max-w-md"
                        data-testid="entities-search-form"
                    >
                        <Search
                            size={14}
                            strokeWidth={1.75}
                            className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
                        />
                        <Input
                            value={searchValue}
                            onChange={(e) => setSearchValue(e.target.value)}
                            placeholder="Search name or legal name…"
                            className="pl-9 h-9 bg-white"
                            data-testid="entities-search-input"
                        />
                    </form>

                    <select
                        value={type}
                        onChange={(e) => setParam("type", e.target.value)}
                        className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="filter-type"
                    >
                        <option value="">All types</option>
                        {enums?.entity_types.map((t) => (
                            <option key={t} value={t}>
                                {displayEnum(t)}
                            </option>
                        ))}
                    </select>

                    <select
                        value={status}
                        onChange={(e) => setParam("status", e.target.value)}
                        className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                        data-testid="filter-status"
                    >
                        <option value="">Active + Dormant</option>
                        {enums?.entity_statuses.map((s) => (
                            <option key={s} value={s}>
                                {displayEnum(s)}
                            </option>
                        ))}
                    </select>

                    {filterChips.length > 0 && (
                        <button
                            type="button"
                            onClick={() => setParams(new URLSearchParams())}
                            className="text-xs text-slate-600 hover:text-slate-900 underline decoration-dotted"
                            data-testid="clear-filters-button"
                        >
                            Clear all
                        </button>
                    )}

                    <div className="ml-auto text-xs text-slate-500 tabular font-mono">
                        {loading ? (
                            <span className="flex items-center gap-1.5">
                                <Loader2 size={12} className="animate-spin" />
                                Loading…
                            </span>
                        ) : (
                            <>
                                {data.total} {data.total === 1 ? "entity" : "entities"}
                            </>
                        )}
                    </div>
                </div>

                {filterChips.length > 0 && (
                    <div className="px-6 pt-3 flex flex-wrap gap-2" data-testid="filter-chips">
                        {filterChips.map((c) => (
                            <span
                                key={c.key}
                                className="inline-flex items-center gap-1.5 rounded-full bg-slate-100 border border-slate-200 pl-3 pr-1 py-0.5 text-xs text-slate-700"
                            >
                                {c.label}
                                <button
                                    className="h-5 w-5 rounded-full hover:bg-slate-200 flex items-center justify-center"
                                    onClick={() => setParam(c.key, "")}
                                    data-testid={`remove-chip-${c.key}`}
                                >
                                    <X size={11} />
                                </button>
                            </span>
                        ))}
                    </div>
                )}

                {/* Table */}
                <div className="overflow-x-auto">
                    <table className="w-full text-sm" data-testid="entities-table">
                        <thead>
                            <tr className="bg-slate-50 border-y border-slate-200">
                                {COLUMNS.map((c) => (
                                    <th
                                        key={c.key}
                                        className={`text-left px-4 py-3 text-[11px] font-semibold uppercase tracking-widest text-slate-500 ${c.className ?? ""}`}
                                    >
                                        {c.sortable ? (
                                            <button
                                                onClick={() => toggleSort(c.key)}
                                                className="inline-flex items-center gap-1 hover:text-slate-900"
                                                data-testid={`sort-${c.key}`}
                                            >
                                                {c.label}
                                                {sort === c.key && (
                                                    dir === "asc" ? (
                                                        <ChevronUp size={12} />
                                                    ) : (
                                                        <ChevronDown size={12} />
                                                    )
                                                )}
                                            </button>
                                        ) : (
                                            c.label
                                        )}
                                    </th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {loading && data.items.length === 0 && (
                                Array.from({ length: 4 }).map((_, i) => (
                                    <tr key={i} className="border-b border-slate-200">
                                        {COLUMNS.map((c) => (
                                            <td key={c.key} className="px-4 py-3">
                                                <div className="h-3 w-24 rounded bg-slate-200 animate-pulse" />
                                            </td>
                                        ))}
                                    </tr>
                                ))
                            )}
                            {!loading && data.items.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={COLUMNS.length}
                                        className="px-4 py-16 text-center text-slate-500"
                                        data-testid="entities-empty-state"
                                    >
                                        <div className="font-heading text-lg text-slate-700">
                                            No entities match these filters.
                                        </div>
                                        <p className="text-sm mt-1">
                                            Try clearing filters, or{" "}
                                            <Link
                                                to="/entities/new"
                                                className="underline decoration-dotted text-slate-900"
                                                data-testid="empty-state-new-link"
                                            >
                                                create a new entity
                                            </Link>
                                            .
                                        </p>
                                    </td>
                                </tr>
                            )}
                            {data.items.map((e) => (
                                <tr
                                    key={e.id}
                                    onClick={() => navigate(`/entities/${e.id}`)}
                                    className="border-b border-slate-200 hover:bg-slate-50/80 cursor-pointer transition-colors"
                                    data-testid={`entity-row-${e.id}`}
                                >
                                    <td className="px-4 py-3">
                                        <div className="font-medium text-slate-900">
                                            {e.name}
                                        </div>
                                        <div className="text-xs text-slate-500">
                                            {e.legal_name}
                                        </div>
                                    </td>
                                    <td className="px-4 py-3 text-slate-700">
                                        {displayEnum(e.entity_type)}
                                    </td>
                                    <td className="px-4 py-3 mono tabular text-slate-700">
                                        {formatCompaniesHouse(e.companies_house_number)}
                                    </td>
                                    <td className="px-4 py-3 mono tabular text-slate-700">
                                        {e.vat_number
                                            ? formatVATNumber(e.vat_number)
                                            : "—"}
                                    </td>
                                    <td className="px-4 py-3">
                                        <EntityStatusBadge status={e.status} />
                                    </td>
                                    <td className="px-4 py-3 mono tabular text-slate-700">
                                        {formatYearEnd(e.year_end)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>

                {/* Pagination */}
                <div className="px-6 py-3 border-t border-slate-200 flex items-center justify-between text-xs text-slate-600">
                    <div data-testid="pagination-summary">
                        Page <span className="mono tabular">{page}</span> of{" "}
                        <span className="mono tabular">{totalPages}</span>
                        {" · "}
                        <span className="mono tabular">{pageSize}</span> per page
                    </div>
                    <div className="flex items-center gap-2">
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page <= 1}
                            onClick={() => setParam("page", String(page - 1))}
                            data-testid="page-prev"
                        >
                            Previous
                        </Button>
                        <Button
                            variant="outline"
                            size="sm"
                            disabled={page >= totalPages}
                            onClick={() => setParam("page", String(page + 1))}
                            data-testid="page-next"
                        >
                            Next
                        </Button>
                    </div>
                </div>
            </section>
        </div>
    );
}
