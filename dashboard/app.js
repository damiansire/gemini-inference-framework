/**
 * Gemini Latency Benchmark Dashboard — App Logic
 * Loads benchmark_results/benchmark_data.json when a snapshot exists
 */

// ── Chart.js global config ──
Chart.defaults.color = '#8888a0';
Chart.defaults.borderColor = 'rgba(255, 255, 255, 0.06)';
Chart.defaults.font.family = "'Inter', sans-serif";
Chart.defaults.font.size = 12;
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.pointStyleWidth = 12;

// Strategy colors
const STRATEGY_COLORS = {
    monolithic: { bg: 'rgba(99, 102, 241, 0.7)', border: '#6366f1' },
    monolithic_schema: { bg: 'rgba(139, 92, 246, 0.7)', border: '#8b5cf6' },
    pipeline: { bg: 'rgba(249, 115, 22, 0.7)', border: '#f97316' },
    thinking_budget: { bg: 'rgba(34, 211, 238, 0.7)', border: '#22d3ee' },
    pro_model: { bg: 'rgba(251, 191, 36, 0.7)', border: '#fbbf24' },
    cascade: { bg: 'rgba(52, 211, 153, 0.7)', border: '#34d399' },
    optimized_monolithic: { bg: 'rgba(244, 114, 182, 0.7)', border: '#f472b6' },
    lazy_optimized: { bg: 'rgba(96, 165, 250, 0.7)', border: '#60a5fa' },
};

let benchmarkData = null;

// ── Init ──
document.addEventListener('DOMContentLoaded', async () => {
    try {
        const resp = await fetch('../benchmark_results/benchmark_data.json');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        benchmarkData = await resp.json();
        renderDashboard(benchmarkData);
    } catch (err) {
        console.error('Failed to load benchmark data:', err);
        showEmptyState();
    } finally {
        document.getElementById('loadingOverlay').classList.add('hidden');
    }
});

function showEmptyState() {
    const sections = document.querySelectorAll('.section');
    sections.forEach(s => {
        s.innerHTML = `
            <div class="container">
                <div class="empty-state">
                    <h3>No Current Benchmark Snapshot</h3>
                    <p>This dashboard reads a generated dataset from <code>benchmark_results/benchmark_data.json</code>. None exists in this checkout yet.</p>
                    <code>./venv/bin/python compare_benchmarks.py --iterations 3</code>
                </div>
            </div>
        `;
    });
}

// ── Main render ──
function renderDashboard(data) {
    renderHeroStats(data);
    renderClaims(data);
    renderLatencyChart(data);
    renderThoughtChart(data);
    renderCostChart(data);
    renderScatterChart(data);
    renderComparisonTable(data);
    renderRunsGrid(data);
    renderCascadeResults(data);
    setupFilters(data);
}

// ── Hero Stats ──
function renderHeroStats(data) {
    const meta = data.metadata;
    document.getElementById('statStrategies').textContent = meta.strategies_tested.length;
    document.getElementById('statWords').textContent = meta.words.length;
    document.getElementById('statRuns').textContent = data.raw_runs.length;

    const ts = new Date(meta.timestamp);
    document.getElementById('statTimestamp').textContent = ts.toLocaleDateString('en-US', {
        month: 'short', day: 'numeric', year: 'numeric'
    });
}

