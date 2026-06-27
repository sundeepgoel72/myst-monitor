const MystMonUtils = {
    clearCache() {},
    showToast(message) {
        if (message) {
            console.warn(message);
        }
    },
    formatEarnings(value) {
        if (value === null || value === undefined || value === '') return '-';
        const num = Number(value);
        if (!Number.isFinite(num)) return String(value);
        return num.toFixed(num >= 10 ? 2 : 4);
    },
    formatQuality(value) {
        if (value === null || value === undefined || value === '') {
            return { class: 'text-gray-500', value: '-' };
        }
        const num = Number(value);
        if (!Number.isFinite(num)) {
            return { class: 'text-gray-500', value: String(value) };
        }
        if (num >= 3) return { class: 'text-green-600', value: num.toFixed(1) };
        if (num >= 1) return { class: 'text-amber-600', value: num.toFixed(1) };
        return { class: 'text-red-600', value: num.toFixed(1) };
    },
    formatUptimeMinutes(value) {
        if (value === null || value === undefined || value === '') return '-';
        const hours = Number(value) / 60;
        return Number.isFinite(hours) ? `${hours.toFixed(1)}h` : '-';
    },
    formatRelativeTime(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString();
    },
    formatDateTime(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return String(value);
        return date.toLocaleString();
    },
    formatNumber(value, digits = 2) {
        const num = Number(value);
        return Number.isFinite(num) ? num.toFixed(digits) : '-';
    },
    escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },
    truncate(value, length) {
        const text = String(value ?? '');
        return text.length <= length ? text : `${text.slice(0, length)}...`;
    },
    getNodeStatus(online, running) {
        if (online === true || online === 1) return { value: 'online', label: 'Online', dotClass: 'bg-green-500', textClass: 'text-green-700' };
        if (online === false || online === 0) return { value: 'offline', label: 'Offline', dotClass: 'bg-red-500', textClass: 'text-red-700' };
        if (running === true || running === 1) return { value: 'running', label: 'Running', dotClass: 'bg-blue-500', textClass: 'text-blue-700' };
        if (running === false || running === 0) return { value: 'stopped', label: 'Stopped', dotClass: 'bg-gray-500', textClass: 'text-gray-700' };
        return { value: 'unknown', label: 'Unknown', dotClass: 'bg-gray-400', textClass: 'text-gray-600' };
    },
    copyToClipboard(text) {
        if (navigator.clipboard?.writeText) {
            navigator.clipboard.writeText(text).catch(() => {});
        }
    },
    getChartColor(index = 0) {
        const colors = [
            'rgb(37, 99, 235)',
            'rgb(5, 150, 105)',
            'rgb(202, 138, 4)',
            'rgb(220, 38, 38)',
            'rgb(124, 58, 237)',
            'rgb(8, 145, 178)',
            'rgb(234, 88, 12)',
        ];
        return colors[index % colors.length];
    },
};

function debounce(fn, wait = 0) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), wait);
    };
}
