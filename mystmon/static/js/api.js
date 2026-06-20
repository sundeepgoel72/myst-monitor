const MystMonApi = {
    clearCache() {},
    async config() { return {}; },
    async collectorsStatus() { return { collectors: {} }; },
    async historyOverall() { return []; },
    async historyDelta() { return { fleet: {}, nodes: [] }; },
    async historyLatest() { return {}; },
    async historyNodes() { return { nodes: [] }; },
    async historyNode() { return { history: [] }; },
    async snapshot() { return { nodes: [] }; },
};