// ── Claims Verification ──
function renderClaims(data) {
    const summaries = data.summaries;

    // Claim 1: Extreme thought tokens
    const monoSummary = summaries.monolithic || summaries.monolithic_schema;
    if (monoSummary) {
        const maxThought = monoSummary.max_thought_tokens || 0;
        const avgThought = monoSummary.avg_thought_tokens || 0;
        document.getElementById('maxThoughtObserved').textContent = maxThought.toLocaleString();
        document.getElementById('avgThoughtMono').textContent = avgThought.toLocaleString();

        const verdict1 = document.getElementById('verdict1');
        if (maxThought > 30000) {
            verdict1.textContent = 'CONFIRMED';
            verdict1.className = 'claim-verdict confirmed';
        } else if (maxThought > 10000) {
            verdict1.textContent = 'PARTIALLY';
            verdict1.className = 'claim-verdict partial';
        } else {
            verdict1.textContent = 'NOT REPRODUCED';
            verdict1.className = 'claim-verdict refuted';
        }
    }

    // Claim 2: Flash gets trapped in loops
    if (monoSummary) {
        const failRate = monoSummary.failure_rate || 0;
        document.getElementById('flashFailRate').textContent = `${(failRate * 100).toFixed(0)}%`;

        const budgetSummary = summaries.thinking_budget;
        if (budgetSummary) {
            const reduction = monoSummary.avg_thought_tokens > 0
                ? ((1 - budgetSummary.avg_thought_tokens / monoSummary.avg_thought_tokens) * 100).toFixed(0)
                : 0;
            document.getElementById('budgetEffect').textContent = `${reduction}% reduction`;
        }

        const verdict2 = document.getElementById('verdict2');
        if (failRate > 0.1 || (monoSummary.max_thought_tokens > 20000)) {
            verdict2.textContent = 'CONFIRMED';
            verdict2.className = 'claim-verdict confirmed';
        } else if (monoSummary.std_duration > 10) {
            verdict2.textContent = 'PARTIALLY';
            verdict2.className = 'claim-verdict partial';
        } else {
            verdict2.textContent = 'NOT OBSERVED';
            verdict2.className = 'claim-verdict refuted';
        }
    }

    // Claim 3: Pro is more efficient
    const proSummary = summaries.pro_model;
    if (proSummary && monoSummary) {
        const costDiff = proSummary.avg_cost > 0 && monoSummary.avg_cost > 0
            ? (proSummary.avg_cost / monoSummary.avg_cost).toFixed(1) + 'x'
            : '—';
        document.getElementById('proCostComparison').textContent = costDiff;
        document.getElementById('proFailRate').textContent = `${((proSummary.failure_rate || 0) * 100).toFixed(0)}%`;

        const verdict3 = document.getElementById('verdict3');
        if (proSummary.failure_rate < monoSummary.failure_rate && proSummary.avg_thought_tokens < monoSummary.avg_thought_tokens) {
            verdict3.textContent = 'CONFIRMED';
            verdict3.className = 'claim-verdict confirmed';
        } else if (proSummary.avg_thought_tokens < monoSummary.avg_thought_tokens) {
            verdict3.textContent = 'PARTIALLY';
            verdict3.className = 'claim-verdict partial';
        } else {
            verdict3.textContent = 'NOT CONFIRMED';
            verdict3.className = 'claim-verdict refuted';
        }
    }
}

