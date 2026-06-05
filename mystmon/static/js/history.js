/**
 * History page logic
 */

let historyCharts = {};
let collectionsData = [];
let currentRange = 24;
let comparisonRange = 'none';

async function refreshHistory() {
    const btn = document.getElementById('refresh-btn');
    if (btn) btn.disabled = true;
    
    try {
        await loadHistoryData();
    } catch (err) {
        console.error('History refresh failed:', err);
        MystMonUtils.showToast('Failed to refresh history', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function loadHistoryData() {
    try {
        const [overall, delta] = await Promise.all([
            MystMonApi.historyOverall(500),
            MystMonApi.historyDelta(currentRange),
        ]);
        
        collectionsData = overall.collections || [];
        renderSummary(delta);
        renderFleetTrendsChart(delta);
        renderCollectionsTable();
        
    } catch (err) {
        console.error('Failed to load history data:', err);
    }
}

function renderSummary(delta) {
    const fleet = delta.fleet || {};
    const current = fleet.current || {};
    const prior = fleet.prior || {};
    
    const container = document.getElementById('history-summary');
    if (!container) return;
    
    const cards = [
        { label: 'Nodes', value: current.nodes || 0, change: formatDelta(current.nodes, prior.nodes), icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z' },
        { label: 'Online', value: current.online || 0, change: formatDelta(current.online, prior.online), icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
        { label: 'Avg Quality', value: current.quality_avg !== null ? Math.round(current.quality_avg) : '-', change: formatDelta(current.quality_avg, prior.quality_avg), icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z' },
        { label: 'Earnings (24h)', value: MystMonUtils.formatEarnings(current.earnings_total), change: formatDelta(current.earnings_total, prior.earnings_total, true), icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    ];
    
    container.innerHTML = cards.map(card => `
        <div class="card">
            <div class="card-body">
                <div class="flex items-center justify-between">
                    <div>
                        <p class="text-sm text-gray-500 dark:text-gray-400">${card.label}</p>
                        <p class="text-2xl font-bold text-gray-900 dark:text-white">${card.value}</p>
                        ${card.change ? `<p class="text-sm mt-1">${card.change}</p>` : ''}
                    </div>
                    <div class="w-12 h-12 rounded-lg bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
                        <svg class="w-6 h-6 text-primary-600 dark:text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${card.icon}"/>
                        </svg>
                    </div>
                </div>
            </div>
        </div>
    `).join('');
}

function formatDelta(current, prior, isEarnings = false) {
    if (current === null || current === undefined || prior === null || prior === undefined) {
        return '<span class="text-gray-400 dark:text-gray-500">No prior data</span>';
    }
    const diff = current - prior;
    if (diff === 0) return '<span class="text-gray-400 dark:text-gray-500">No change</span>';
    
    const formatter = isEarnings ? MystMonUtils.formatEarnings : (v => (v > 0 ? '+' : '') + v);
    const color = diff > 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400';
    const icon = diff > 0 
        ? '<svg class="w-3 h-3 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 10l7-7m0 0l7 7m-7-7v18"/></svg>'
        : '<svg class="w-3 h-3 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3"/></svg>';
    
    return `<span class="${color} flex items-center space-x-1">${icon}<span>${formatter(diff)}</span></span>`;
}

function renderFleetTrendsChart(delta) {
    const nodes = delta.nodes || [];
    if (!nodes.length) return;
    
    // For now, we'll show a simple bar chart of node deltas
    // In a full implementation, you'd fetch time series data
    
    const ctx = document.getElementById('fleet-trends-chart');
    if (!ctx) return;
    
    if (historyCharts['fleet-trends']) {
        historyCharts['fleet-trends'].destroy();
    }
    
    const metrics = getSelectedMetrics();
    const datasets = [];
    const colors = [
        'rgb(14, 165, 233)',    // primary
        'rgb(217, 70, 239)',    // myst
        'rgb(34, 197, 94)',     // green
        'rgb(239, 68, 68)',     // red
        'rgb(234, 179, 8)',     // yellow
    ];
    
    metrics.forEach((metric, i) => {
        const data = nodes
            .filter(n => n.delta?.[metric] !== undefined)
            .map(n => ({ x: n.node_name, y: n.delta[metric] }))
            .sort((a, b) => b.y - a.y)
            .slice(0, 20); // Top 20
        
        if (data.length) {
            datasets.push({
                label: getMetricLabel(metric),
                data: data.map(d => d.y),
                backgroundColor: colors[i % colors.length],
                borderRadius: 4,
            });
        }
    });
    
    const isDark = document.documentElement.classList.contains('dark');
    const gridColor = isDark ? '#374151' : '#e5e7eb';
    const textColor = isDark ? '#9ca3af' : '#6b7280';
    
    historyCharts['fleet-trends'] = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: datasets[0]?.data.map((_, i) => nodes[i]?.node_name || '') || [],
            datasets,
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: true, position: 'top', labels: { color: textColor, font: { size: 11 } } },
                tooltip: {
                    backgroundColor: isDark ? '#1f2937' : '#ffffff',
                    titleColor: isDark ? '#f3f4f6' : '#111827',
                    bodyColor: isDark ? '#d1d5db' : '#374151',
                    borderColor: gridColor,
                    borderWidth: 1,
                },
            },
            scales: {
                x: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 } } },
                y: { grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } },
            },
        },
    });
}

