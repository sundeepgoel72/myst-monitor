/**
 * Dashboard page logic
 */

let dashboardCharts = {};
let refreshInterval = null;

async function refreshDashboard() {
    const btn = document.getElementById('refresh-btn');
    if (btn) btn.disabled = true;
    MystMonApi.clearCache();
    
    try {
        await Promise.all([
            loadSummaryCards(),
            loadTrendCharts(),
            loadAlerts(),
            loadCollectorsStatus(),
            loadQuickNodes(),
        ]);
    } catch (err) {
        console.error('Dashboard refresh failed:', err);
        MystMonUtils.showToast('Failed to refresh dashboard: ' + err.message, 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function loadSummaryCards() {
    try {
        const [delta, latest] = await Promise.all([
            MystMonApi.historyDelta(24),
            MystMonApi.historyLatest(),
        ]);
        
        const fleet = delta.fleet || {};
        const current = fleet.current || {};
        const prior = fleet.prior || {};
        const healthyNodes = pickMetric(current, ['online', 'running']);
        const priorHealthyNodes = pickMetric(prior, ['online', 'running']);
        const totalNodes = pickNumber(current.nodes, 0);
        const stoppedNodes = healthyNodes !== null ? totalNodes - healthyNodes : '-';
        const portalKnown = isKnownNumber(current.online);
        const statusLabel = portalKnown ? 'Online' : 'Running';
        const inactiveLabel = portalKnown ? 'Offline' : 'Stopped';
        
        const cards = [
            {
                id: 'card-nodes-total',
                label: 'Total Nodes',
                value: totalNodes,
                change: formatDelta(current.nodes, prior.nodes),
                icon: 'M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z',
            },
            {
                id: 'card-nodes-online',
                label: statusLabel,
                value: healthyNodes !== null ? healthyNodes : '-',
                change: formatDelta(healthyNodes, priorHealthyNodes),
                icon: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z',
            },
            {
                id: 'card-nodes-offline',
                label: inactiveLabel,
                value: stoppedNodes,
                change: '',
                icon: 'M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z',
            },
            {
                id: 'card-earnings',
                label: 'Earnings (24h)',
                value: MystMonUtils.formatEarnings(current.earnings_total),
                change: formatDelta(current.earnings_total, prior.earnings_total, true),
                icon: 'M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z',
            },
            {
                id: 'card-quality',
                label: 'Avg Quality',
                value: pickMetric(current, ['quality_avg']) !== null ? Math.round(pickMetric(current, ['quality_avg'])) : '-',
                change: formatDelta(current.quality_avg, prior.quality_avg),
                icon: 'M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z',
            },
            {
                id: 'card-restarts',
                label: 'Restarts (24h)',
                value: pickNumber(current.restart_count, 0),
                change: formatDelta(current.restart_count, prior.restart_count),
                icon: 'M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15',
            },
        ];
        
        const container = document.getElementById('summary-cards');
        if (!container) return;
        
        container.innerHTML = cards.map(card => `
            <div class="card">
                <div class="card-body">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-sm text-gray-500 dark:text-gray-400">${card.label}</p>
                            <p class="text-2xl font-bold text-gray-900 dark:text-white" id="${card.id}">${card.value}</p>
                            ${card.change ? `<p class="text-sm mt-1" id="${card.id}-change">${card.change}</p>` : ''}
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
        
        // Update last collection time
        if (latest.collection) {
            const time = new Date(latest.collection.collected_at);
            document.getElementById('last-update').textContent = `Last updated: ${time.toLocaleTimeString()}`;
        } else {
            document.getElementById('last-update').textContent = 'Last updated: Never';
        }
    } catch (err) {
        console.error('Failed to load summary cards:', err);
        MystMonUtils.showToast('Failed to load summary cards: ' + err.message, 'error');
        
        // Show error state in UI
        const container = document.getElementById('summary-cards');
        if (container) {
            container.innerHTML = '<div class="col-span-full text-center py-8 text-red-500">Failed to load summary data</div>';
        }
    }
}

function formatDelta(current, prior, isEarnings = false) {
    if (!isKnownNumber(current) || !isKnownNumber(prior)) {
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

async function loadTrendCharts() {
    try {
        const overall = await MystMonApi.historyOverall(48);
        const collections = overall.collections || [];

        const series = collections
            .slice()
            .reverse()
            .map(collection => collection.fleet || {});

        const onlineData = series.map(item => pickMetric(item, ['online', 'running']));
        const qualityData = series.map(item => pickMetric(item, ['quality_avg']));
        const earningsData = series.map(item => pickMetric(item, ['earnings_total']));
        const restartsData = series.map(item => pickMetric(item, ['restart_count']));
        
        // Create sparklines
        createSparkline('online-trend-chart', onlineData, MystMonUtils.getChartColor(0));
        createSparkline('quality-trend-chart', qualityData, MystMonUtils.getChartColor(1));
        createSparkline('earnings-trend-chart', earningsData, MystMonUtils.getChartColor(2));
        createSparkline('restarts-trend-chart', restartsData, MystMonUtils.getChartColor(3));
        
        // Update trend values
        const totalOnlineDelta = aggregateLatest(onlineData);
        const avgQualityDelta = aggregateAverage(qualityData);
        const totalEarningsDelta = aggregateLatest(earningsData);
        const totalRestartsDelta = aggregateLatest(restartsData);
        
        updateTrendValue('online-trend-value', totalOnlineDelta, 'nodes');
        updateTrendValue('quality-trend-value', avgQualityDelta, 'quality');
        updateTrendValue('earnings-trend-value', totalEarningsDelta, 'earnings');
        updateTrendValue('restarts-trend-value', totalRestartsDelta, 'restarts');
        
    } catch (err) {
        console.error('Failed to load trend charts:', err);
        MystMonUtils.showToast('Failed to load trend charts: ' + err.message, 'error');
        
        // Show error state in UI
        const trendElements = [
            'online-trend-chart', 'quality-trend-chart', 
            'earnings-trend-chart', 'restarts-trend-chart'
        ];
        trendElements.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = '<div class="text-center text-red-500 py-4">Failed to load chart</div>';
        });
    }
}

function isKnownNumber(value) {
    return typeof value === 'number' && Number.isFinite(value);
}

function pickNumber(value, fallback = null) {
    return isKnownNumber(value) ? value : fallback;
}

function pickMetric(obj, keys) {
    for (const key of keys) {
        const value = obj?.[key];
        if (isKnownNumber(value)) return value;
    }
    return null;
}

function aggregateLatest(values) {
    if (!Array.isArray(values) || values.length === 0) return null;
    const known = values.filter(isKnownNumber);
    return known.length > 0 ? known[known.length - 1] : null;
}

function aggregateAverage(values) {
    if (!Array.isArray(values) || values.length === 0) return null;
    const known = values.filter(isKnownNumber);
    return known.length > 0 ? known.reduce((a, b) => a + b, 0) / known.length : null;
}

function createSparkline(canvasId, data, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    const width = canvas.width = canvas.offsetWidth * 2;
    const height = canvas.height = 80;
    
    // Clear
    ctx.clearRect(0, 0, width, height);
    
    const points = Array.isArray(data) ? data.filter(isKnownNumber) : [];

    if (points.length === 0) {
        // Show "No data" message
        ctx.fillStyle = '#9ca3af';
        ctx.font = '14px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText('No data', width/2, height/2);
        return;
    }
    
    const max = Math.max(...points);
    const min = Math.min(...points);
    const range = (max - min) || 1;
    
    // Draw area
    ctx.beginPath();
    ctx.moveTo(0, height);
    
    points.forEach((value, i) => {
        const x = points.length === 1 ? width / 2 : (i / (points.length - 1)) * width;
        const y = height - ((value - min) / range) * (height - 10) - 5;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    
    ctx.lineTo(width, height);
    ctx.closePath();
    
    const gradient = ctx.createLinearGradient(0, 0, 0, height);
    gradient.addColorStop(0, color.replace('1)', '0.3)'));
    gradient.addColorStop(1, color.replace('1)', '0)'));
    ctx.fillStyle = gradient;
    ctx.fill();
    
    // Draw line
    ctx.beginPath();
    points.forEach((value, i) => {
        const x = points.length === 1 ? width / 2 : (i / (points.length - 1)) * width;
        const y = height - ((value - min) / range) * (height - 10) - 5;
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.stroke();
}

function updateTrendValue(elementId, value, type) {
    const el = document.getElementById(elementId);
    if (!el) return;
    
    let formatted;
    switch (type) {
        case 'earnings':
            formatted = MystMonUtils.formatEarnings(value);
            break;
        case 'quality':
            formatted = isKnownNumber(value) ? value.toFixed(1) : '-';
            break;
        default:
            formatted = isKnownNumber(value) ? (value > 0 ? '+' + value : value) : '-';
    }
    
    el.textContent = formatted;
    
    const changeEl = document.getElementById(elementId.replace('-value', '-change'));
    if (changeEl) {
        changeEl.innerHTML = value > 0 
            ? '<span class="text-green-600 dark:text-green-400">↑ Positive</span>'
            : value < 0
            ? '<span class="text-red-600 dark:text-red-400">↓ Negative</span>'
            : value === 0
            ? '<span class="text-gray-400 dark:text-gray-500">→ Neutral</span>'
            : '<span class="text-gray-400 dark:text-gray-500">No data</span>';
    }
}

async function loadAlerts() {
    try {
        const delta = await MystMonApi.historyDelta(24);
        const nodes = delta.nodes || [];
        
        const alerts = [];
        
        nodes.forEach(node => {
            const current = node.current || {};
            
            // Quality alerts
            if (current.quality !== null && current.quality !== undefined && current.quality < 50) {
                alerts.push({
                    type: 'warning',
                    message: `${node.node_name}: Quality is ${current.quality} (below 50)`,
                    node: node.node_key,
                });
            }
            
            // Restart alerts
            if (node.delta?.restart_count > 5) {
                alerts.push({
                    type: 'error',
                    message: `${node.node_name}: ${node.delta.restart_count} restarts in 24h`,
                    node: node.node_key,
                });
            }
            
            // Offline alerts
            if (current.online === 0 || current.online === false) {
                alerts.push({
                    type: 'error',
                    message: `${node.node_name}: Node is offline`,
                    node: node.node_key,
                });
            } else if ((current.online === null || current.online === undefined) && (current.running === 0 || current.running === false)) {
                alerts.push({
                    type: 'error',
                    message: `${node.node_name}: Container is stopped`,
                    node: node.node_key,
                });
            }
            
            // Log error alerts
            if (node.delta?.log_error_or_warning > 10) {
                alerts.push({
                    type: 'warning',
                    message: `${node.node_name}: ${node.delta.log_error_or_warning} new errors/warnings`,
                    node: node.node_key,
                });
            }
        });
        
        const container = document.getElementById('alerts-list');
        if (!container) return;
        
        if (alerts.length === 0) {
            container.innerHTML = '<div class="text-center text-gray-500 dark:text-gray-400 py-4">No alerts</div>';
            return;
        }
        
        container.innerHTML = alerts.slice(0, 10).map(alert => `
            <div class="flex items-start space-x-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <svg class="w-5 h-5 mt-0.5 flex-shrink-0 ${alert.type === 'error' ? 'text-red-500' : 'text-yellow-500'}" fill="currentColor" viewBox="0 0 20 20">
                    ${alert.type === 'error' 
                        ? '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>'
                        : '<path fill-rule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clip-rule="evenodd"/>'
                    }
                </svg>
                <div class="flex-1 min-w-0">
                    <p class="text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(alert.message)}</p>
                    <a href="${MystMonUtils.getUiPath()}/node/${encodeURIComponent(alert.node)}" class="text-xs text-primary-600 dark:text-primary-400 hover:underline">View node</a>
                </div>
            </div>
        `).join('');
        
    } catch (err) {
        console.error('Failed to load alerts:', err);
        const container = document.getElementById('alerts-list');
        if (container) container.innerHTML = '<div class="text-center text-red-500 py-4">Failed to load alerts</div>';
    }
}

async function loadCollectorsStatus() {
    try {
        const status = await MystMonApi.collectorsStatus();
        const collectors = status.collectors || {};
        
        const container = document.getElementById('collectors-list');
        if (!container) return;
        
        if (Object.keys(collectors).length === 0) {
            container.innerHTML = '<div class="text-center text-gray-500 dark:text-gray-400 py-4">No collector data</div>';
            return;
        }
        
        container.innerHTML = Object.entries(collectors).map(([name, info]) => {
            const isOk = info.status === 'ok';
            const isDisabled = info.status === 'disabled';
            const dotClass = isOk ? 'bg-green-500' : isDisabled ? 'bg-gray-400' : 'bg-yellow-500';
            const badgeClass = isOk
                ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200'
                : isDisabled
                ? 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
                : 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200';
            const detail = isDisabled
                ? 'disabled'
                : `${info.nodes_collected} nodes • ${MystMonUtils.formatRelativeTime(info.last_run)}`;
            return `
            <div class="flex items-center justify-between p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <div class="flex items-center space-x-3">
                    <div class="w-2 h-2 rounded-full ${dotClass}"></div>
                    <div>
                        <p class="font-medium text-gray-900 dark:text-white capitalize">${name}</p>
                        <p class="text-xs text-gray-500 dark:text-gray-400">${detail}</p>
                    </div>
                </div>
                <span class="px-2 py-1 text-xs rounded-full ${badgeClass}">
                    ${info.status}
                </span>
            </div>
        `; }).join('');
        
    } catch (err) {
        console.error('Failed to load collectors status:', err);
        const container = document.getElementById('collectors-list');
        if (container) container.innerHTML = '<div class="text-center text-red-500 py-4">Failed to load</div>';
    }
}

async function loadQuickNodes() {
    try {
        const nodesResponse = await MystMonApi.historyNodes(true, 10);
        const nodes = nodesResponse.nodes || [];
        
        const tbody = document.getElementById('quick-nodes-body');
        if (!tbody) return;
        
        if (nodes.length === 0) {
            tbody.innerHTML = '<tr><td colspan="13" class="text-center text-gray-500 dark:text-gray-400 py-4">No nodes found</td></tr>';
            return;
        }
        
        tbody.innerHTML = nodes.map(node => {
            const quality = isKnownNumber(node.api_provider_quality) ? node.api_provider_quality : (isKnownNumber(node.quality) ? node.quality : null);
            const earnings = isKnownNumber(node.api_payments_balance) ? node.api_payments_balance : (isKnownNumber(node.earnings_total) ? node.earnings_total : null);
            const uptime = isKnownNumber(node.uptime_minutes_24h) ? node.uptime_minutes_24h : (isKnownNumber(node.uptime_seconds) ? node.uptime_seconds / 60 : null);
            const restarts = (node.restart_count !== null && node.restart_count !== undefined) ? node.restart_count : 0;
            const apiStatus = node.api_enabled === true ? 'Up' : (node.api_schema_available === false ? 'Unsupported' : 'Unavailable');
            const nat = node.api_nat_type || node.nat_type || '-';
            const publicIp = node.api_public_ip || node.public_ip || '-';
            const location = [node.api_location_city, node.api_location_country].filter(Boolean).join(', ') || (node.api_location_isp || '-');
            const services = node.api_services_running !== null && node.api_services_count !== null
                ? `${node.api_services_running}/${node.api_services_count}`
                : '-';
            const sessions = [node.api_sessions_1d, node.api_sessions_7d].map(v => v !== null && v !== undefined ? v : '-').join(' / ');
            
            return `
            <tr class="hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer" onclick="window.location='${MystMonUtils.getUiPath()}/node/${encodeURIComponent(node.node_key)}'">
                <td class="px-3 py-2 font-medium text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(node.node_name)}</td>
                <td class="px-3 py-2">${MystMonUtils.getStatusBadge(node.online, node.running)}</td>
                <td class="px-3 py-2">
                    <span class="px-2 py-1 text-xs rounded-full ${node.api_enabled === true ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200' : node.api_schema_available === false ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200' : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200'}">${apiStatus}</span>
                </td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(nat)}</td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(publicIp)}</td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(location)}</td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(services)}</td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(sessions)}</td>
                <td class="px-3 py-2">
                    ${quality !== null
                        ? `<span class="${MystMonUtils.formatQuality(quality).class} font-medium">${MystMonUtils.formatQuality(quality).text}</span>`
                        : '<span class="text-gray-400 dark:text-gray-500">Unknown</span>'}
                </td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${earnings !== null ? MystMonUtils.formatEarnings(earnings) : '-'}</td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${uptime !== null ? MystMonUtils.formatUptimeMinutes(uptime) : '-'}</td>
                <td class="px-3 py-2 text-sm text-gray-900 dark:text-white">${restarts}</td>
                <td class="px-3 py-2 text-sm text-gray-500 dark:text-gray-400">${MystMonUtils.formatRelativeTime(node.collected_at)}</td>
            </tr>
        `}).join('');
        
    } catch (err) {
        console.error('Failed to load quick nodes:', err);
        const tbody = document.getElementById('quick-nodes-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="13" class="text-center text-red-500 py-4">Failed to load</td></tr>';
    }
}

async function triggerCollection() {
    const btn = document.getElementById('collect-btn');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<svg class="w-5 h-5 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>Collecting...';
    }
    
    try {
        const result = await MystMonApi.collect();
        MystMonApi.clearCache();
        MystMonUtils.showToast(`Collection complete: ${JSON.stringify(result)}`, 'success');
        await refreshDashboard();
    } catch (err) {
        MystMonUtils.showToast('Collection failed: ' + err.message, 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>Collect Now';
        }
    }
}

// Auto-refresh
function startAutoRefresh() {
    const interval = 30000; // 30 seconds
    refreshInterval = setInterval(refreshDashboard, interval);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    refreshDashboard();
    startAutoRefresh();
    
    // Stop refresh when page is hidden
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) stopAutoRefresh();
        else startAutoRefresh();
    });
});

// Cleanup on page unload
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
    if (typeof MystMonCharts !== 'undefined' && typeof MystMonCharts.charts !== 'undefined') {
        MystMonCharts.charts.destroyAll();
    }
});