// ── Latency Chart ──
function renderLatencyChart(data) {
    const ctx = document.getElementById('latencyChart').getContext('2d');
    const summaries = data.summaries;
    const strategies = Object.keys(summaries);

    const labels = strategies.map(s => summaries[s].name);
    const avgData = strategies.map(s => summaries[s].avg_duration);
    const minData = strategies.map(s => summaries[s].min_duration);
    const maxData = strategies.map(s => summaries[s].max_duration);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Avg Latency',
                    data: avgData,
                    backgroundColor: strategies.map(s => STRATEGY_COLORS[s]?.bg || 'rgba(99,102,241,0.5)'),
                    borderColor: strategies.map(s => STRATEGY_COLORS[s]?.border || '#6366f1'),
                    borderWidth: 1.5,
                    borderRadius: 6,
                },
                {
                    label: 'Min Latency',
                    data: minData,
                    backgroundColor: 'rgba(52, 211, 153, 0.25)',
                    borderColor: '#34d399',
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'Max Latency',
                    data: maxData,
                    backgroundColor: 'rgba(251, 113, 133, 0.25)',
                    borderColor: '#fb7185',
                    borderWidth: 1,
                    borderRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.raw.toFixed(2)}s`
                    }
                }
            },
            scales: {
                y: {
                    title: { display: true, text: 'Seconds' },
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
                x: {
                    ticks: { font: { size: 10 }, maxRotation: 45 },
                    grid: { display: false },
                },
            },
        },
    });
}

// ── Thought Tokens Chart ──
function renderThoughtChart(data) {
    const ctx = document.getElementById('thoughtChart').getContext('2d');
    const summaries = data.summaries;
    const strategies = Object.keys(summaries);

    const labels = strategies.map(s => summaries[s].name);
    const avgData = strategies.map(s => summaries[s].avg_thought_tokens);
    const maxData = strategies.map(s => summaries[s].max_thought_tokens);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                {
                    label: 'Avg Thought Tokens',
                    data: avgData,
                    backgroundColor: strategies.map(s => STRATEGY_COLORS[s]?.bg || 'rgba(99,102,241,0.5)'),
                    borderColor: strategies.map(s => STRATEGY_COLORS[s]?.border || '#6366f1'),
                    borderWidth: 1.5,
                    borderRadius: 6,
                },
                {
                    label: 'Max Thought Tokens',
                    data: maxData,
                    backgroundColor: 'rgba(251, 113, 133, 0.3)',
                    borderColor: '#fb7185',
                    borderWidth: 1,
                    borderRadius: 4,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => `${ctx.dataset.label}: ${ctx.raw.toLocaleString()}`
                    }
                }
            },
            scales: {
                y: {
                    title: { display: true, text: 'Tokens' },
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
                x: {
                    ticks: { font: { size: 10 }, maxRotation: 45 },
                    grid: { display: false },
                },
            },
        },
    });
}

// ── Cost Chart ──
function renderCostChart(data) {
    const ctx = document.getElementById('costChart').getContext('2d');
    const summaries = data.summaries;
    const strategies = Object.keys(summaries);

    const labels = strategies.map(s => summaries[s].name);
    const costData = strategies.map(s => summaries[s].avg_cost * 1000);  // Convert to millicents for readability

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [{
                label: 'Avg Cost (×10⁻³ $)',
                data: costData,
                backgroundColor: strategies.map(s => STRATEGY_COLORS[s]?.bg || 'rgba(99,102,241,0.5)'),
                borderColor: strategies.map(s => STRATEGY_COLORS[s]?.border || '#6366f1'),
                borderWidth: 1.5,
                borderRadius: 6,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => `$${(ctx.raw / 1000).toFixed(5)}`
                    }
                }
            },
            scales: {
                y: {
                    title: { display: true, text: 'Cost (× $0.001)' },
                    beginAtZero: true,
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
                x: {
                    ticks: { font: { size: 10 }, maxRotation: 45 },
                    grid: { display: false },
                },
            },
        },
    });
}

// ── Scatter: Thought Tokens vs Latency ──
function renderScatterChart(data) {
    const ctx = document.getElementById('scatterChart').getContext('2d');
    const runs = data.raw_runs.filter(r => r.success);

    // Group by strategy
    const strategyGroups = {};
    runs.forEach(r => {
        if (!strategyGroups[r.strategy]) strategyGroups[r.strategy] = [];
        strategyGroups[r.strategy].push({
            x: r.thought_tokens,
            y: r.duration,
            word: r.word,
        });
    });

    const datasets = Object.entries(strategyGroups).map(([key, points]) => ({
        label: data.summaries[key]?.name || key,
        data: points,
        backgroundColor: STRATEGY_COLORS[key]?.bg || 'rgba(99,102,241,0.5)',
        borderColor: STRATEGY_COLORS[key]?.border || '#6366f1',
        borderWidth: 1.5,
        pointRadius: 5,
        pointHoverRadius: 8,
    }));

    new Chart(ctx, {
        type: 'scatter',
        data: { datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: ctx => {
                            const p = ctx.raw;
                            return `${ctx.dataset.label}: ${p.x.toLocaleString()} tokens, ${p.y.toFixed(1)}s (${p.word})`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    title: { display: true, text: 'Thought Tokens' },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
                y: {
                    title: { display: true, text: 'Latency (s)' },
                    grid: { color: 'rgba(255,255,255,0.04)' },
                },
            },
        },
    });
}

// ── Comparison Table ──
function renderComparisonTable(data) {
    const summaries = data.summaries;
    const strategies = Object.keys(summaries);

    // Header
    const headerRow = document.getElementById('tableHeader');
    headerRow.innerHTML = '<th>Metric</th>';
    strategies.forEach(s => {
        const th = document.createElement('th');
        th.textContent = summaries[s].name;
        headerRow.appendChild(th);
    });

    // Rows
    const metrics = [
        { key: 'avg_duration', label: 'Avg Latency', fmt: v => `${v.toFixed(2)}s`, best: 'min' },
        { key: 'min_duration', label: 'Min Latency', fmt: v => `${v.toFixed(2)}s`, best: 'min' },
        { key: 'max_duration', label: 'Max Latency', fmt: v => `${v.toFixed(2)}s`, best: 'min' },
        { key: 'std_duration', label: 'Latency StdDev', fmt: v => `±${v.toFixed(2)}s`, best: 'min' },
        { key: 'avg_thought_tokens', label: 'Avg Thought Tokens', fmt: v => v.toLocaleString(undefined, { maximumFractionDigits: 0 }), best: 'min' },
        { key: 'max_thought_tokens', label: 'Max Thought Tokens', fmt: v => v.toLocaleString(undefined, { maximumFractionDigits: 0 }), best: 'min' },
        { key: 'avg_total_tokens', label: 'Avg Total Tokens', fmt: v => v.toLocaleString(undefined, { maximumFractionDigits: 0 }), best: 'min' },
        { key: 'avg_cost', label: 'Avg Cost', fmt: v => `$${v.toFixed(5)}`, best: 'min' },
        { key: 'api_success_rate', label: 'API Success Rate', fmt: v => `${(v * 100).toFixed(0)}%`, best: 'max' },
        { key: 'valid_output_rate', label: 'Valid Output Rate', fmt: v => `${(v * 100).toFixed(0)}%`, best: 'max' },
        { key: 'failure_rate', label: 'Failure Rate', fmt: v => `${(v * 100).toFixed(0)}%`, best: 'min' },
        { key: 'successful_runs', label: 'Successful Runs', fmt: v => v, best: 'max' },
    ];

    const tbody = document.getElementById('tableBody');
    tbody.innerHTML = '';

    metrics.forEach(metric => {
        const tr = document.createElement('tr');
        const tdLabel = document.createElement('td');
        tdLabel.innerHTML = `<span class="metric-label">${metric.label}</span>`;
        tr.appendChild(tdLabel);

        const values = strategies.map(s => summaries[s][metric.key] || 0);
        const nonZeroValues = values.filter(v => v > 0);
        const bestVal = metric.best === 'min'
            ? Math.min(...(nonZeroValues.length ? nonZeroValues : values))
            : Math.max(...values);
        const worstVal = metric.best === 'min' ? Math.max(...values) : Math.min(...values);

        strategies.forEach((s, i) => {
            const td = document.createElement('td');
            const val = values[i];
            td.textContent = metric.fmt(val);
            if (val === bestVal && nonZeroValues.length > 0) td.classList.add('best-value');
            if (val === worstVal && val !== bestVal) td.classList.add('worst-value');
            tr.appendChild(td);
        });

        tbody.appendChild(tr);
    });
}

// ── Individual Runs ──
function renderRunsGrid(data, filters = {}) {
    const grid = document.getElementById('runsGrid');
    grid.innerHTML = '';

    let runs = data.raw_runs;

    // Apply filters
    if (filters.strategy && filters.strategy !== 'all') {
        runs = runs.filter(r => r.strategy === filters.strategy);
    }
    if (filters.word && filters.word !== 'all') {
        runs = runs.filter(r => r.word === filters.word);
    }
    if (filters.failedOnly) {
        runs = runs.filter(r => !r.success);
    }

    if (runs.length === 0) {
        grid.innerHTML = '<div class="empty-state"><p>No runs match the current filters.</p></div>';
        return;
    }

    runs.forEach(run => {
        const card = document.createElement('div');
        card.className = `run-card ${!run.success ? (run.timed_out ? 'timeout' : 'failed') : ''}`;

        const statusClass = run.success ? 'success' : 'fail';
        const statusText = run.success ? '✓ OK' : (run.timed_out ? '⏰ TIMEOUT' : '✗ ERROR');

        card.innerHTML = `
            <div class="run-header">
                <span class="run-strategy">${run.strategy_name}</span>
                <span class="run-status ${statusClass}">${statusText}</span>
            </div>
            <div class="run-word">Word: "${run.word}" · Iteration ${run.iteration}</div>
            <div class="run-metrics">
                <div class="run-metric">
                    <span class="run-metric-label">Latency</span>
                    <span class="run-metric-value">${run.duration.toFixed(1)}s</span>
                </div>
                <div class="run-metric">
                    <span class="run-metric-label">Thought</span>
                    <span class="run-metric-value">${run.thought_tokens.toLocaleString()}</span>
                </div>
                <div class="run-metric">
                    <span class="run-metric-label">Total</span>
                    <span class="run-metric-value">${run.total_tokens.toLocaleString()}</span>
                </div>
                <div class="run-metric">
                    <span class="run-metric-label">Cost</span>
                    <span class="run-metric-value">$${run.cost.toFixed(5)}</span>
                </div>
            </div>
            ${run.error ? `<div style="margin-top:0.5rem;font-size:0.7rem;color:var(--accent-rose);word-break:break-all;">${run.error.substring(0, 120)}</div>` : ''}
        `;
        grid.appendChild(card);
    });
}

// ── Cascade Results ──
function renderCascadeResults(data) {
    const cascade = data.summaries.cascade;
    const mono = data.summaries.monolithic || data.summaries.monolithic_schema;

    if (!cascade || !mono) return;

    // Thought token reduction
    if (mono.avg_thought_tokens > 0) {
        const reduction = ((1 - cascade.avg_thought_tokens / mono.avg_thought_tokens) * 100).toFixed(0);
        const el = document.getElementById('cascadeThoughtReduction');
        el.textContent = `${reduction}%`;
        el.style.color = reduction > 0 ? 'var(--accent-emerald)' : 'var(--accent-rose)';
    }

    // Latency difference
    if (mono.avg_duration > 0) {
        const diff = ((cascade.avg_duration / mono.avg_duration - 1) * 100).toFixed(0);
        const el = document.getElementById('cascadeLatencyDiff');
        const prefix = diff > 0 ? '+' : '';
        el.textContent = `${prefix}${diff}%`;
        el.style.color = diff < 0 ? 'var(--accent-emerald)' : 'var(--accent-amber)';
    }

    // Cost difference
    if (mono.avg_cost > 0) {
        const diff = ((cascade.avg_cost / mono.avg_cost - 1) * 100).toFixed(0);
        const el = document.getElementById('cascadeCostDiff');
        const prefix = diff > 0 ? '+' : '';
        el.textContent = `${prefix}${diff}%`;
        el.style.color = diff < 0 ? 'var(--accent-emerald)' : 'var(--accent-amber)';
    }

    // Failure rate
    document.getElementById('cascadeFailRate').textContent =
        `${((cascade.failure_rate || 0) * 100).toFixed(0)}%`;
}

// ── Filters ──
function setupFilters(data) {
    const strategySelect = document.getElementById('filterStrategy');
    const wordSelect = document.getElementById('filterWord');
    const failedCheckbox = document.getElementById('filterFailed');

    // Populate strategy options
    const strategies = [...new Set(data.raw_runs.map(r => r.strategy))];
    strategies.forEach(s => {
        const opt = document.createElement('option');
        opt.value = s;
        opt.textContent = data.summaries[s]?.name || s;
        strategySelect.appendChild(opt);
    });

    // Populate word options
    const words = [...new Set(data.raw_runs.map(r => r.word))];
    words.forEach(w => {
        const opt = document.createElement('option');
        opt.value = w;
        opt.textContent = w;
        wordSelect.appendChild(opt);
    });

    // Event listeners
    const applyFilters = () => {
        renderRunsGrid(data, {
            strategy: strategySelect.value,
            word: wordSelect.value,
            failedOnly: failedCheckbox.checked,
        });
    };

    strategySelect.addEventListener('change', applyFilters);
    wordSelect.addEventListener('change', applyFilters);
    failedCheckbox.addEventListener('change', applyFilters);
}
