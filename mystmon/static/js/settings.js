/**
 * Settings page logic
 */

async function refreshSettings() {
    const btn = document.getElementById('refresh-btn');
    if (btn) btn.disabled = true;
    
    try {
        await Promise.all([
            loadConfig(),
            loadCollectorsStatus(),
            loadPortalConfig(),
            loadTelegramConfig(),
            loadSystemInfo(),
        ]);
    } catch (err) {
        console.error('Settings refresh failed:', err);
        MystMonUtils.showToast('Failed to refresh settings', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function loadConfig() {
    try {
        const config = await MystMonApi.config();
        
        // Full config JSON
        const pre = document.getElementById('config-json');
        if (pre) {
            pre.textContent = JSON.stringify(config, null, 2);
        }
        
        // UI config
        const uiConfig = config.ui || {};
        const dl = document.getElementById('ui-config');
        if (dl) {
            dl.innerHTML = Object.entries(uiConfig).map(([key, value]) => `
                <dt class="text-gray-500 dark:text-gray-400">${key}</dt>
                <dd class="font-mono text-sm text-gray-900 dark:text-white">${JSON.stringify(value)}</dd>
            `).join('');
        }
        
    } catch (err) {
        console.error('Failed to load config:', err);
    }
}

async function loadCollectorsStatus() {
    try {
        const status = await MystMonApi.collectorsStatus();
        const collectors = status.collectors || {};
        
        const tbody = document.getElementById('collectors-body');
        if (tbody) {
            tbody.innerHTML = Object.entries(collectors).map(([name, info]) => `
                <tr class="border-b border-gray-200 dark:border-gray-700">
                    <td class="py-2 px-3 font-medium">${name}</td>
                    <td class="py-2 px-3">${info.enabled !== false ? '✓' : '✗'}</td>
                    <td class="py-2 px-3 text-sm text-gray-500 dark:text-gray-400">${info.last_run ? MystMonUtils.formatRelativeTime(info.last_run) : '-'}</td>
                    <td class="py-2 px-3 text-sm">${info.nodes_collected || 0}</td>
                    <td class="py-2 px-3">
                        <span class="px-2 py-1 text-xs rounded-full ${info.status === 'ok' ? 'bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200' : 'bg-yellow-100 dark:bg-yellow-900 text-yellow-800 dark:text-yellow-200'}">
                            ${info.status}
                        </span>
                    </td>
                    <td class="py-2 px-3 text-sm text-gray-500 dark:text-gray-400">${info.error || '-'}</td>
                </tr>
            `).join('') || '<tr><td colspan="6" class="text-center text-gray-500 dark:text-gray-400 py-4">No collector data</td></tr>';
        }
        
        // Collector config JSON
        const config = await MystMonApi.config();
        const pre = document.getElementById('collectors-config-json');
        if (pre) {
            const collectorConfig = {
                myst: config.myst,
                prometheus: config.prometheus,
                snmp: config.snmp,
                mystnodes: config.mystnodes,
            };
            pre.textContent = JSON.stringify(collectorConfig, null, 2);
        }
        
    } catch (err) {
        console.error('Failed to load collectors status:', err);
    }
}

async function loadPortalConfig() {
    try {
        const config = await MystMonApi.config();
        const portalConfig = config.mystnodes || {};
        
        const pre = document.getElementById('portal-config-json');
        if (pre) {
            // Redact sensitive fields
            const safeConfig = { ...portalConfig };
            if (safeConfig.email_env) safeConfig.email_env = '***';
            if (safeConfig.password_env) safeConfig.password_env = '***';
            pre.textContent = JSON.stringify(safeConfig, null, 2);
        }
        
        const walletEl = document.getElementById('wallet-address');
        if (walletEl) {
            walletEl.textContent = portalConfig.wallet_address || 'Not configured';
        }
        
    } catch (err) {
        console.error('Failed to load portal config:', err);
    }
}

async function testPortalConnection() {
    const btn = event.target;
    const resultEl = document.getElementById('portal-test-result');
    
    btn.disabled = true;
    btn.innerHTML = '<svg class="w-5 h-5 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>Testing...';
    resultEl.classList.add('hidden');
    
    try {
        // Trigger a collection which will test portal
        await MystMonApi.collect();
        
        // Check status
        const status = await MystMonApi.collectorsStatus();
        const portalStatus = status.collectors?.mystnodes;
        
        resultEl.className = 'p-4 rounded-lg ' + (portalStatus?.status === 'ok' ? 'bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-800');
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = `
            <div class="flex items-center space-x-2">
                <svg class="w-5 h-5 ${portalStatus?.status === 'ok' ? 'text-green-500' : 'text-red-500'}" fill="currentColor" viewBox="0 0 20 20">
                    ${portalStatus?.status === 'ok' 
                        ? '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>'
                        : '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>'
                    }
                </svg>
                <span class="font-medium">${portalStatus?.status === 'ok' ? 'Portal connection successful' : 'Portal connection failed'}</span>
            </div>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">Nodes collected: ${portalStatus?.nodes_collected || 0}</p>
        `;
        
    } catch (err) {
        resultEl.className = 'p-4 rounded-lg bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-800';
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = `
            <div class="flex items-center space-x-2 text-red-500">
                <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>
                <span class="font-medium">Test failed: ${err.message}</span>
            </div>
        `;
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Test Connection';
    }
}

async function loadTelegramConfig() {
    try {
        const config = await MystMonApi.config();
        const telegramConfig = config.telegram || {};
        
        const dl = document.getElementById('telegram-config');
        if (dl) {
            const safeConfig = { ...telegramConfig };
            if (safeConfig.bot_token_env) safeConfig.bot_token_env = '***';
            if (safeConfig.chat_id_env) safeConfig.chat_id_env = '***';
            
            dl.innerHTML = Object.entries(safeConfig).map(([key, value]) => `
                <dt class="text-gray-500 dark:text-gray-400">${key}</dt>
                <dd class="font-mono text-sm text-gray-900 dark:text-white">${JSON.stringify(value)}</dd>
            `).join('');
        }
        
        // Load report history
        if (config.history?.enabled) {
            // Would need to query history store for telegram_reports
            // For now, show placeholder
            const tbody = document.getElementById('telegram-reports-body');
            if (tbody) {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-gray-500 dark:text-gray-400 py-4">Report history requires database access</td></tr>';
            }
        }
        
    } catch (err) {
        console.error('Failed to load telegram config:', err);
    }
}

async function testTelegram() {
    const btn = event.target;
    const resultEl = document.getElementById('telegram-test-result');
    
    btn.disabled = true;
    btn.innerHTML = '<svg class="w-5 h-5 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>Sending...';
    resultEl.classList.add('hidden');
    
    try {
        const result = await MystMonApi.telegramTest();
        
        resultEl.className = 'p-4 rounded-lg ' + (result.ok ? 'bg-green-50 dark:bg-green-900 border border-green-200 dark:border-green-800' : 'bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-800');
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = `
            <div class="flex items-center space-x-2">
                <svg class="w-5 h-5 ${result.ok ? 'text-green-500' : 'text-red-500'}" fill="currentColor" viewBox="0 0 20 20">
                    ${result.ok 
                        ? '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zm3.707-9.293a1 1 0 00-1.414-1.414L9 10.586 7.707 9.293a1 1 0 00-1.414 1.414l2 2a1 1 0 001.414 0l4-4z" clip-rule="evenodd"/>'
                        : '<path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/>'
                    }
                </svg>
                <span class="font-medium">${result.ok ? 'Test message sent successfully' : 'Failed to send test message'}</span>
            </div>
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">${result.message || JSON.stringify(result)}</p>
        `;
        
    } catch (err) {
        resultEl.className = 'p-4 rounded-lg bg-red-50 dark:bg-red-900 border border-red-200 dark:border-red-800';
        resultEl.classList.remove('hidden');
        resultEl.innerHTML = `
            <div class="flex items-center space-x-2 text-red-500">
                <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z" clip-rule="evenodd"/></svg>
                <span class="font-medium">Test failed: ${err.message}</span>
            </div>
        `;
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Send Test Message';
    }
}

async function loadSystemInfo() {
    try {
        const info = await MystMonApi.systemInfo();
        
        // System info
        const sysInfo = document.getElementById('system-info');
        if (sysInfo) {
            sysInfo.innerHTML = [
                { key: 'Version', value: info.version },
                { key: 'Service Name', value: info.service_name },
                { key: 'Uptime', value: info.uptime_seconds ? MystMonUtils.formatDuration(info.uptime_seconds) : 'Unknown' },
            ].map(item => `
                <dt class="text-gray-500 dark:text-gray-400">${item.key}</dt>
                <dd class="font-mono text-sm text-gray-900 dark:text-white">${item.value}</dd>
            `).join('');
        }
        
        // Database stats
        const dbStats = document.getElementById('db-stats');
        if (dbStats && info.database) {
            const db = info.database;
            dbStats.innerHTML = [
                { key: 'Enabled', value: db.enabled ? 'Yes' : 'No' },
                { key: 'Collections', value: db.collections || 0 },
                { key: 'Node Metrics', value: db.node_metrics || 0 },
                { key: 'Size', value: db.size_bytes ? formatBytes(db.size_bytes) : 'Unknown' },
                { key: 'Date Range', value: db.date_range ? `${MystMonUtils.formatDateTime(db.date_range.from)} to ${MystMonUtils.formatDateTime(db.date_range.to)}` : 'N/A' },
            ].map(item => `
                <dt class="text-gray-500 dark:text-gray-400">${item.key}</dt>
                <dd class="font-mono text-sm text-gray-900 dark:text-white">${item.value}</dd>
            `).join('');
        }
        
        // Disk usage
        const diskUsage = document.getElementById('disk-usage');
        if (diskUsage && info.disk_usage) {
            const disk = info.disk_usage;
            const usedPct = disk.total_bytes ? ((disk.used_bytes / disk.total_bytes) * 100).toFixed(1) : 0;
            diskUsage.innerHTML = [
                { key: 'Total', value: formatBytes(disk.total_bytes) },
                { key: 'Used', value: `${formatBytes(disk.used_bytes)} (${usedPct}%)` },
                { key: 'Free', value: formatBytes(disk.free_bytes) },
                { key: 'Path', value: disk.path },
            ].map(item => `
                <dt class="text-gray-500 dark:text-gray-400">${item.key}</dt>
                <dd class="font-mono text-sm text-gray-900 dark:text-white">${item.value}</dd>
            `).join('');
        }
        
    } catch (err) {
        console.error('Failed to load system info:', err);
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

function switchSettingsTab(tabName) {
    document.querySelectorAll('#settings-collectors, #settings-portal, #settings-telegram, #settings-system, #settings-config').forEach(el => {
        el.classList.add('hidden');
    });
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });
    document.getElementById(`settings-${tabName}`)?.classList.remove('hidden');
}

async function triggerCollection() {
    const btn = event.target;
    btn.disabled = true;
    btn.innerHTML = '<svg class="w-5 h-5 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>Collecting...';
    
    try {
        const result = await MystMonApi.collect();
        MystMonUtils.showToast(`Collection complete: ${JSON.stringify(result)}`, 'success');
        await refreshSettings();
    } catch (err) {
        MystMonUtils.showToast('Collection failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Run Collection Now';
    }
}

async function vacuumDatabase() {
    if (!confirm('This will vacuum the SQLite database. Continue?')) return;
    
    const btn = event.target;
    btn.disabled = true;
    btn.innerHTML = '<svg class="w-5 h-5 mr-2 animate-spin" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>Vacuuming...';
    
    try {
        // This would need a new API endpoint
        MystMonUtils.showToast('Database vacuum not implemented yet', 'warning');
    } catch (err) {
        MystMonUtils.showToast('Vacuum failed: ' + err.message, 'error');
    } finally {
        btn.disabled = false;
        btn.innerHTML = 'Vacuum Database';
    }
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    refreshSettings();
});
