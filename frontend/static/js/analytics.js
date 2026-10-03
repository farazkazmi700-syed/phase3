'use strict';

/**
 * analytics.js — Phase 3 Analytics System frontend controller
 *
 * Responsibilities:
 *  - Fetch /api/analytics/data (FR14)
 *  - Render 7 Chart.js responsive graphs (FR20)
 *  - Populate 6 analytical tables + session insights (FR19, FR21)
 *  - Render KPI summary cards (FR21)
 *  - Handle "End & Save Summary" button → POST /api/analytics/end-session (FR22)
 */

/* ============================================================
   Colour palette — dark-theme consistent with style.css tokens
   ============================================================ */
const PALETTE = {
  blue:       '#3B82F6',
  purple:     '#8B5CF6',
  green:      '#10B981',
  yellow:     '#FACC15',
  orange:     '#F97316',
  pink:       '#EC4899',
  cyan:       '#06B6D4',
  red:        '#EF4444',
  border:     '#334155',
  text:       '#F8FAFC',
  muted:      '#94A3B8',
  background: '#1E293B',
};

/** Five topic colours — index-matched to the TOPIC_MAP order in analytics.py */
const TOPIC_COLORS = [
  PALETTE.blue,
  PALETTE.purple,
  PALETTE.green,
  PALETTE.yellow,
  PALETTE.cyan,
  PALETTE.orange,  // "General / Other"
];

/* Chart.js global defaults for dark theme */
Chart.defaults.color            = PALETTE.muted;
Chart.defaults.borderColor      = PALETTE.border;
Chart.defaults.font.family      = "'Inter', sans-serif";
Chart.defaults.font.size        = 12;
Chart.defaults.plugins.legend.labels.boxWidth = 14;
Chart.defaults.plugins.legend.labels.padding  = 14;

/* ============================================================
   Utility helpers
   ============================================================ */

