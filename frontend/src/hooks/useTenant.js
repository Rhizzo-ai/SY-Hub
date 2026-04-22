import { useEffect, useState } from "react";
import { api } from "@/lib/api";

let cache = null;
let inflight = null;

export function useTenant() {
    const [tenant, setTenant] = useState(cache);
    const [loading, setLoading] = useState(!cache);
    useEffect(() => {
        if (cache) {
            setTenant(cache);
            setLoading(false);
            return;
        }
        if (!inflight) {
            inflight = api.get("/meta/tenant").then((r) => {
                cache = r.data;
                return r.data;
            });
        }
        inflight
            .then((d) => {
                setTenant(d);
            })
            .finally(() => setLoading(false));
    }, []);
    return { tenant, loading };
}

export function useEnums() {
    const [enums, setEnums] = useState(null);
    useEffect(() => {
        api.get("/meta/enums").then((r) => setEnums(r.data));
    }, []);
    return enums;
}
