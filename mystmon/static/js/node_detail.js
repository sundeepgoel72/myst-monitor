/**
 * Node detail page logic
 */

const nodeKey = new URLSearchParams(window.location.search).get('node') || 
                window.location.pathname.split('/').pop();

let nodeCharts = {};
let nodeData = null;

async function refreshNodeDetail() {
    const btn = document.getElementById('refresh-btn');
    if (btn) btn.disabled = true;
    
    try {
        await loadNodeData();
    } catch (err) {
        console.error('Node detail refresh failed:', err);
        MystMonUtils.showToast('Failed to refresh node data', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function loadNodeData() {
    try {
        const [nodeHistory, snapshot] = await Promise.all([
            MystMonApi.historyNode(nodeKey, 200),
            MystMonApi.snapshot(),
        ]);
        
        // Find node in snapshot for current data
        const snapshotNode = snapshot.nodes?.find(n => n.name === nodeKey || n.identity === nodeKey);
        const portalNode = findPortalNode(snapshot, nodeKey);
        
        nodeData = {
            history: nodeHistory.history || [],
            current: snapshotNode,
            portal: portalNode,
        };
        
        renderOverview();
        renderMetricsCharts();
        renderLogs();
        renderEarnings();
        renderRawData();
        
    } catch (err) {
        console.error('Failed to load node data:', err);
        MystMonUtils.showToast('Failed to load node data', 'error');
    }
}

function findPortalNode(snapshot, key) {
    const mystnodes = snapshot.mystnodes;
    if (!mystnodes) return null;
    
    const nodes = mystnodes.endpoints?.nodes?.data?.nodes || [];
    return nodes.find(n => n.id === key || n.identity === key || n.name === key) || null;
}

function renderOverview() {
    if (!nodeData) return;
    
    const { current, portal } = nodeData;
    
    // Update header
    document.getElementById('node-name').textContent = current?.name || portal?.name || nodeKey;
    document.getElementById('node-identity').textContent = current?.identity || portal?.identity || 'Unknown identity';
    
    // Status badge
    const online = current?.running && (portal?.nodeStatus?.online || current?.api?.up);
    const statusBadge = document.getElementById('node-status-badge');
    if (statusBadge) {
        statusBadge.innerHTML = `
            <span class="w-3 h-3 rounded-full ${online ? 'bg-green-500' : 'bg-red-500'}"></span>
            <span class="text-sm font-medium ${online ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">
                ${online ? 'Online' : 'Offline'}
            </span>
        `;
    }
    
    // Metrics cards
    const metricsContainer = document.getElementById('node-metrics-cards');
    if (metricsContainer) {
        const quality = portal?.nodeStatus?.quality ?? current?.api?.metrics?.quality;
        const earnings = portal?.earnings?.[0]?.etherAmount ?? current?.api?.metrics?.earnings_total;
        const uptime = portal?.detail?.uptimeMinLast24H ?? current?.uptime_seconds;
        const restarts = current?.restart_count;
        
        metricsContainer.innerHTML = [
            { label: 'Quality', value: quality !== undefined ? Math.round(quality) : '-', icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z', class: quality !== undefined ? MystMonUtils.formatQuality(quality).class : '' },
            { label: 'Earnings (24h)', value: MystMonUtils.formatEarnings(earnings), icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
            { label: 'Uptime (24h)', value: MystMonUtils.formatUptimeMinutes(uptime), icon: 'M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z' },
            { label: 'Restarts', value: restarts || 0, icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15' },
        ].map(m => `
            <div class="card">
                <div class="card-body">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-sm text-gray-500 dark:text-gray-400">${m.label}</p>
                            <p class="text-2xl font-bold text-gray-900 dark:text-white ${m.class}">${m.value}</p>
                        </div>
                        <div class="w-12 h-12 rounded-lg bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
                            <svg class="w-6 h-6 text-primary-600 dark:text-primary-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="${m.icon}"/>
                            </svg>
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }
    
    // Container info
    if (current) {
        document.getElementById('ci-name').textContent = current.name || '-';
        document.getElementById('ci-host').textContent = current.host || '-';
        document.getElementById('ci-image').textContent = current.image || '-';
        document.getElementById('ci-network').textContent = current.network || '-';
        document.getElementById('ci-ports').textContent = current.ports ? JSON.stringify(current.ports) : '-';
        document.getElementById('ci-uptime').textContent = MystMonUtils.formatDuration(current.uptime_seconds);
        document.getElementById('ci-restarts').textContent = current.restart_count || 0;
        document.getElementById('ci-created').textContent = MystMonUtils.formatDateTime(current.created_at);
    }
    
    // Portal info
    if (portal) {
        document.getElementById('pi-id').textContent = portal.id || '-';
        document.getElementById('pi-local-ip').textContent = portal.localIp || '-';
        document.getElementById('pi-public-ip').textContent = portal.publicIp || '-';
        document.getElementById('pi-version').textContent = portal.version || '-';
        document.getElementById('pi-nat').textContent = portal.natType || '-';
        document.getElementById('pi-location').textContent = portal.location || '-';
        document.getElementById('pi-match').innerHTML = nodeData.current?.local_match 
            ? '<span class="text-green-600 dark:text-green-400">Matched</span>' 
            : '<span class="text-gray-500 dark:text-gray-400">Unmatched</span>';
    }
    
    // API endpoints
    renderApiEndpoints(current?.api?.endpoints);
}

function renderApiEndpoints(endpoints) {
    const tbody = document.getElementById('api-endpoints-body');
    if (!tbody) return;
    
    if (!endpoints || Object.keys(endpoints).length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" class="text-center text-gray-500 dark:text-gray-400 py-4">No API endpoint data</td></tr>';
        return;
    }
    
    tbody.innerHTML = Object.entries(endpoints).map(([name, data]) => `
        <tr class="border-b border-gray-200 dark:border-gray-700">
            <td class="py-2 px-3 font-mono text-sm">${MystMonUtils.escapeHtml(name)}</td>
            <td class="py-2 px-3">
                <span class="inline-flex items-center px-2 py-1 text-xs rounded-full ${data.ok ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200' : 'bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200'}">
                    ${data.ok ? 'OK' : 'Failed'}
                </span>
            </td>
            <td class="py-2 px-3 text-sm text-gray-500 dark:text-gray-400">${data.last_check ? MystMonUtils.formatRelativeTime(data.last_check) : '-'}</td>
            <td class="py-2 px-3 text-sm text-gray-500 dark:text-gray-400">${data.response_time_ms ? data.response_time_ms + 'ms' : '-'}</td>
        </tr>
    `).join('');
}

function renderMetricsCharts() {
    const history = nodeData?.history || [];
    if (!history.length) return;
    
    // Prepare time series data
    const qualityData = history
        .filter(h => h.quality !== null && h.quality !== undefined)
        .map(h => ({ x: new Date(h.collected_at), y: h.quality }))
        .sort((a, b) => a.x - b.x);
    
    const earningsData = history
        .filter(h => h.earnings_total !== null && h.earnings_total !== undefined)
        .map(h => ({ x: new Date(h.collected_at), y: h.earnings_total }))
        .sort((a, b) => a.x - b.x);
    
    const uptimeData = history
        .filter(h => h.uptime_minutes_24h !== null && h.uptime_minutes_24h !== undefined)
        .map(h => ({ x: new Date(h.collected_at), y: h.uptime_minutes_24h / 60 })) // Convert to hours
        .sort((a, b) => a.x - b.x);
    
    const restartsData = history
        .filter(h => h.restart_count !== null && h.restart_count !== undefined)
        .map(h => ({ x: new Date(h.collected_at), y: h.restart_count }))
        .sort((a, b) => a.x - b.x);
    
    // Create charts
    createNodeChart('quality-chart', qualityData, 'Quality Score', MystMonUtils.getChartColor(0), { max: 100, min: 0 });
    createNodeChart('earnings-chart', earningsData, 'Earnings (MYST)', MystMonUtils.getChartColor(1));
    createNodeChart('uptime-chart', uptimeData, 'Uptime (hours)', MystMonUtils.getChartColor(2), { max: 24, min: 0 });
    createNodeChart('restarts-chart', restartsData, 'Restarts', MystMonUtils.getChartColor(3), { type: 'bar' });
}

function createNodeChart(canvasId, data, label, color, options = {}) {
    const ctx = document.getElementById(canvasId);
    if (!ctx || !data.length) return;
    
    if (nodeCharts[canvasId]) {
        nodeCharts[canvasId].destroy();
    }
    
    const isDark = document.documentElement.classList.contains('dark');
    const gridColor = isDark ? '#374151' : '#e5e7eb';
    const textColor = isDark ? '#9ca3af' : '#6b7280';
    
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, color.replace('1)', '0.3)'));
    gradient.addColorStop(1, color.replace('1)', '0)'));
    
    const config = {
        type: options.type || 'line',
        data: {
            datasets: [{
                label,
                data,
                borderColor: color,
                backgroundColor: gradient,
                fill: true,
                tension: 0.3,
                pointRadius: 0,
                pointHoverRadius: 4,
                borderWidth: 2,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: isDark ? '#1f2937' : '#ffffff',
                    titleColor: isDark ? '#f3f4f6' : '#111827',
                    bodyColor: isDark ? '#d1d5db' : '#374151',
                    borderColor: gridColor,
                    borderWidth: 1,
                    padding: 12,
                    displayColors: false,
                    callbacks: {
                        label: (context) => {
                            let value = context.parsed.y;
                            if (label.includes('Earnings')) value = MystMonUtils.formatEarnings(value);
                            else if (label.includes('Uptime')) value = value.toFixed(1) + 'h';
                            else if (label === 'Quality Score') value = value.toFixed(1);
                            return `${label}: ${value}`;
                        },
                    },
                },
            },
            scales: {
                x: {
                    type: 'time',
                    time: { unit: 'hour', displayFormats: { hour: 'HH:mm' } },
                    grid: { display: false },
                    ticks: { color: textColor, font: { size: 11 }, maxTicksLimit: 8 },
                },
                y: {
                    min: options.min,
                    max: options.max,
                    grid: { color: gridColor, drawBorder: false },
                    ticks: { 
                        color: textColor, 
                        font: { size: 11 },
                        callback: (value) => {
                            if (label.includes('Earnings')) return MystMonUtils.formatNumber(value, 2);
                            return value;
                        },
                    },
                },
            },
            interaction: { intersect: false, mode: 'index' },
            animation: { duration: 300 },
        },
    };
    
    nodeCharts[canvasId] = new Chart(ctx, config);
}

function renderLogs() {
    const history = nodeData?.history || [];
    if (!history.length) return;
    
    const latest = history[0];
    const logs = latest.log_counts || {};
    
    document.getElementById('log-errors').textContent = logs.error_or_warning || 0;
    document.getElementById('log-identity').textContent = logs.identity_warning || 0;
    document.getElementById('log-promises').textContent = logs.promise || 0;
    document.getElementById('log-sessions').textContent = logs.session || 0;
    
    // Logs chart
    const logTypes = ['error_or_warning', 'identity_warning', 'promise', 'session'];
    const logLabels = ['Errors/Warnings', 'Identity Warnings', 'Promises', 'Sessions'];
    const logColors = [MystMonUtils.getChartColor(3), MystMonUtils.getChartColor(4), MystMonUtils.getChartColor(5), MystMonUtils.getChartColor(6)];
    
    const datasets = logTypes.map((type, i) => ({
        label: logLabels[i],
        data: history
            .filter(h => h.log_counts?.[type] !== undefined)
            .map(h => ({ x: new Date(h.collected_at), y: h.log_counts[type] }))
            .sort((a, b) => a.x - b.x),
        borderColor: logColors[i],
        backgroundColor: logColors[i].replace('1)', '0.1)'),
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 3,
    })).filter(d => d.data.length > 0);
    
    if (datasets.length > 0) {
        const ctx = document.getElementById('logs-chart');
        if (ctx) {
            if (nodeCharts['logs-chart']) nodeCharts['logs-chart'].destroy();
            
            const isDark = document.documentElement.classList.contains('dark');
            const gridColor = isDark ? '#374151' : '#e5e7eb';
            const textColor = isDark ? '#9ca3af' : '#6b7280';
            
            nodeCharts['logs-chart'] = new Chart(ctx, {
                type: 'line',
                data: { datasets },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
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
                        x: { type: 'time', time: { unit: 'hour' }, grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } },
                        y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 }, precision: 0 } },
                    },
                    interaction: { intersect: false, mode: 'index' },
                },
            });
        }
    }
}

function renderEarnings() {
    const portal = nodeData?.portal;
    if (!portal) {
        document.getElementById('earnings-summary').innerHTML = '<div class="col-span-3 text-center text-gray-500 dark:text-gray-400 py-8">No portal earnings data available</div>';
        return;
    }
    
    // Summary cards
    const totalEarnings = portal.earnings?.reduce((sum, e) => sum + (e.etherAmount || 0), 0) || 0;
    const totalSessions = portal.earnings?.reduce((sum, e) => sum + (e.sessionCount || 0), 0) || 0;
    const totalTransferred = portal.earnings?.reduce((sum, e) => sum + (e.transferredBytes || 0), 0) || 0;
    
    document.getElementById('earnings-summary').innerHTML = [
        { label: 'Total Earnings', value: MystMonUtils.formatEarnings(totalEarnings) },
        { label: 'Total Sessions', value: totalSessions.toLocaleString() },
        { label: 'Total Transferred', value: formatBytes(totalTransferred) },
    ].map(m => `
        <div class="card">
            <div class="card-body text-center">
                <p class="text-sm text-gray-500 dark:text-gray-400">${m.label}</p>
                <p class="text-2xl font-bold text-gray-900 dark:text-white">${m.value}</p>
            </div>
        </div>
    `).join('');
    
    // Earnings history chart
    if (portal.earnings?.length) {
        const earningsHistory = portal.earnings
            .map(e => ({ x: new Date(e.timestamp), y: e.etherAmount || 0 }))
            .sort((a, b) => a.x - b.x);
        
        const ctx = document.getElementById('earnings-history-chart');
        if (ctx) {
            if (nodeCharts['earnings-history-chart']) nodeCharts['earnings-history-chart'].destroy();
            
            const isDark = document.documentElement.classList.contains('dark');
            const gridColor = isDark ? '#374151' : '#e5e7eb';
            const textColor = isDark ? '#9ca3af' : '#6b7280';
            
            const gradient = ctx.createLinearGradient(0, 0, 0, 200);
            gradient.addColorStop(0, 'rgba(14, 165, 233, 0.3)');
            gradient.addColorStop(1, 'rgba(14, 165, 233, 0)');
            
            nodeCharts['earnings-history-chart'] = new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Earnings (MYST)',
                        data: earningsHistory,
                        borderColor: 'rgb(14, 165, 233)',
                        backgroundColor: gradient,
                        fill: true,
                        tension: 0.3,
                        pointRadius: 0,
                        pointHoverRadius: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (context) => `Earnings: ${MystMonUtils.formatEarnings(context.parsed.y)}`,
                            },
                        },
                    },
                    scales: {
                        x: { type: 'time', grid: { display: false }, ticks: { color: textColor, font: { size: 11 } } },
                        y: { grid: { color: gridColor }, ticks: { color: textColor, font: { size: 11 }, callback: (v) => MystMonUtils.formatEarnings(v) } },
                    },
                },
            });
        }
    }
    
    // Earnings details table
    const tbody = document.getElementById('earnings-details-body');
    if (tbody && portal.earnings?.length) {
        tbody.innerHTML = portal.earnings
            .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
            .slice(0, 50)
            .map(e => `
                <tr class="border-b border-gray-200 dark:border-gray-700">
                    <td class="py-2 px-3 text-sm">${MystMonUtils.formatDateTime(e.timestamp)}</td>
                    <td class="py-2 px-3 text-sm font-mono">${MystMonUtils.formatEarnings(e.etherAmount)}</td>
                    <td class="py-2 px-3 text-sm">${e.sessionCount || 0}</td>
                    <td class="py-2 px-3 text-sm">${formatBytes(e.transferredBytes)}</td>
                </tr>
            `).join('');
    }
}

function formatBytes(bytes) {
    if (!bytes) return '0 B';
    const units = ['B', 'KB', 'MB', 'GB', 'TB'];
    let i = 0;
    while (bytes >= 1024 && i < units.length - 1) {
        bytes /= 1024;
        i++;
    }
    return `${bytes.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
}

function renderRawData() {
    const pre = document.getElementById('raw-data');
    if (pre && nodeData) {
        pre.textContent = JSON.stringify(nodeData, null, 2);
    }
}

function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    
    // Update tab content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.toggle('hidden', content.id !== `tab-${tabName}`);
    });
    
    // Trigger chart resize for visible charts
    setTimeout(() => {
        Object.values(nodeCharts).forEach(chart => chart.resize());
    }, 50);
}

function copyRawData() {
    if (nodeData) {
        MystMonUtils.copyToClipboard(JSON.stringify(nodeData, null, 2));
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadNodeData();
});

// Cleanup
window.addEventListener('beforeunload', () => {
    Object.values(nodeCharts).forEach(chart => chart.destroy());
});
