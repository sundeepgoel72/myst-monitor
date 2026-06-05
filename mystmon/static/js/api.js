/**
 * API client for MystMon UI
 */

class ApiClient {
    constructor(basePath = '') {
        this.basePath = basePath;
        this.cache = new Map();
        this.pendingRequests = new Map();
    }
    
    async request(endpoint, options = {}) {
        const url = `${this.basePath}${endpoint}`;
        const cacheKey = `${options.method || 'GET'}:${url}:${JSON.stringify(options.body || {})}`;
        
        // Return cached response if available and not forced
        if (!options.force && this.cache.has(cacheKey)) {
            const cached = this.cache.get(cacheKey);
            if (Date.now() - cached.timestamp < 5000) { // 5 second cache
                return cached.data;
            }
        }
        
        // Deduplicate simultaneous requests
        if (this.pendingRequests.has(cacheKey)) {
            return this.pendingRequests.get(cacheKey);
        }
        
        const promise = this._doRequest(url, options);
        this.pendingRequests.set(cacheKey, promise);
        
        try {
            const data = await promise;
            this.cache.set(cacheKey, { data, timestamp: Date.now() });
            return data;
        } finally {
            this.pendingRequests.delete(cacheKey);
        }
    }
    
    async _doRequest(url, options) {
        const response = await fetch(url, {
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
            ...options,
        });
        
        if (!response.ok) {
            const error = await response.json().catch(() => ({ message: response.statusText }));
            throw new Error(error.message || `HTTP ${response.status}`);
        }
        
        const contentType = response.headers.get('content-type');
        if (contentType && contentType.includes('application/json')) {
            return response.json();
        }
        return response.text();
    }
    
    get(endpoint, params = {}) {
        const query = new URLSearchParams(params).toString();
        const url = query ? `${endpoint}?${query}` : endpoint;
        return this.request(url);
    }
    
    post(endpoint, data) {
        return this.request(endpoint, {
            method: 'POST',
            body: JSON.stringify(data),
        });
    }
    
    // Clear cache
    clearCache() {
        this.cache.clear();
    }
    
    // Invalidate specific endpoint
    invalidate(endpoint) {
        for (const key of this.cache.keys()) {
            if (key.includes(endpoint)) {
                this.cache.delete(key);
            }
        }
    }
}

// Create global API client instance
const api = new ApiClient('/api/v1');

// API methods
const Api = {
    // Health
    health: () => api.get('/health'),
    
    // Config
    config: () => api.get('/config'),
    
    // Readings
    readings: () => api.get('/readings'),
    
    // Snapshot
    snapshot: () => api.get('/snapshot'),
    
    // Collection
    collect: () => api.post('/collect', {}),
    
    // History
    historyLatest: () => api.get('/history/latest'),
    historyOverall: (limit = 100) => api.get('/history/overall', { limit }),
    historyDelta: (hours = 24) => api.get('/history/delta', { hours }),
    historyNodes: (latestOnly = true, limit = 100) => api.get('/history/nodes', { latest_only: latestOnly, limit }),
    historyNode: (node, limit = 100) => api.get(`/history/nodes/${encodeURIComponent(node)}`, { limit }),
    historyExport: (hours = 24, format = 'json') => api.get('/history/export', { hours, format }),
    
    // Telegram
    telegramTest: () => api.post('/telegram/test', {}),
    telegramReport: (hours = 24) => api.post('/telegram/report', { hours }),
    
    // UI-specific endpoints
    uiConfig: () => api.get('/ui/config'),
    collectorsStatus: () => api.get('/collectors/status'),
    systemInfo: () => api.get('/system/info'),
};

// Export for use in other modules
window.MystMonApi = Api;
