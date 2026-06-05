/**
 * Utility functions for MystMon UI
 */

// Format numbers with appropriate precision
function formatNumber(value, decimals = 2) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    if (value === 0) return '0';
    
    const abs = Math.abs(value);
    if (abs >= 1e12) return (value / 1e12).toFixed(decimals) + 'T';
    if (abs >= 1e9) return (value / 1e9).toFixed(decimals) + 'B';
    if (abs >= 1e6) return (value / 1e6).toFixed(decimals) + 'M';
    if (abs >= 1e3) return (value / 1e3).toFixed(decimals) + 'K';
    if (abs < 0.01) return value.toFixed(6);
    return value.toFixed(decimals);
}

// Format earnings (MYST tokens)
function formatEarnings(value) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    return formatNumber(value, 4) + ' MYST';
}

// Format duration in seconds to human readable
function formatDuration(seconds) {
    if (seconds === null || seconds === undefined || isNaN(seconds)) return '-';
    if (seconds < 60) return `${Math.round(seconds)}s`;
    if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
    if (seconds < 86400) return `${(seconds / 3600).toFixed(1)}h`;
    return `${(seconds / 86400).toFixed(1)}d`;
}

// Format uptime minutes to human readable
function formatUptimeMinutes(minutes) {
    if (minutes === null || minutes === undefined || isNaN(minutes)) return '-';
    if (minutes < 60) return `${Math.round(minutes)}m`;
    if (minutes < 1440) return `${(minutes / 60).toFixed(1)}h`;
    return `${(minutes / 1440).toFixed(1)}d`;
}

// Format timestamp to relative time
function formatRelativeTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return '-';
    
    const now = new Date();
    const diff = now - date;
    
    if (diff < 60000) return 'Just now';
    if (diff < 3600000) return `${Math.round(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.round(diff / 3600000)}h ago`;
    if (diff < 604800000) return `${Math.round(diff / 86400000)}d ago`;
    
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