function getSelectedMetrics() {
    const select = document.getElementById('metrics-select');
    if (!select) return ['online', 'quality', 'earnings'];
    return Array.from(select.selectedOptions).map(o => o.value);
}

function getMetricLabel(metric) {
    const labels = {
        online: 'Online Change',
        quality: 'Quality Change',
        earnings: 'Earnings Change',
        restarts: 'Restarts Change',
        errors: 'Errors Change',
    };
    return labels[metric] || metric;
}

function renderCollectionsTable() {
    const tbody = document.getElementById('collections-body');
    if (!tbody) return;
    
    if (!collectionsData.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-gray-500 dark:text-gray-400 py-4">No collection history</td></tr>';
        return;
    }
    
    tbody.innerHTML = collectionsData.slice(0, 50).map(c => {
        const counts = c.counts || {};
        const snapshot = c.snapshot || {};
        const mystnodes = snapshot.mystnodes || {};
        
        return `
            <tr class="border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800">
                <td class="py-2 px-3 text-sm">${MystMonUtils.formatDateTime(c.collected_at)}</td>
                <td class="py-2 px-3 text-sm font-mono">${c.snapshot?.collection_duration_ms ? c.snapshot.collection_duration_ms + 'ms' : '-'}</td>
                <td class="py-2 px-3 text-sm">${counts.myst || 0}</td>
                <td class="py-2 px-3 text-sm">${mystnodes.authenticated ? '✓' : '✗'}</td>
                <td class="py-2 px-3 text-sm">${counts.prometheus || 0}</td>
                <td class="py-2 px-3 text-sm">${counts.snmp || 0}</td>
                <td class="py-2 px-3">
                    <span class="px-2 py-1 text-xs rounded-full ${c.snapshot?.collection_error ? 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200' : 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'}">
                        ${c.snapshot?.collection_error ? 'Error' : 'OK'}
                    </span>
                </td>
            </tr>
        `;
    }).join('');
}

function onTimeRangeChange() {
    const select = document.getElementById('time-range');
    const customRange = document.getElementById('custom-range');
    
    if (select.value === 'custom') {
        customRange.classList.remove('hidden');
    } else {
        customRange.classList.add('hidden');
        currentRange = parseInt(select.value);
        refreshHistory();
    }
}

function updateCharts() {
    renderFleetTrendsChart({ nodes: [] }); // Would need to refetch with new params
}

function exportHistory() {
    const format = 'csv';
    const hours = currentRange;
    
    MystMonApi.historyExport(hours, format).then(blob => {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `mystmon_history_${hours}h.${format}`;
        a.click();
        window.URL.revokeObjectURL(url);
        MystMonUtils.showToast('History exported', 'success');
    }).catch(err => {
        MystMonUtils.showToast('Export failed: ' + err.message, 'error');
    });
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadHistoryData();
    
    // Custom range handler
    document.getElementById('range-start')?.addEventListener('change', () => {
        if (document.getElementById('time-range').value === 'custom') {
            // Would need to calculate hours from dates
        }
    });
    
    document.getElementById('range-end')?.addEventListener('change', () => {
        if (document.getElementById('time-range').value === 'custom') {
            // Would need to calculate hours from dates
        }
    });
});

// Cleanup
window.addEventListener('beforeunload', () => {
    Object.values(historyCharts).forEach(chart => chart.destroy());
});
