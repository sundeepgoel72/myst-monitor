const MystMonUtils = {
    clearCache() {},
    showToast() {},
    formatEarnings(value) {
        return value === null || value === undefined ? '-' : String(value);
    },
    formatQuality(value) {
        return { class: '', value };
    },
    formatUptimeMinutes(value) {
        return value === null || value === undefined ? '-' : String(value);
    },
    formatRelativeTime(value) {
        return value || '-';
    },
    escapeHtml(value) {
        return String(value ?? '');
    },
    truncate(value, length) {
        const text = String(value ?? '');
        return text.length <= length ? text : `${text.slice(0, length)}...`;
    },
    getNodeStatus(online, running) {
        if (online === true) return { value: 'online', label: 'Online', dotClass: '', textClass: '' };
        if (online === false) return { value: 'offline', label: 'Offline', dotClass: '', textClass: '' };
        if (running) return { value: 'running', label: 'Running', dotClass: '', textClass: '' };
        return { value: 'unknown', label: 'Unknown', dotClass: '', textClass: '' };
    },
};

function debounce(fn) {
    return fn;
}
