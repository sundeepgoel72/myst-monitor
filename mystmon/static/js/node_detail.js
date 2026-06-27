const nodeKey = decodeURIComponent(window.location.pathname.split('/').pop());
let nodeCharts = {};
let selectedHours = 24;
let nodeHistoryPayload = null;

async function refreshNodeDetail() {
    const btn = document.getElementById('refresh-btn');
    if (btn) btn.disabled = true;
    MystMonApi.clearCache();
    try {
        nodeHistoryPayload = await MystMonApi.historyNode(nodeKey, 500, 0, selectedHours);
        renderNodeHistory(nodeHistoryPayload);
    } catch (err) {
        console.error('Node detail refresh failed:', err);
        MystMonUtils.showToast(`Failed to load node history: ${err.message}`);
        renderNodeError(err.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

function renderNodeHistory(payload) {
    const history = payload.history || [];
    const current = history[0] || null;

    document.getElementById('node-name').textContent = current?.node_name || nodeKey;
    document.getElementById('node-identity').textContent = current?.identity || current?.node_key || nodeKey;

    renderSummaryCards(current, history.length);
    renderHistoryTable(history);
    renderCharts(history);
    const lastUpdate = document.getElementById('last-update');
    if (lastUpdate) {
        lastUpdate.textContent = current?.collected_at
            ? `Last updated: ${MystMonUtils.formatDateTime(current.collected_at)}`
            : 'Last updated: Never';
    }
}

function renderSummaryCards(current, count) {
    const container = document.getElementById('node-summary-cards');
    if (!container) return;
    if (!current) {
        container.innerHTML = '<div class="col-span-full text-gray-500 dark:text-gray-400">No history for this node.</div>';
        return;
    }

    const status = MystMonUtils.getNodeStatus(current.online, current.running).label;
    const cards = [
        { label: 'Status', value: status },
        { label: 'Quality', value: current.quality_known ? MystMonUtils.formatQuality(current.quality).value : '-' },
        { label: 'Earnings', value: current.earnings_known ? MystMonUtils.formatEarnings(current.earnings_total) : '-' },
        { label: 'Rows', value: String(count) },
    ];

    container.innerHTML = cards.map((card) => `
        <div class="card">
            <div class="card-body">
                <div class="text-sm text-gray-500 dark:text-gray-400">${MystMonUtils.escapeHtml(card.label)}</div>
                <div class="text-2xl font-bold text-gray-900 dark:text-white">${MystMonUtils.escapeHtml(card.value)}</div>
            </div>
        </div>
    `).join('');
}

function renderHistoryTable(history) {
    const tbody = document.getElementById('node-history-body');
    if (!tbody) return;
    if (!history || history.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-gray-500 dark:text-gray-400 py-4">No history rows in the selected range.</td></tr>';
        return;
    }

    tbody.innerHTML = history.map((row) => `
        <tr class="border-b border-gray-200 dark:border-gray-700">
            <td class="py-2 px-3">${MystMonUtils.escapeHtml(MystMonUtils.formatDateTime(row.collected_at))}</td>
            <td class="py-2 px-3">${MystMonUtils.escapeHtml(MystMonUtils.getNodeStatus(row.online, row.running).label)}</td>
            <td class="py-2 px-3">${row.quality_known ? MystMonUtils.escapeHtml(MystMonUtils.formatQuality(row.quality).value) : '-'}</td>
            <td class="py-2 px-3">${row.earnings_known ? MystMonUtils.escapeHtml(MystMonUtils.formatEarnings(row.earnings_total)) : '-'}</td>
            <td class="py-2 px-3">${row.restart_count ?? '-'}</td>
        </tr>
    `).join('');
}

function renderCharts(history) {
    createMetricChart('quality-chart', history, 'quality', 'Quality', (row) => row.quality_known ? row.quality : null);
    createMetricChart('earnings-chart', history, 'earnings_total', 'Earnings', (row) => row.earnings_known ? row.earnings_total : null);
    createMetricChart('restarts-chart', history, 'restart_count', 'Restarts', (row) => row.restart_count);
}

function createMetricChart(canvasId, history, key, label, getter) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    if (nodeCharts[canvasId]) nodeCharts[canvasId].destroy();

    const rows = [...history]
        .reverse()
        .map((row) => ({ x: MystMonUtils.formatDateTime(row.collected_at), y: getter(row) }))
        .filter((row) => row.y !== null && row.y !== undefined && row.y !== '');

    if (rows.length === 0) {
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = '#6b7280';
        ctx.font = '14px sans-serif';
        ctx.fillText('No data', 12, 24);
        return;
    }

    nodeCharts[canvasId] = new Chart(canvas, {
        type: key === 'restart_count' ? 'bar' : 'line',
        data: {
            labels: rows.map((row) => row.x),
            datasets: [{
                label,
                data: rows.map((row) => row.y),
                borderColor: MystMonUtils.getChartColor(canvasId === 'quality-chart' ? 0 : canvasId === 'earnings-chart' ? 1 : 3),
                backgroundColor: 'rgba(37, 99, 235, 0.15)',
                fill: key !== 'restart_count',
                tension: 0.25,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 6 } },
                y: { beginAtZero: key === 'restart_count' },
            },
        },
    });
}

function renderNodeError(message) {
    const tbody = document.getElementById('node-history-body');
    if (tbody) {
        tbody.innerHTML = `<tr><td colspan="5" class="text-center text-red-600 py-4">${MystMonUtils.escapeHtml(message)}</td></tr>`;
    }
}

function setActiveRange(hours) {
    selectedHours = hours;
    document.querySelectorAll('.history-range-btn').forEach((button) => {
        button.classList.toggle('active', Number(button.dataset.hours) === Number(hours));
    });
}

window.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.history-range-btn').forEach((button) => {
        button.addEventListener('click', () => {
            setActiveRange(Number(button.dataset.hours));
            refreshNodeDetail();
        });
    });
    setActiveRange(selectedHours);
    refreshNodeDetail();
});
