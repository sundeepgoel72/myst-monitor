/**
 * Chart.js wrappers and helpers for MystMon UI
 */

class ChartManager {
    constructor() {
        this.charts = new Map();
        this.defaults = MystMonUtils.getChartDefaults();
        this.themeObserver = null;
    }
    
    createLineChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        // Destroy existing chart
        if (this.charts.has(canvasId)) {
            this.charts.get(canvasId).destroy();
        }
        
        const config = {
            type: 'line',
            data: data,
            options: {
                ...this.defaults,
                ...options,
                plugins: {
                    ...this.defaults.plugins,
                    ...options.plugins,
                },
                scales: {
                    ...this.defaults.scales,
                    ...options.scales,
                },
            },
        };
        
        const chart = new Chart(ctx, config);
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    createAreaChart(canvasId, data, options = {}) {
        return this.createLineChart(canvasId, data, {
            ...options,
            options: {
                ...options.options,
                elements: {
                    line: {
                        fill: true,
                        tension: 0.3,
                    },
                    point: {
                        radius: 0,
                        hoverRadius: 4,
                    },
                },
            },
        });
    }
    
    createBarChart(canvasId, data, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        if (this.charts.has(canvasId)) {
            this.charts.get(canvasId).destroy();
        }
        
        const config = {
            type: 'bar',
            data: data,
            options: {
                ...this.defaults,
                ...options,
                plugins: {
                    ...this.defaults.plugins,
                    ...options.plugins,
                },
                scales: {
                    ...this.defaults.scales,
                    ...options.scales,
                },
            },
        };
        
        const chart = new Chart(ctx, config);
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    createSparkline(canvasId, data, color, options = {}) {
        const ctx = document.getElementById(canvasId);
        if (!ctx) return null;
        
        if (this.charts.has(canvasId)) {
            this.charts.get(canvasId).destroy();
        }
        
        const isDark = document.documentElement.classList.contains('dark');
        const gridColor = isDark ? '#374151' : '#e5e7eb';
        
        const config = {
            type: 'line',
            data: {
                labels: data.map((_, i) => i),
                datasets: [{
                    data: data.map(d => d.value ?? d),
                    borderColor: color,
                    backgroundColor: color.replace('1)', '0.1)'),
                    fill: true,
                    tension: 0.3,
                    pointRadius: 0,
                    pointHoverRadius: 3,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: false,
                    },
                },
                scales: {
                    x: { display: false },
                    y: { display: false },
                },
                elements: {
                    line: { borderWidth: 2 },
                },
                animation: { duration: 0 },
                ...options,
            },
        };
        
        const chart = new Chart(ctx, config);
        this.charts.set(canvasId, chart);
        return chart;
    }
    
    updateChart(canvasId, newData) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            chart.data = newData;
            chart.update('none');
        }
    }
    
    destroyChart(canvasId) {
        const chart = this.charts.get(canvasId);
        if (chart) {
            chart.destroy();
            this.charts.delete(canvasId);
        }
    }
    
    destroyAll() {
        this.charts.forEach(chart => chart.destroy());
        this.charts.clear();
        if (this.themeObserver) {
            this.themeObserver.disconnect();
        }
    }
    
    // Setup theme change listener
    watchTheme() {
        if (this.themeObserver) return;
        this.themeObserver = MystMonUtils.setupChartThemeListener(Array.from(this.charts.values()));
    }
}

// Global chart manager instance
const charts = new ChartManager();

// Helper functions for common chart data transformations
function prepareTimeSeriesData(points, valueKey = 'value', timeKey = 'collected_at') {
    return points
        .filter(p => p[valueKey] !== null && p[valueKey] !== undefined)
        .map(p => ({
            x: new Date(p[timeKey]),
            y: p[valueKey],
        }))
        .sort((a, b) => a.x - b.x);
}

function prepareComparisonData(current, prior, valueKey = 'value', timeKey = 'collected_at') {
    return {
        current: prepareTimeSeriesData(current, valueKey, timeKey),
        prior: prepareTimeSeriesData(prior, valueKey, timeKey),
    };
}

function createGradient(ctx, colorStops) {
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    colorStops.forEach(([offset, color]) => gradient.addColorStop(offset, color));
    return gradient;
}

// Export
window.MystMonCharts = {
    ChartManager,
    charts,
    prepareTimeSeriesData,
    prepareComparisonData,
    createGradient,
};
