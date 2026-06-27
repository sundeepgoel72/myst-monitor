async function refreshDashboard() {
    const btn = document.getElementById('refresh-btn');
    if (btn) btn.disabled = true;
    MystMonApi.clearCache();
    try {
        const home = await MystMonApi.home();
        renderHome(home);
    } catch (err) {
        console.error('Dashboard refresh failed:', err);
        MystMonUtils.showToast(`Failed to load home data: ${err.message}`);
        renderDashboardError(err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function renderHome(payload) {
    renderWallet(payload.wallet || {});
    renderNodes(payload.nodes || []);
    const lastUpdate = document.getElementById('last-update');
    if (lastUpdate) {
        lastUpdate.textContent = payload.collection?.collected_at
            ? `Last updated: ${MystMonUtils.formatDateTime(payload.collection.collected_at)}`
            : 'Last updated: Never';
    }
}

function renderWallet(wallet) {
    const total = document.getElementById('wallet-total');
    const updated = document.getElementById('wallet-updated');
    const accounts = document.getElementById('wallet-accounts');

    if (total) total.textContent = wallet.total ? `${MystMonUtils.formatEarnings(wallet.total)} MYST` : 'Unknown';
    if (updated) updated.textContent = wallet.accounts?.length ? `${wallet.accounts.length} account(s)` : 'No wallet data';

    if (!accounts) return;
    if (!wallet.accounts || wallet.accounts.length === 0) {
        accounts.innerHTML = '<div class="text-gray-500 dark:text-gray-400">No wallet data in SQLite history.</div>';
        return;
    }

    accounts.innerHTML = wallet.accounts.map((account) => `
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 py-2 border-b border-gray-200 dark:border-gray-700 last:border-0">
            <div>
                <div class="font-medium text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(account.name || 'Unnamed account')}</div>
                <div class="text-sm text-gray-500 dark:text-gray-400">${MystMonUtils.escapeHtml(account.wallet_address_hint || '')}</div>
            </div>
            <div class="font-mono text-sm text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(account.wallet_total || 'Unknown')}</div>
        </div>
    `).join('');
}

function renderNodes(nodes) {
    const tbody = document.getElementById('home-nodes-body');
    if (!tbody) return;
    if (!nodes || nodes.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-center text-gray-500 dark:text-gray-400 py-4">No node data in SQLite history.</td></tr>';
        return;
    }

    tbody.innerHTML = nodes.map((node) => {
        const nodeName = node.node_name || node.node_key || '-';
        const nodeId = node.identity || node.node_key || '-';
        const href = `${window.location.pathname.replace(/\/$/, '')}/node/${encodeURIComponent(node.node_key || nodeId)}`;
        return `
            <tr>
                <td class="py-2 px-3 font-medium text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(nodeName)}</td>
                <td class="py-2 px-3"><a href="${href}" class="text-primary-600 dark:text-primary-400 hover:underline">${MystMonUtils.escapeHtml(nodeId)}</a></td>
                <td class="py-2 px-3">${MystMonUtils.escapeHtml(node.status || 'Unknown')}</td>
                <td class="py-2 px-3">${node.quality_known ? MystMonUtils.escapeHtml(MystMonUtils.formatQuality(node.quality).value) : '-'}</td>
                <td class="py-2 px-3">${node.earnings_known ? MystMonUtils.escapeHtml(MystMonUtils.formatEarnings(node.earnings_total)) : '-'}</td>
                <td class="py-2 px-3">${node.restart_count ?? '-'}</td>
                <td class="py-2 px-3">${MystMonUtils.escapeHtml(MystMonUtils.formatDateTime(node.last_seen))}</td>
            </tr>
        `;
    }).join('');
}

function renderDashboardError(message) {
    const tbody = document.getElementById('home-nodes-body');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-red-600 py-4">${MystMonUtils.escapeHtml(message)}</td></tr>`;
    }
}

window.addEventListener('DOMContentLoaded', refreshDashboard);