/** Escape HTML to prevent XSS when inserting user data into innerHTML */
function esc(val) {
  return String(val ?? '—')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Show or hide an element using the 'hidden' CSS class */
function show(id) { document.getElementById(id)?.classList.remove('hidden'); }
function hide(id) { document.getElementById(id)?.classList.add('hidden'); }

/** Format ISO timestamp for display */
function formatDateTime(iso) {
  if (!iso) return '—';
  try {
    let str = String(iso).trim();
    if (!str.endsWith('Z') && !/[+-]\d{2}(:\d{2})?$/.test(str)) {
      str += 'Z';
    }
    const d = new Date(str);
    if (isNaN(d.getTime())) return '—';
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '—';
  }
}

/** Create a responsive Chart.js chart and return the instance */
function makeChart(canvasId, type, data, options = {}) {
  const ctx = document.getElementById(canvasId)?.getContext('2d');
  if (!ctx) return null;

  const defaults = {
    responsive:          true,
    maintainAspectRatio: false,
    plugins: {
      legend:  { position: 'bottom' },
      tooltip: { callbacks: {} },
    },
    animation: { duration: 600, easing: 'easeInOutQuart' },
  };

  // Deep-merge options into defaults (one level deep for plugins)
  const merged = { ...defaults, ...options };
  if (options.plugins) {
    merged.plugins = { ...defaults.plugins, ...options.plugins };
  }

  return new Chart(ctx, { type, data, options: merged });
}

/* ============================================================
   FR21: KPI card rendering
   ============================================================ */

/**
 * Render the 6 summary KPI cards at the top of the dashboard.
 * @param {Object} d  Full analytics payload from /api/analytics/data
 */
function renderKPICards(d) {
  const grid = document.getElementById('kpi-grid');
  if (!grid) return;

  const cards = [
    { label: 'Total Sessions',    value: d.total_sessions,                  color: 'blue'   },
    { label: 'Total Responses',   value: d.total_messages,                  color: 'purple' },
    { label: 'Overall Accuracy',  value: `${d.overall_accuracy}%`,          color: 'green'  },
    { label: 'Avg Rating',        value: `${d.avg_rating} / 4`,             color: 'yellow' },
    { label: 'Correct Replies',   value: `${d.correct_count} / ${d.rated_count}`, color: 'green'  },
    { label: 'Incorrect Replies', value: `${d.incorrect_count} / ${d.rated_count}`, color: 'red'    },
  ];

  grid.innerHTML = cards.map(c => `
    <div class="kpi-card kpi-${c.color}">
      <div class="kpi-value">${esc(c.value)}</div>
      <div class="kpi-label">${esc(c.label)}</div>
    </div>
  `).join('');
}

/* ============================================================
   FR20: Chart rendering functions
   ============================================================ */

/**
 * FR20: Topic distribution pie chart.
 * Shows the share of messages for each AI domain.
 */
function renderTopicDistChart(topicAccuracy) {
  const labels = Object.keys(topicAccuracy);
  const data   = labels.map(l => topicAccuracy[l].count);
  const colors = labels.map((_, i) => TOPIC_COLORS[i % TOPIC_COLORS.length]);

  makeChart('chart-topic-dist', 'pie', {
    labels,
    datasets: [{
      data,
      backgroundColor: colors,
      borderColor:     PALETTE.background,
      borderWidth:     2,
      hoverOffset:     6,
    }],
  }, {
    plugins: {
      legend: { position: 'right' },
      tooltip: {
        callbacks: {
          label: (ctx) => ` ${ctx.label}: ${ctx.parsed} messages`,
        },
      },
    },
  });
}

/**
 * FR20: Accuracy per topic bar chart.
 * Displays accuracy percentage for each classified domain.
 */
function renderTopicAccChart(topicAccuracy) {
  const labels   = Object.keys(topicAccuracy);
  const accData  = labels.map(l => topicAccuracy[l].accuracy);
  const colors   = labels.map((_, i) => TOPIC_COLORS[i % TOPIC_COLORS.length]);

  makeChart('chart-topic-acc', 'bar', {
    labels,
    datasets: [{
      label:           'Accuracy %',
      data:            accData,
      backgroundColor: colors.map(c => c + 'BB'),
      borderColor:     colors,
      borderWidth:     2,
      borderRadius:    6,
    }],
  }, {
    scales: {
      y: {
        beginAtZero: true,
        max:         100,
        ticks: { callback: v => `${v}%` },
        grid:  { color: PALETTE.border },
      },
      x: { grid: { display: false } },
    },
    plugins: {
      legend:  { display: false },
      tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y}%` } },
    },
  });
}

/**
 * FR20: Accuracy vs Phase line graph.
 * Shows how accuracy changes across Start, Middle, and End phases.
 */
function renderPhaseAccChart(phaseAccuracy) {
  const phases = ['Start', 'Middle', 'End'];
  const data   = phases.map(p => phaseAccuracy[p] ?? 0);

  makeChart('chart-phase-acc', 'line', {
    labels: phases,
    datasets: [{
      label:           'Accuracy %',
      data,
      borderColor:     PALETTE.blue,
      backgroundColor: PALETTE.blue + '33',
      pointBackgroundColor: PALETTE.blue,
      pointRadius:     6,
      pointHoverRadius: 8,
      fill:            true,
      tension:         0.35,
    }],
  }, {
    scales: {
      y: {
        beginAtZero: true,
        max:         100,
        ticks: { callback: v => `${v}%` },
        grid:  { color: PALETTE.border },
      },
      x: { grid: { display: false } },
    },
    plugins: {
      legend:  { display: false },
      tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y}%` } },
    },
  });
}

/**
 * FR20: Correctness per reply bar chart.
 * Each bar represents one assistant response's accuracy score.
 */