// Format timestamp to local string
function formatDateTime(timestamp) {
    if (!timestamp) return '-';
    const date = new Date(timestamp);
    if (isNaN(date.getTime())) return '-';
    return date.toLocaleString(undefined, { 
        year: 'numeric', 
        month: 'short', 
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

// Truncate string with ellipsis
function truncate(str, length = 20) {
    if (!str) return '-';
    if (str.length <= length) return str;
    return str.substring(0, length - 1) + '…';
}

// Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Throttle function
function throttle(func, limit) {
    let inThrottle;
    return function(...args) {
        if (!inThrottle) {
            func(...args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Copy text to clipboard
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        showToast('Copied to clipboard', 'success');
    } catch (err) {
        showToast('Failed to copy', 'error');
    }
}

// Show toast notification
function showToast(message, type = 'info', duration = 5000) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
        <svg class="w-5 h-5 mr-3 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
            ${getToastIcon(type)}
        </svg>
        <span class="flex-1">${escapeHtml(message)}</span>
        <button class="ml-4 text-current opacity-50 hover:opacity-100" onclick="this.parentElement.remove()">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
                <path d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"/>
            </svg>
        </button>
    `;
    
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.animation = 'slide-in 0.3s ease-out reverse';
        setTimeout(() => toast.remove(), 300);
    }, duration);
}

function getToastIcon(type) {
    switch (type) {
        case 'success':
            return '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>';
        case 'error':
            return '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>';
        case 'warning':
            return '<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>';
        default:
            return '<path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/>';
    }
}

// Escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Get UI path from base URL
function getUiPath() {
    const base = document.querySelector('html').getAttribute('data-ui-path') || '/ui';
    return base;
}

// Format quality score with color
function formatQuality(quality) {
    if (quality === null || quality === undefined || isNaN(quality)) {
        return { text: '-', class: 'text-gray-400 dark:text-gray-500' };
    }
    const q = Math.round(quality);
    if (q >= 80) return { text: q, class: 'text-green-600 dark:text-green-400' };
    if (q >= 50) return { text: q, class: 'text-yellow-600 dark:text-yellow-400' };
    return { text: q, class: 'text-red-600 dark:text-red-400' };
}

// Get status badge HTML
function getStatusBadge(online, running) {
    if (online) {
        return `<span class="status-online"><svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/></svg>Online</span>`;
    }
    return `<span class="status-offline"><svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>Offline</span>`;
}

// Initialize theme toggle
function initThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    const sunIcon = document.getElementById('theme-icon-sun');
    const moonIcon = document.getElementById('theme-icon-moon');
    const systemIcon = document.getElementById('theme-icon-system');
    const html = document.documentElement;
    
    function updateIcons(theme) {
        sunIcon.classList.add('hidden');
        moonIcon.classList.add('hidden');
        systemIcon.classList.add('hidden');
        
        if (theme === 'light') sunIcon.classList.remove('hidden');
        else if (theme === 'dark') moonIcon.classList.remove('hidden');
        else systemIcon.classList.remove('hidden');
    }
    
    function getTheme() {
        return localStorage.getItem('theme') || 'system';
    }
    
    function setTheme(theme) {
        localStorage.setItem('theme', theme);
        html.setAttribute('data-theme', theme);
        
        if (theme === 'dark' || (theme === 'system' && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
            html.classList.add('dark');
        } else {
            html.classList.remove('dark');
        }
        updateIcons(theme);
    }
    
    // Initialize
    const currentTheme = getTheme();
    setTheme(currentTheme);
    
    // Toggle on click
    toggle.addEventListener('click', () => {
        const themes = ['light', 'dark', 'system'];
        const current = getTheme();
        const next = themes[(themes.indexOf(current) + 1) % themes.length];
        setTheme(next);
    });
    
    // Listen for system theme changes
    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (getTheme() === 'system') {
            setTheme('system');
        }
    });
}

// Initialize mobile menu
function initMobileMenu() {
    const btn = document.getElementById('mobile-menu-btn');
    const menu = document.getElementById('mobile-menu');
    const openIcon = document.getElementById('menu-open');
    const closeIcon = document.getElementById('menu-close');
    
    if (!btn || !menu) return;
    
    btn.addEventListener('click', () => {
        const isOpen = menu.classList.toggle('hidden');
        openIcon.classList.toggle('hidden', !isOpen);
        closeIcon.classList.toggle('hidden', isOpen);
    });
    
    // Close on link click
    menu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            menu.classList.add('hidden');
            openIcon.classList.remove('hidden');
            closeIcon.classList.add('hidden');
        });
    });
}

// Initialize connection monitor
function initConnectionMonitor() {
    const indicator = document.getElementById('status-indicator');
    const text = document.getElementById('status-text');
    
    async function checkConnection() {
        try {
            const response = await fetch('/health', { cache: 'no-cache' });
            if (response.ok) {
                indicator.className = 'w-2 h-2 rounded-full bg-green-500';
                text.textContent = 'Connected';
            } else {
                throw new Error('Health check failed');
            }
        } catch (err) {
            indicator.className = 'w-2 h-2 rounded-full bg-red-500';
            text.textContent = 'Disconnected';
        }
    }
    
    // Check immediately and then every 30 seconds
    checkConnection();
    setInterval(checkConnection, 30000);
}

// Update last update time in footer
function updateLastUpdateTime() {
    const el = document.getElementById('last-update');
    if (el) {
        el.textContent = `Last updated: ${new Date().toLocaleTimeString()}`;
    }
    setInterval(updateLastUpdateTime, 60000);
}

// Generate color for charts
function getChartColor(index, alpha = 1) {
    const colors = [
        [14, 165, 233],    // primary-500
        [217, 70, 239],    // myst-500
        [34, 197, 94],     // green-500
        [234, 179, 8],     // yellow-500
        [239, 68, 68],     // red-500
        [168, 85, 247],    // purple-500
        [249, 115, 22],    // orange-500
        [6, 182, 212],     // cyan-500
    ];
    const [r, g, b] = colors[index % colors.length];
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// Get Chart.js default options for dark mode
function getChartDefaults() {
    const isDark = document.documentElement.classList.contains('dark');
    const textColor = isDark ? '#9ca3af' : '#6b7280';
    const gridColor = isDark ? '#374151' : '#e5e7eb';
    
    return {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: false,
            },
            tooltip: {
                backgroundColor: isDark ? '#1f2937' : '#ffffff',
                titleColor: isDark ? '#f3f4f6' : '#111827',
                bodyColor: isDark ? '#d1d5db' : '#374151',
                borderColor: gridColor,
                borderWidth: 1,
                padding: 12,
                displayColors: false,
            },
        },
        scales: {
            x: {
                grid: {
                    display: false,
                },
                ticks: {
                    color: textColor,
                    font: { size: 11 },
                    maxRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 8,
                },
            },
            y: {
                grid: {
                    color: gridColor,
                    drawBorder: false,
                },
                ticks: {
                    color: textColor,
                    font: { size: 11 },
                    callback: function(value) {
                        if (value >= 1e6) return (value / 1e6).toFixed(1) + 'M';
                        if (value >= 1e3) return (value / 1e3).toFixed(1) + 'K';
                        return value;
                    },
                },
            },
        },
        interaction: {
            intersect: false,
            mode: 'index',
        },
        animation: {
            duration: 300,
        },
    };
}

// Update chart theme when system theme changes
function setupChartThemeListener(charts) {
    const observer = new MutationObserver(() => {
        const defaults = getChartDefaults();
        charts.forEach(chart => {
            chart.options.plugins.tooltip = defaults.plugins.tooltip;
            chart.options.scales.x.ticks.color = defaults.scales.x.ticks.color;
            chart.options.scales.y.ticks.color = defaults.scales.y.ticks.color;
            chart.options.scales.y.grid.color = defaults.scales.y.grid.color;
            chart.update('none');
        });
    });
    
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
    return observer;
}

// Export for use in other modules
window.MystMonUtils = {
    formatNumber,
    formatEarnings,
    formatDuration,
    formatUptimeMinutes,
    formatRelativeTime,
    formatDateTime,
    truncate,
    debounce,
    throttle,
    copyToClipboard,
    showToast,
    escapeHtml,
    getUiPath,
    formatQuality,
    getStatusBadge,
    getChartColor,
    getChartDefaults,
    setupChartThemeListener,
};
