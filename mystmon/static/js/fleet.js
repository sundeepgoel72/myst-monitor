/**
 * Fleet page logic
 */

let allNodes = [];
let filteredNodes = [];
let currentPage = 1;
const rowsPerPage = 25;
let sortColumn = 'node_name';
let sortDirection = 'asc';
let selectedNodes = new Set();

async function refreshFleet() {
    const btn = document.getElementById('refresh-btn');
    if (btn) btn.disabled = true;
    
    try {
        await loadFleetData();
    } catch (err) {
        console.error('Fleet refresh failed:', err);
        MystMonUtils.showToast('Failed to refresh fleet', 'error');
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function loadFleetData() {
    try {
        const [nodesResponse, delta] = await Promise.all([
            MystMonApi.historyNodes(true, 500),
            MystMonApi.historyDelta(24),
        ]);
        
        allNodes = nodesResponse.nodes || [];
        const deltaNodes = delta.nodes || [];
        
        // Merge delta data
        const deltaMap = new Map(deltaNodes.map(n => [n.node_key, n.delta]));
        
        allNodes = allNodes.map(node => {
            const delta = deltaMap.get(node.node_key) || {};
            return {
                ...node,
                delta,
                // Compute derived fields
                status: node.online ? 'online' : 'offline',
                running: node.running === 1 || node.running === true,
                quality: node.quality,
                earnings_24h: node.earnings_total,
                uptime_24h: node.uptime_minutes_24h,
                restarts: node.restart_count,
                last_seen: node.collected_at,
                local_match: node.local_match === 1 || node.local_match === true,
                identity_short: MystMonUtils.truncate(node.identity || '', 16),
                node_id_short: MystMonUtils.truncate(node.node_key || '', 12),
            };
        });
        
        // Populate host filter
        populateHostFilter();
        
        // Apply filters and render
        filterTable();
        
    } catch (err) {
        console.error('Failed to load fleet data:', err);
        const tbody = document.getElementById('fleet-body');
        if (tbody) tbody.innerHTML = '<tr><td colspan="11" class="text-center text-red-500 py-4">Failed to load fleet data</td></tr>';
    }
}

function populateHostFilter() {
    const hosts = [...new Set(allNodes.map(n => n.host).filter(Boolean))].sort();
    const select = document.getElementById('host-filter');
    if (!select) return;
    
    const currentValue = select.value;
    select.innerHTML = '<option value="">All</option>' + hosts.map(h => `<option value="${MystMonUtils.escapeHtml(h)}">${MystMonUtils.escapeHtml(h)}</option>`).join('');
    select.value = currentValue;
}

function filterTable() {
    const search = document.getElementById('search-input')?.value.toLowerCase() || '';
    const status = document.getElementById('status-filter')?.value || '';
    const host = document.getElementById('host-filter')?.value || '';
    const quality = document.getElementById('quality-filter')?.value || '';
    const match = document.getElementById('match-filter')?.value || '';
    
    filteredNodes = allNodes.filter(node => {
        // Search
        if (search) {
            const haystack = `${node.node_name} ${node.identity || ''} ${node.local_ip || ''} ${node.host || ''}`.toLowerCase();
            if (!haystack.includes(search)) return false;
        }
        
        // Status filter
        if (status) {
            if (status === 'online' && !node.online) return false;
            if (status === 'offline' && node.online) return false;
            if (status === 'running' && !node.running) return false;
            if (status === 'stopped' && node.running) return false;
        }
        
        // Host filter
        if (host && node.host !== host) return false;
        
        // Quality filter
        if (quality) {
            const q = node.quality;
            if (quality === 'high' && (q === null || q < 80)) return false;
            if (quality === 'medium' && (q === null || q < 50 || q >= 80)) return false;
            if (quality === 'low' && (q === null || q >= 50)) return false;
            if (quality === 'unknown' && q !== null) return false;
        }
        
        // Match filter
        if (match) {
            if (match === 'matched' && !node.local_match) return false;
            if (match === 'unmatched' && node.local_match) return false;
        }
        
        return true;
    });
    
    // Sort
    filteredNodes.sort((a, b) => {
        let aVal = a[sortColumn];
        let bVal = b[sortColumn];
        
        if (aVal === null || aVal === undefined) aVal = '';
        if (bVal === null || bVal === undefined) bVal = '';
        
        if (typeof aVal === 'string') {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }
        
        if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
        return 0;
    });
    
    currentPage = 1;
    renderTable();
    updatePagination();
    updateSelectionBar();
}

function sortTable(column) {
    if (sortColumn === column) {
        sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        sortColumn = column;
        sortDirection = 'asc';
    }
    
    // Update sort icons
    document.querySelectorAll('[data-sort]').forEach(th => {
        const icon = th.querySelector('.sort-icon');
        if (th.dataset.sort === column) {
            icon.textContent = sortDirection === 'asc' ? '↑' : '↓';
        } else {
            icon.textContent = '↕';
        }
    });
    
    filterTable();
}

function renderTable() {
    const tbody = document.getElementById('fleet-body');
    if (!tbody) return;
    
    const start = (currentPage - 1) * rowsPerPage;
    const end = start + rowsPerPage;
    const pageNodes = filteredNodes.slice(start, end);
    
    if (pageNodes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="11" class="text-center text-gray-500 dark:text-gray-400 py-8">No nodes match the current filters</td></tr>';
        return;
    }
    
    tbody.innerHTML = pageNodes.map(node => {
        const isSelected = selectedNodes.has(node.node_key);
        const quality = node.quality;
        const qualityClass = quality !== null && quality !== undefined 
            ? (quality >= 80 ? 'text-green-600 dark:text-green-400' : quality >= 50 ? 'text-yellow-600 dark:text-yellow-400' : 'text-red-600 dark:text-red-400')
            : 'text-gray-400 dark:text-gray-500';
        const qualityText = quality !== null && quality !== undefined ? Math.round(quality) : '-';
        
        return `
            <tr class="${isSelected ? 'selected bg-primary-50 dark:bg-primary-900/30' : 'hover:bg-gray-50 dark:hover:bg-gray-800'}" data-node-key="${MystMonUtils.escapeHtml(node.node_key)}" onclick="toggleRowSelection('${MystMonUtils.escapeHtml(node.node_key)}', event)">
                <td class="px-4 py-3">
                    <div class="font-medium text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(node.node_name)}</div>
                    <div class="text-sm text-gray-500 dark:text-gray-400">${MystMonUtils.escapeHtml(node.container_name || '')}</div>
                </td>
                <td class="px-4 py-3">
                    <div class="font-mono text-sm text-gray-900 dark:text-white">${node.identity_short}</div>
                    ${node.node_key ? `<div class="text-sm text-gray-500 dark:text-gray-400">ID: ${node.node_id_short}</div>` : ''}
                </td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(node.host || '-')}</td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(node.local_ip || '-')}</td>
                <td class="px-4 py-3">
                    <div class="flex items-center space-x-2">
                        <span class="w-2.5 h-2.5 rounded-full ${node.online ? 'bg-green-500' : 'bg-red-500'}"></span>
                        <span class="text-sm font-medium ${node.online ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">${node.online ? 'Online' : 'Offline'}</span>
                    </div>
                    <div class="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
                        Container: <span class="${node.running ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}">${node.running ? 'Running' : 'Stopped'}</span>
                    </div>
                </td>
                <td class="px-4 py-3">
                    <div class="flex items-center space-x-2">
                        <div class="w-24 h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
                            <div class="h-full ${quality >= 80 ? 'bg-green-500' : quality >= 50 ? 'bg-yellow-500' : quality !== null ? 'bg-red-500' : 'bg-gray-400'}" style="width: ${quality !== null && quality !== undefined ? quality : 0}%"></div>
                        </div>
                        <span class="text-sm font-medium ${qualityClass}">${qualityText}</span>
                    </div>
                </td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">${MystMonUtils.formatEarnings(node.earnings_24h)}</td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">${MystMonUtils.formatUptimeMinutes(node.uptime_24h)}</td>
                <td class="px-4 py-3 text-sm text-gray-900 dark:text-white">${node.restarts || 0}</td>
                <td class="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">${MystMonUtils.formatRelativeTime(node.last_seen)}</td>
                <td class="px-4 py-3">
                    ${node.local_match 
                        ? '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 dark:bg-green-900 text-green-800 dark:text-green-200"><svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd"/></svg>Matched</span>'
                        : '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200"><svg class="w-3 h-3 mr-1" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>Unmatched</span>'
                    }
                </td>
            </tr>
        `;
    }).join('');
}

function updatePagination() {
    const totalPages = Math.ceil(filteredNodes.length / rowsPerPage);
    const start = filteredNodes.length > 0 ? (currentPage - 1) * rowsPerPage + 1 : 0;
    const end = Math.min(currentPage * rowsPerPage, filteredNodes.length);
    
    const pagination = document.getElementById('pagination');
    if (!pagination) return;
    
    if (totalPages <= 1) {
        pagination.style.display = 'none';
        return;
    }
    
    pagination.style.display = 'flex';
    document.getElementById('showing-start').textContent = start;
    document.getElementById('showing-end').textContent = end;
    document.getElementById('total-rows').textContent = filteredNodes.length;
    document.getElementById('page-info').textContent = `Page ${currentPage} of ${totalPages}`;
    
    const prevBtn = document.getElementById('prev-page');
    const nextBtn = document.getElementById('next-page');
    
    if (prevBtn) prevBtn.disabled = currentPage <= 1;
    if (nextBtn) nextBtn.disabled = currentPage >= totalPages;
}

function changePage(delta) {
    const totalPages = Math.ceil(filteredNodes.length / rowsPerPage);
    const newPage = currentPage + delta;
    if (newPage >= 1 && newPage <= totalPages) {
        currentPage = newPage;
        renderTable();
        updatePagination();
    }
}

function toggleRowSelection(nodeKey, event) {
    // Don't select if clicking on a link
    if (event.target.tagName === 'A') return;
    
    if (selectedNodes.has(nodeKey)) {
        selectedNodes.delete(nodeKey);
    } else {
        selectedNodes.add(nodeKey);
    }
    
    // Update row visual
    const row = document.querySelector(`tr[data-node-key="${nodeKey}"]`);
    if (row) {
        row.classList.toggle('selected', selectedNodes.has(nodeKey));
        row.classList.toggle('bg-primary-50', selectedNodes.has(nodeKey));
        row.classList.toggle('dark:bg-primary-900/30', selectedNodes.has(nodeKey));
    }
    
    updateSelectionBar();
}

function clearSelection() {
    selectedNodes.clear();
    document.querySelectorAll('#fleet-body tr').forEach(row => {
        row.classList.remove('selected', 'bg-primary-50', 'dark:bg-primary-900/30');
    });
    updateSelectionBar();
}

function updateSelectionBar() {
    const bar = document.getElementById('selection-bar');
    const count = document.getElementById('selection-count');
    
    if (!bar || !count) return;
    
    if (selectedNodes.size > 0) {
        bar.classList.remove('hidden');
        count.textContent = `${selectedNodes.size} node${selectedNodes.size !== 1 ? 's' : ''} selected`;
    } else {
        bar.classList.add('hidden');
    }
}

function viewSelectedHistory() {
    if (selectedNodes.size === 0) return;
    const keys = Array.from(selectedNodes).join(',');
    window.location.href = `${MystMonUtils.getUiPath()}/history?nodes=${encodeURIComponent(keys)}`;
}

function exportSelected() {
    if (selectedNodes.size === 0) return;
    
    const selected = filteredNodes.filter(n => selectedNodes.has(n.node_key));
    exportToCsv(selected, 'mystmon_selected_nodes.csv');
}

function exportFleet() {
    exportToCsv(filteredNodes, 'mystmon_fleet.csv');
}

function exportToCsv(nodes, filename) {
    const headers = ['Name', 'Identity', 'Host', 'Local IP', 'Online', 'Running', 'Quality', 'Earnings (24h)', 'Uptime (24h)', 'Restarts', 'Last Seen', 'Local Match'];
    
    const rows = nodes.map(node => [
        node.node_name,
        node.identity || '',
        node.host || '',
        node.local_ip || '',
        node.online ? 'Online' : 'Offline',
        node.running ? 'Running' : 'Stopped',
        node.quality !== null && node.quality !== undefined ? Math.round(node.quality) : '',
        node.earnings_24h || 0,
        node.uptime_24h || 0,
        node.restarts || 0,
        MystMonUtils.formatDateTime(node.last_seen),
        node.local_match ? 'Matched' : 'Unmatched',
    ]);
    
    const csv = [headers, ...rows].map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(',')).join('\n');
    
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    URL.revokeObjectURL(link.href);
    
    MystMonUtils.showToast(`Exported ${nodes.length} nodes to CSV`, 'success');
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    loadFleetData();
    
    // Sort handlers
    document.querySelectorAll('[data-sort]').forEach(th => {
        th.addEventListener('click', () => sortTable(th.dataset.sort));
    });
    
    // Keyboard navigation for table
    document.addEventListener('keydown', (e) => {
        if (e.target.tagName === 'INPUT' || e.target.tagName === 'SELECT') return;
        
        if (e.key === 'ArrowUp' || e.key === 'ArrowDown') {
            const rows = Array.from(document.querySelectorAll('#fleet-body tr[data-node-key]'));
            const selected = rows.find(r => r.classList.contains('selected'));
            const idx = selected ? rows.indexOf(selected) : -1;
            const newIdx = Math.max(0, Math.min(rows.length - 1, idx + (e.key === 'ArrowUp' ? -1 : 1)));
            
            if (rows[newIdx]) {
                clearSelection();
                const key = rows[newIdx].dataset.nodeKey;
                selectedNodes.add(key);
                rows[newIdx].classList.add('selected', 'bg-primary-50', 'dark:bg-primary-900/30');
                rows[newIdx].scrollIntoView({ block: 'nearest' });
                updateSelectionBar();
            }
        }
    });
});