function renderReplyAccChart(series) {
  // Limit to last 30 replies for readability; user can scroll the table for all.
  const display = series.slice(-30);
  const labels  = display.map(r => `#${r.index}`);
  const data    = display.map(r => r.accuracy);
  const colors  = display.map(r =>
    r.accuracy >= 75 ? PALETTE.green :
    r.accuracy >= 40 ? PALETTE.yellow :
    PALETTE.red
  );

  makeChart('chart-reply-acc', 'bar', {
    labels,
    datasets: [{
      label:           'Accuracy %',
      data,
      backgroundColor: colors.map(c => c + 'BB'),
      borderColor:     colors,
      borderWidth:     1,
      borderRadius:    4,
    }],
  }, {
    scales: {
      y: {
        beginAtZero: true,
        max:         100,
        ticks: { callback: v => `${v}%` },
        grid:  { color: PALETTE.border },
      },
      x: {
        ticks: { maxRotation: 45, font: { size: 10 } },
        grid:  { display: false },
      },
    },
    plugins: {
      legend:  { display: false },
      tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y}%` } },
    },
  });
}

/**
 * FR20: Response time trend line graph.
 * Shows latency in milliseconds for each reply in chronological order.
 */
function renderResponseTimeChart(timeSeries) {
  const labels = timeSeries.map((_, i) => `#${i + 1}`);

  makeChart('chart-response-time', 'line', {
    labels,
    datasets: [{
      label:           'Response Time (ms)',
      data:            timeSeries,
      borderColor:     PALETTE.purple,
      backgroundColor: PALETTE.purple + '22',
      pointRadius:     timeSeries.length < 20 ? 4 : 2,
      fill:            true,
      tension:         0.3,
    }],
  }, {
    scales: {
      y: {
        beginAtZero: true,
        ticks: { callback: v => `${v}ms` },
        grid:  { color: PALETTE.border },
      },
      x: {
        ticks: { maxRotation: 0, font: { size: 10 }, maxTicksLimit: 12 },
        grid:  { display: false },
      },
    },
    plugins: {
      legend:  { display: false },
      tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y} ms` } },
    },
  });
}

/**
 * FR20: Rating distribution bar chart.
 * Counts of each star rating (1–4) given as feedback.
 */
function renderRatingDistChart(ratingDist) {
  const labels = ['1 Star', '2 Stars', '3 Stars', '4 Stars'];
  const data   = ['1', '2', '3', '4'].map(k => ratingDist[k] ?? 0);
  const colors = [PALETTE.red, PALETTE.orange, PALETTE.yellow, PALETTE.green];

  makeChart('chart-rating-dist', 'bar', {
    labels,
    datasets: [{
      label:           'Count',
      data,
      backgroundColor: colors.map(c => c + 'BB'),
      borderColor:     colors,
      borderWidth:     2,
      borderRadius:    6,
    }],
  }, {
    scales: {
      y: {
        beginAtZero: true,
        ticks: { stepSize: 1 },
        grid:  { color: PALETTE.border },
      },
      x: { grid: { display: false } },
    },
    plugins: {
      legend:  { display: false },
      tooltip: { callbacks: { label: ctx => ` ${ctx.parsed.y} responses` } },
    },
  });
}

/**
 * FR20: Length preference pie chart.
 * Shows proportion of Short / To the Point / Lengthy selections.
 */
function renderLengthDistChart(lengthDist) {
  const labels = Object.keys(lengthDist);
  const data   = Object.values(lengthDist);
  const colors = [PALETTE.cyan, PALETTE.green, PALETTE.orange];

  makeChart('chart-length-dist', 'pie', {
    labels,
    datasets: [{
      data,
      backgroundColor: colors,
      borderColor:     PALETTE.background,
      borderWidth:     2,
      hoverOffset:     6,
    }],
  }, {
    plugins: {
      legend: { position: 'right' },
      tooltip: { callbacks: { label: ctx => ` ${ctx.label}: ${ctx.parsed}` } },
    },
  });
}

/* ============================================================
   FR19: Table population helpers
   ============================================================ */

/** Helper: inject rows into a <tbody> given an array of <tr> HTML strings */
function fillTable(tbodyId, rowsHtml) {
  const tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  tbody.innerHTML = rowsHtml.length
    ? rowsHtml.join('')
    : '<tr><td colspan="99" class="an-empty">No data available yet.</td></tr>';
}

/** Return a coloured badge span for correctness values */
function correctnessBadge(val) {
  const cls = val === 'Correct'   ? 'badge-correct'
            : val === 'Partial'   ? 'badge-partial'
            : val === 'Incorrect' ? 'badge-incorrect'
            : 'badge-none';
  return `<span class="an-badge ${cls}">${esc(val)}</span>`;
}

/** Return a coloured badge span for phase values */
function phaseBadge(val) {
  const cls = val === 'Start'  ? 'badge-start'
            : val === 'Middle' ? 'badge-middle'
            : 'badge-end';
  return `<span class="an-badge ${cls}">${esc(val)}</span>`;
}

/**
 * FR19: Topic vs accuracy table
 */
function renderTopicAccTable(topicAccuracy) {
  const rows = Object.entries(topicAccuracy).map(([topic, v]) => `
    <tr>
      <td>${esc(topic)}</td>
      <td class="td-num">${v.count}</td>
      <td class="td-num">${v.rated}</td>
      <td class="td-num accent-${v.accuracy >= 70 ? 'green' : v.accuracy >= 40 ? 'yellow' : 'red'}">${v.accuracy}%</td>
    </tr>
  `);
  fillTable('tbl-topic-acc-body', rows);
}

/**
 * FR19: Reply correctness table (shows all replies with their metadata)
 */
function renderReplyCorrectnessTable(series) {
  const rows = series.map(r => `
    <tr>
      <td class="td-num">${r.index}</td>
      <td>${formatDateTime(r.timestamp)}</td>
      <td><code class="session-id">${esc(r.session_id)}</code></td>
      <td>${esc(r.topic)}</td>
      <td>${phaseBadge(r.phase)}</td>
      <td>${correctnessBadge(r.correctness)}</td>
      <td class="td-num">${r.accuracy}%</td>
      <td class="td-num">${r.rating ?? '—'}</td>
      <td>${esc(r.length)}</td>
    </tr>
  `);
  fillTable('tbl-reply-corr-body', rows);
}

/**
 * FR19: Phase-wise accuracy table
 */
function renderPhaseAccTable(phaseAccuracy) {
  const phases = ['Start', 'Middle', 'End'];
  const rows = phases.map(p => `
    <tr>
      <td>${phaseBadge(p)}</td>
      <td class="td-num accent-${(phaseAccuracy[p] ?? 0) >= 70 ? 'green' : 'yellow'}">${phaseAccuracy[p] ?? 0}%</td>
    </tr>
  `);
  fillTable('tbl-phase-acc-body', rows);
}

/**
 * FR19: Response time summary table
 */
function renderResponseTimeSummaryTable(stats) {
  const rows = [
    ['Total Measured',  stats.count],
    ['Minimum (ms)',    stats.min],
    ['Maximum (ms)',    stats.max],
    ['Average (ms)',    stats.avg],
  ].map(([label, val]) => `
    <tr>
      <td>${esc(label)}</td>
      <td class="td-num">${val}</td>
    </tr>
  `);
  fillTable('tbl-resp-time-body', rows);
}

/**
 * FR19: Rating distribution table
 */
function renderRatingDistTable(ratingDist) {
  const rows = ['1', '2', '3', '4'].map(k => `
    <tr>
      <td>${k} Star${Number(k) > 1 ? 's' : ''}</td>
      <td class="td-num">${ratingDist[k] ?? 0}</td>
    </tr>
  `);
  fillTable('tbl-rating-dist-body', rows);
}

/**
 * FR19: Length preference table
 */
function renderLengthPrefTable(lengthDist) {
  const rows = Object.entries(lengthDist).map(([cat, count]) => `
    <tr>
      <td>${esc(cat)}</td>
      <td class="td-num">${count}</td>
    </tr>
  `);
  fillTable('tbl-length-pref-body', rows);
}

/**
 * FR21: Session-level insights table
 */
function renderSessionInsightsTable(sessions) {
  const rows = sessions.map(s => `
    <tr>
      <td><code class="session-id">${esc(s.session_id)}</code></td>
      <td>${formatDateTime(s.created_at)}</td>
      <td class="td-num">${s.message_count}</td>
      <td>${s.topics.map(t => `<span class="an-badge badge-topic">${esc(t)}</span>`).join(' ')}</td>
      <td class="td-num">${s.accuracy != null ? s.accuracy + '%' : '—'}</td>
      <td class="td-num">${s.avg_rating != null ? s.avg_rating + ' / 4' : '—'}</td>
    </tr>
  `);
  fillTable('tbl-sessions-body', rows);
}

/* ============================================================
   FR22: End session handler
   ============================================================ */

/**
 * POST /api/analytics/end-session — permanently save the final analytics
 * summary for this user.  Shows a toast on success or failure.
 */
async function handleEndSession() {
  const btn   = document.getElementById('btn-end-session');
  const toast = document.getElementById('an-toast');
  if (!btn || !toast) return;

  btn.disabled    = true;
  btn.textContent = 'Saving…';

  try {
    const res  = await fetch('/api/analytics/end-session', {
      method:      'POST',
      headers:     { 'Content-Type': 'application/json' },
      credentials: 'include',
      body:        JSON.stringify({}),
    });
    const data = await res.json().catch(() => ({}));

    if (res.ok && data.success) {
      toast.textContent = 'Session summary saved permanently.';
      toast.className   = 'an-toast an-toast-success';
    } else {
      toast.textContent = `Error: ${data.error || 'Could not save summary.'}`;
      toast.className   = 'an-toast an-toast-error';
    }
  } catch (err) {
    toast.textContent = `Network error: ${err.message}`;
    toast.className   = 'an-toast an-toast-error';
  }

  // Show toast then auto-hide after 4 s.
  show('an-toast');
  btn.disabled    = false;
  btn.textContent = 'End & Save Summary';
  setTimeout(() => hide('an-toast'), 4000);
}

/* ============================================================
   Main initialisation — fetch data and wire everything together
   ============================================================ */

async function initAnalytics() {
  show('an-loader');

  try {
    const res  = await fetch('/api/analytics/data', { credentials: 'include' });
    const data = await res.json().catch(() => null);

    if (!res.ok || !data) {
      throw new Error((data && data.error) || `HTTP ${res.status}`);
    }

    hide('an-loader');

    // Render KPI summary cards (FR21)
    renderKPICards(data);

    // Render all FR20 charts
    renderTopicDistChart(data.topic_accuracy);
    renderTopicAccChart(data.topic_accuracy);
    renderPhaseAccChart(data.phase_accuracy);
    renderReplyAccChart(data.reply_accuracy_series);
    renderResponseTimeChart(data.response_time_stats.series);
    renderRatingDistChart(data.rating_distribution);
    renderLengthDistChart(data.length_distribution);

    // Populate all FR19 tables
    renderTopicAccTable(data.topic_accuracy);
    renderReplyCorrectnessTable(data.reply_accuracy_series);
    renderPhaseAccTable(data.phase_accuracy);
    renderResponseTimeSummaryTable(data.response_time_stats);
    renderRatingDistTable(data.rating_distribution);
    renderLengthPrefTable(data.length_distribution);

    // FR21: session insights table
    renderSessionInsightsTable(data.session_insights);

    // Reveal the full dashboard
    show('an-content');

  } catch (err) {
    hide('an-loader');
    const errorEl = document.getElementById('an-error');
    if (errorEl) {
      errorEl.textContent = `Failed to load analytics: ${err.message}`;
      show('an-error');
    }
  }
}

/* ============================================================
   Bootstrap
   ============================================================ */
document.addEventListener('DOMContentLoaded', () => {
  // Initialise dashboard data
  initAnalytics();

  // FR22: wire End Session button
  document.getElementById('btn-end-session')
    ?.addEventListener('click', handleEndSession);
});
