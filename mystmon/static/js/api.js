const MystMonApi = (() => {
    const cache = new Map();

    async function fetchJson(path) {
        const response = await fetch(path, {
            headers: { 'Accept': 'application/json' },
            cache: 'no-store',
        });
        if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}`);
        }
        return response.json();
    }

    async function cached(key, path) {
        if (cache.has(key)) return cache.get(key);
        const promise = fetchJson(path);
        cache.set(key, promise);
        try {
            return await promise;
        } catch (err) {
            cache.delete(key);
            throw err;
        }
    }

    return {
        clearCache() {
            cache.clear();
        },
        async config() { return cached('ui-config', '/api/v1/ui/config'); },
        async home() { return cached('ui-home', '/api/v1/ui/home'); },
        async collectorsStatus() { return cached('collectors-status', '/api/v1/collectors/status'); },
        async historyOverall(limit = 100) { return cached(`history-overall:${limit}`, `/api/v1/history/overall?limit=${encodeURIComponent(limit)}`); },
        async historyDelta(hours = 24) { return cached(`history-delta:${hours}`, `/api/v1/history/delta?hours=${encodeURIComponent(hours)}`); },
        async historyLatest() { return cached('history-latest', '/api/v1/history/latest'); },
        async historyNodes(latestOnly = true, limit = 100, offset = 0) {
            const qs = new URLSearchParams({ latest_only: String(latestOnly), limit: String(limit), offset: String(offset) });
            return cached(`history-nodes:${qs.toString()}`, `/api/v1/history/nodes?${qs.toString()}`);
        },
        async historyNode(node, limit = 100, offset = 0, hours = null) {
            const qs = new URLSearchParams({ limit: String(limit), offset: String(offset) });
            if (hours !== null && hours !== undefined) qs.set('hours', String(hours));
            return cached(`history-node:${node}:${qs.toString()}`, `/api/v1/history/nodes/${encodeURIComponent(node)}?${qs.toString()}`);
        },
        async snapshot() { return fetchJson('/api/v1/snapshot'); },
    };
})();
