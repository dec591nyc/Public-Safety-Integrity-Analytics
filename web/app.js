const fmt = new Intl.NumberFormat('zh-TW');

const priorityTopics = [
  'property_fraud',
  'drug_public_safety',
  'violence_personal',
  'sexual_safety',
  'integrity_governance',
  'digital_ip',
  'other_types',
  'all_types'
];

const trendWindowMonths = 12;
const allRegionsLabel = '全部縣市';
const peakSegmentLimit = 10;
const state = {
  summary: null,
  activeTopic: null,
  activeRegion: null,
  activeMetric: null,
  activeView: 'year',
  activeAnnualTab: 'kpi'
};

function el(id) { return document.getElementById(id); }

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}

function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch {
    return '';
  }
}

function safeColor(value) {
  return /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#64748b';
}

function formatMonth(value) {
  return /^\d{6}$/.test(value) ? `${value.slice(0, 4)} 年 ${Number(value.slice(4))} 月` : value;
}

function formatMonthLabel(value) {
  return /^\d{6}$/.test(value) ? `${value.slice(0, 4)}/${value.slice(4, 6)}` : value;
}

function formatChange(current, previous) {
  if (!previous) return '無前月基準';
  const change = ((current - previous) / previous) * 100;
  const sign = change > 0 ? '+' : '';
  return `${sign}${change.toFixed(1)}%`;
}

function showToast(message) {
  const toast = el('toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('is-visible');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('is-visible'), 3200);
}

async function getJson(url) {
  const isStaticDemo = window.location.hostname.endsWith('github.io') ||
    window.location.hostname.endsWith('vercel.app') ||
    window.location.protocol === 'file:' ||
    window.location.port === '5500' ||
    !window.location.port;

  let fetchUrl = url;
  if (isStaticDemo) {
    if (url === '/api/months') {
      fetchUrl = 'static_api/months.json';
    } else if (url.startsWith('/api/official-summary')) {
      const parts = url.split('?');
      const month = parts[1] ? (new URLSearchParams(parts[1]).get('month') || '202604') : '202604';
      fetchUrl = `static_api/official-summary_${month}.json`;
    }
  }

  try {
    const response = await fetch(fetchUrl);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  } catch (error) {
    if (!isStaticDemo && fetchUrl === url) {
      const fallback = url === '/api/months'
        ? 'static_api/months.json'
        : `static_api/official-summary_${new URLSearchParams(url.split('?')[1] || '').get('month') || '202604'}.json`;
      const response = await fetch(fallback);
      if (!response.ok) throw error;
      return response.json();
    }
    throw error;
  }
}

function currentMonth() {
  return el('month')?.value || '202604';
}

function topicList() {
  const topics = state.summary?.topic_drilldowns || [];
  return priorityTopics.map(id => topics.find(topic => topic.id === id)).filter(Boolean);
}

function allTopicRegions(topic) {
  return topic?.region_breakdowns?.length ? topic.region_breakdowns : (topic?.top_regions || []);
}

function segmentOtherRank(segment) {
  const metric = String(segment?.metric || '');
  const label = String(segment?.label || '');
  if (metric === '__other__' || label === '其他案類') return 2;
  if (metric === '其他' || label === '其他') return 1;
  return 0;
}

function orderedSegments(segments) {
  return [...(segments || [])]
    .filter(segment => Number(segment.count) > 0)
    .sort((a, b) => segmentOtherRank(a) - segmentOtherRank(b) ||
      Number(b.count || 0) - Number(a.count || 0) ||
      String(a.label || '').localeCompare(String(b.label || ''), 'zh-Hant'));
}

function caseMetricNames() {
  const allTypes = (state.summary?.topic_drilldowns || []).find(topic => topic.id === 'all_types');
  if (allTypes?.source_metrics?.length) return allTypes.source_metrics;
  return (state.summary?.metric_styles?.items || [])
    .map(item => item.metric)
    .filter(metric => metric && metric !== '總計');
}

function nationalRegion(topic) {
  return {
    geography: allRegionsLabel,
    total: Number(topic?.total || 0),
    share_pct: 100,
    previous_year_total: topic?.previous_year_total,
    yoy_pct: topic?.yoy_pct,
    segments: orderedSegments(topic?.segments || []),
    isNational: true,
  };
}

function selectableRegions(topic) {
  if (!topic) return [];
  return [nationalRegion(topic), ...allTopicRegions(topic)];
}

function findActiveTopic() {
  const topics = topicList();
  if (!topics.length) return null;
  if (!state.activeTopic || !topics.some(topic => topic.id === state.activeTopic)) {
    state.activeTopic = topics[0].id;
  }
  return topics.find(topic => topic.id === state.activeTopic) || topics[0];
}

function syncDrilldownSelection(topic) {
  const regions = selectableRegions(topic);
  if (!state.activeRegion || !regions.some(row => row.geography === state.activeRegion)) {
    state.activeRegion = regions[0]?.geography || null;
  }
  const segments = orderedSegments(topic?.segments || []);
  if (!state.activeMetric || !segments.some(row => row.metric === state.activeMetric)) {
    state.activeMetric = segments[0]?.metric || null;
  }
}

function selectedRegion(topic) {
  return selectableRegions(topic).find(row => row.geography === state.activeRegion) || selectableRegions(topic)[0] || null;
}

function selectedMetric(topic) {
  const segments = orderedSegments(topic?.segments || []);
  return segments.find(row => row.metric === state.activeMetric) || segments[0] || null;
}

function segmentCount(segments, metric) {
  return Number((segments || []).find(row => row.metric === metric)?.count || 0);
}

function trendWindow(rows, size = trendWindowMonths) {
  return (rows || []).slice(Math.max((rows || []).length - size, 0));
}

function latestTrendChange(rows) {
  const values = (rows || []).filter(row => Number.isFinite(Number(row.count)));
  if (values.length < 2) return '無前月基準';
  const last = values[values.length - 1];
  const previous = values[values.length - 2];
  return formatChange(Number(last.count), Number(previous.count));
}

function formatPct(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '無基準';
  const sign = Number(value) > 0 ? '+' : '';
  return `${sign}${Number(value).toFixed(1)}%`;
}

function formatSignedCount(value) {
  const numeric = Number(value || 0);
  const sign = numeric > 0 ? '+' : '';
  return `${sign}${fmt.format(numeric)} 件`;
}

function deltaClass(value) {
  const numeric = Number(value || 0);
  if (numeric > 0) return 'up';
  if (numeric < 0) return 'down';
  return '';
}

function renderLineChart(containerId, rows) {
  const container = el(containerId);
  if (!container) return;
  const series = trendWindow(rows).map(row => ({ month: row.month, count: Number(row.count || 0) }));
  if (series.length < 2) {
    container.innerHTML = '<div class="chart-empty compact"><p>趨勢資料不足</p></div>';
    return;
  }

  const width = 760;
  const height = container.classList.contains('compact') ? 190 : 240;
  const pad = { top: 18, right: 18, bottom: 30, left: 58 };
  const values = series.map(row => row.count);
  const maxVal = Math.max(...values);
  const minVal = Math.min(...values);
  const span = Math.max(maxVal - minVal, 1);
  const x = index => pad.left + (index * (width - pad.left - pad.right)) / Math.max(series.length - 1, 1);
  const y = value => height - pad.bottom - ((value - minVal) / span) * (height - pad.top - pad.bottom);
  const points = series.map((row, index) => `${x(index)},${y(row.count)}`).join(' ');
  const ticks = [0, 0.5, 1].map(ratio => {
    const value = minVal + span * ratio;
    const yy = y(value);
    return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" class="grid-line" />
      <text x="${pad.left - 8}" y="${yy + 4}" text-anchor="end">${fmt.format(Math.round(value))}</text>`;
  }).join('');
  const labelStep = Math.max(Math.ceil(series.length / 6), 1);
  const labels = series.map((row, index) => index % labelStep === 0 || index === series.length - 1
    ? `<text x="${x(index)}" y="${height - 10}" text-anchor="middle">${escapeHtml(formatMonthLabel(row.month))}</text>` : '').join('');
  const dots = series.map((row, index) => `<circle cx="${x(index)}" cy="${y(row.count)}" r="4">
    <title>${escapeHtml(formatMonth(row.month))}單月：${fmt.format(row.count)} 件</title>
  </circle>`).join('');

  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" aria-hidden="true">
    ${ticks}${labels}
    <polyline points="${points}" class="trend-line" />
    ${dots}
  </svg>`;
}

function renderStackedBarSegments(segments, total) {
  const visible = orderedSegments(segments);
  if (!visible.length || total <= 0) return '<span class="stacked-empty">無資料</span>';
  return visible.map(segment => {
    const width = Math.max((Number(segment.count) / total) * 100, 0.8);
    const title = `${segment.label}: ${fmt.format(segment.count)} 件 (${segment.share_pct}%)`;
    return `<span class="stacked-segment" style="width:${width}%; background:${safeColor(segment.color)}" title="${escapeHtml(title)}"></span>`;
  }).join('');
}

function renderSegmentLegend(segments, activeMetric) {
  const visible = orderedSegments(segments);
  return visible.map(segment => `
    <button type="button" class="segment-key ${segment.metric === activeMetric ? 'is-active' : ''}" data-metric="${escapeHtml(segment.metric)}">
      <i style="background:${safeColor(segment.color)}"></i>
      <span>${escapeHtml(segment.label)}</span>
      <strong>${fmt.format(segment.count)}</strong>
    </button>
  `).join('');
}

function renderTopicTabs(containerId, topics, active) {
  const container = el(containerId);
  if (!container) return;
  container.innerHTML = topics.map(topic => `
    <button type="button" class="topic-tab ${topic.id === active.id ? 'is-active' : ''}" data-topic-id="${escapeHtml(topic.id)}" role="listitem">
      <span>${escapeHtml(topic.label)}</span>
      <strong>${fmt.format(topic.total)}</strong>
    </button>
  `).join('');
  container.querySelectorAll('[data-topic-id]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeTopic = button.dataset.topicId;
      state.activeRegion = null;
      state.activeMetric = null;
      renderDashboard();
    });
  });
}

function renderTopicDetail() {
  const topics = topicList();
  if (!topics.length) {
    el('topic-title').textContent = '尚無主題資料';
    el('topic-description').textContent = '';
    el('topic-regions').innerHTML = '<div class="chart-empty compact"><p>尚無官方案類資料</p></div>';
    if (el('local-topic-tabs')) el('local-topic-tabs').innerHTML = '';
    if (el('topic-ai-analysis')) el('topic-ai-analysis').innerHTML = '';
    return;
  }
  const active = findActiveTopic();
  syncDrilldownSelection(active);
  renderTopicTabs('topic-tabs', topics, active);
  renderTopicTabs('local-topic-tabs', topics, active);

  el('topic-title').textContent = active.label;
  el('topic-description').textContent = active.description || '';
  const mainSegment = orderedSegments(active.segments)[0];
  const topRegion = selectedRegion(active);
  const metricNames = active.source_metrics || [];
  const topicScopeNote = active.is_total_scope
    ? `「${active.label}」包含官方 ${fmt.format(metricNames.length || caseMetricNames().length)} 個非總計案類，${formatMonth(state.summary.source_month)} 加總為 ${fmt.format(active.total)} 件，可和全國總案量核對。`
    : active.is_residual_scope
      ? `「${active.label}」收納未放入前六個分析主題的官方案類，本月合計 ${fmt.format(active.total)} 件；其中也包含官方原始欄位「其他」。`
      : `「${active.label}」是便於閱讀的分析集合，只加總下列官方案類：${metricNames.map(name => `「${name}」`).join('、')}。曲線每點是該主題單一月份件數；要和總案量核對請切到「全部類型」。`;
  if (el('topic-scope-note')) el('topic-scope-note').textContent = topicScopeNote;
  el('selected-topic-stats').innerHTML = [
    ['主題案量', `${fmt.format(active.total)} 件`, `占總案量 ${active.share_pct}%`],
    ['近月變化', latestTrendChange(active.trend), '與前一個月相比'],
    ['範圍 YoY', topRegion ? formatPct(topRegion.yoy_pct) : '無資料', topRegion ? `${topRegion.geography} 與去年同月比較` : ''],
    ['主要案類', mainSegment ? mainSegment.label : '無資料', mainSegment ? `${fmt.format(mainSegment.count)} 件` : ''],
  ].map(([label, value, note]) => `
    <div class="mini-stat">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
      <small>${escapeHtml(note)}</small>
    </div>
  `).join('');

  renderLineChart('topic-trend', active.trend || []);
  el('topic-national-bar').innerHTML = renderStackedBarSegments(active.segments, active.total);
  el('topic-legend').innerHTML = renderSegmentLegend(active.segments, state.activeMetric);
  el('topic-legend').querySelectorAll('[data-metric]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeMetric = button.dataset.metric;
      renderDashboard();
    });
  });

  const buildRegionMarkup = limit => [nationalRegion(active), ...allTopicRegions(active).slice(0, limit)].map(row => `
    <button type="button" class="region-row ${row.geography === state.activeRegion ? 'is-active' : ''} ${row.isNational ? 'is-national' : ''}" data-region="${escapeHtml(row.geography)}">
      <div class="region-label">
        <span>${escapeHtml(row.geography)}</span>
        <strong>${fmt.format(row.total)} 件</strong>
        <small>${row.isNational ? '全國範圍' : `YoY ${formatPct(row.yoy_pct)} · 占本主題 ${row.share_pct}%`}</small>
      </div>
      <div class="stacked-track" aria-label="${escapeHtml(row.geography)} ${escapeHtml(active.label)}案類構成">
        ${renderStackedBarSegments(row.segments, row.total)}
      </div>
    </button>
  `).join('') || '<div class="chart-empty compact"><p>尚無縣市資料</p></div>';

  [
    ['topic-regions', 5],
    ['local-regions', 12],
  ].forEach(([containerId, limit]) => {
    const container = el(containerId);
    if (!container) return;
    container.innerHTML = buildRegionMarkup(limit);
    container.querySelectorAll('[data-region]').forEach(button => {
      button.addEventListener('click', () => {
        state.activeRegion = button.dataset.region;
        renderDashboard();
      });
    });
  });
  renderTopicTrendAnalysis(active);
}

function renderAiInsight() {
  const container = el('ai-insight');
  if (!container) return;
  const insight = state.summary?.ai_insight;
  if (!insight || insight.status !== 'ready') {
    container.innerHTML = '<div class="chart-empty compact"><p>趨勢月份不足，暫不產生研判。</p></div>';
    return;
  }
  const evidence = (insight.evidence || []).map(item => `
    <div class="evidence-chip">
      <span>${escapeHtml(item.label)}</span>
      <strong>${escapeHtml(item.display)}</strong>
    </div>
  `).join('');
  const topicRows = (insight.topic_observations || []).map(row => `
    <li>
      <span>${escapeHtml(row.label)}</span>
      <strong>${fmt.format(row.count)} 件</strong>
      <em>${row.change_pct === null || row.change_pct === undefined ? '無前月基準' : `${row.change_pct > 0 ? '+' : ''}${row.change_pct}%`}</em>
    </li>
  `).join('');
  const limits = (insight.limitations || []).map(item => `<li>${escapeHtml(item)}</li>`).join('');
  container.innerHTML = `
    <div class="insight-head">
      <span class="severity ${escapeHtml(insight.severity || 'watch')}">AI 輔助研判</span>
      <strong>${escapeHtml(insight.title)}</strong>
    </div>
    <p>${escapeHtml(insight.summary)}</p>
    <div class="evidence-grid">${evidence}</div>
    <div class="insight-split">
      <div>
        <span class="subhead">同步下降主題</span>
        <ul class="rank-list">${topicRows}</ul>
      </div>
      <div>
        <span class="subhead">判讀限制</span>
        <ul class="limit-list">${limits}</ul>
      </div>
    </div>
  `;
}

function renderTopicTrendAnalysis(topic) {
  const container = el('topic-ai-analysis');
  if (!container) return;
  const series = trendWindow(topic?.trend || []);
  if (!topic || series.length < 3) {
    container.innerHTML = '<div class="chart-empty compact"><p>主題趨勢月份不足，暫不產生分析。</p></div>';
    return;
  }
  const latest = series[series.length - 1];
  const previous = series[series.length - 2];
  const latestCount = Number(latest.count || 0);
  const previousCount = Number(previous.count || 0);
  const average = series.reduce((sum, row) => sum + Number(row.count || 0), 0) / series.length;
  const peak = [...series].sort((a, b) => Number(b.count || 0) - Number(a.count || 0))[0];
  const low = [...series].sort((a, b) => Number(a.count || 0) - Number(b.count || 0))[0];
  const mainSegment = orderedSegments(topic.segments)[0];
  const topRegion = allTopicRegions(topic)[0];
  const delta = latestCount - previousCount;
  const scopeNote = topic.is_total_scope
    ? '此分頁採全部官方案類加總，資料範圍可與全國總案量曲線核對。'
    : topic.is_residual_scope
      ? '此分頁收納未放入前六個分析主題的官方案類，用來補足主題分類外的案件。'
      : '此分頁是民眾關注主題包，非完整分類表；不同主題間不應直接相加。';

  container.innerHTML = `
    <div class="topic-analysis-head">
      <span class="subhead">AI 案件趨勢分析</span>
      <strong>${escapeHtml(topic.label)}：${formatMonthLabel(latest.month)} ${fmt.format(latestCount)} 件</strong>
    </div>
    <div class="evidence-grid compact">
      <div class="evidence-chip">
        <span>較前月</span>
        <strong class="${deltaClass(delta)}">${escapeHtml(formatSignedCount(delta))}</strong>
      </div>
      <div class="evidence-chip">
        <span>近 12 月平均</span>
        <strong>${fmt.format(Math.round(average))} 件</strong>
      </div>
      <div class="evidence-chip">
        <span>高峰月</span>
        <strong>${escapeHtml(formatMonthLabel(peak.month))} · ${fmt.format(Number(peak.count || 0))}</strong>
      </div>
      <div class="evidence-chip">
        <span>低點月</span>
        <strong>${escapeHtml(formatMonthLabel(low.month))} · ${fmt.format(Number(low.count || 0))}</strong>
      </div>
    </div>
    <p>${escapeHtml(scopeNote)} 最新月主要案類為 ${escapeHtml(mainSegment?.label || '無資料')}，前五縣市以 ${escapeHtml(topRegion?.geography || '無資料')} 最高。此分析只根據官方發生件數提示變化，不推定犯罪原因。</p>
  `;
}

function renderDrilldownDetail() {
  const container = el('drilldown-detail');
  if (!container) return;
  const topic = findActiveTopic();
  if (!topic) {
    container.innerHTML = '<div class="chart-empty compact"><p>請先選擇一個治安主題。</p></div>';
    return;
  }
  syncDrilldownSelection(topic);
  const region = selectedRegion(topic);
  const metric = selectedMetric(topic);
  const countyMetricCount = segmentCount(region?.segments, metric?.metric);
  const nationalMetricCount = segmentCount(topic.segments, metric?.metric);
  const scopeLabel = region?.isNational ? '全國' : '縣市';
  const drillScopeNote = topic.is_total_scope
    ? `目前「${topic.label}」為全部官方案類加總；「${metric?.label || '未選案類'}」是其中一個單一案類。`
    : topic.is_residual_scope
      ? `目前「${topic.label}」為前六個分析主題之外的官方案類集合；「${metric?.label || '未選案類'}」是其中一個單一案類。`
      : `目前「${topic.label}」為主題包合計；「${metric?.label || '未選案類'}」是單一案類。兩者資料範圍不同，例如性犯罪與家庭會把妨害性自主罪、妨害風化、妨害家庭及婚姻、遺棄合併。`;
  const countyMetricRows = allTopicRegions(topic)
    .map(row => ({ geography: row.geography, count: segmentCount(row.segments, metric?.metric) }))
    .filter(row => row.count > 0)
    .sort((a, b) => b.count - a.count);
  const topCounties = countyMetricRows.slice(0, 5);
  const otherCountyCount = countyMetricRows.slice(5).reduce((sum, row) => sum + row.count, 0);
  const countyRankRows = otherCountyCount > 0
    ? [...topCounties, { geography: '其他縣市', count: otherCountyCount, isOther: true }]
    : topCounties;
  container.innerHTML = `
    <div class="metric-picker">
      <span class="subhead">案類選擇</span>
      <div class="segment-legend">${renderSegmentLegend(topic.segments || [], metric?.metric)}</div>
    </div>
    <div class="drill-path" aria-label="目前細究路徑">
      <span>${escapeHtml(topic.label)}</span>
      <b>›</b>
      <span>${escapeHtml(region?.geography || '未選縣市')}</span>
      <b>›</b>
      <span>${escapeHtml(metric?.label || '未選案類')}</span>
    </div>
    <div class="mini-stat-grid drill-stats">
      <div class="mini-stat">
        <span>${escapeHtml(scopeLabel)}主題案量</span>
        <strong>${region ? fmt.format(region.total) : '0'} 件</strong>
        <small>${region?.isNational ? '全部縣市合計' : (region ? `占本主題 ${region.share_pct}%` : '無資料')}</small>
      </div>
      <div class="mini-stat">
        <span>${escapeHtml(scopeLabel)} YoY</span>
        <strong class="${deltaClass(region?.yoy_pct)}">${region ? escapeHtml(formatPct(region.yoy_pct)) : '無資料'}</strong>
        <small>與去年同月同資料範圍比較</small>
      </div>
      <div class="mini-stat">
        <span>${escapeHtml(scopeLabel)}選定案類</span>
        <strong>${fmt.format(countyMetricCount)} 件</strong>
        <small>${metric ? escapeHtml(metric.label) : '未選案類'}</small>
      </div>
      <div class="mini-stat">
        <span>全國選定案類</span>
        <strong>${fmt.format(nationalMetricCount)} 件</strong>
        <small>官方刑事案件發生件數</small>
      </div>
      <div class="mini-stat">
        <span>${escapeHtml(scopeLabel)}案類占比</span>
        <strong>${region?.total ? ((countyMetricCount / region.total) * 100).toFixed(1) : '0.0'}%</strong>
        <small>占目前範圍本主題</small>
      </div>
    </div>
    <div class="drill-columns">
      <div>
        <span class="subhead">${region?.isNational ? '全國案類構成' : '該縣市案類構成'}</span>
        <div class="stacked-track national">${renderStackedBarSegments(region?.segments, region?.total || 0)}</div>
        <div class="segment-legend">${renderSegmentLegend(region?.segments || [], metric?.metric)}</div>
      </div>
      <div>
        <span class="subhead">此案類前五縣市與其他縣市</span>
        <ul class="rank-list">${countyRankRows.map(row => `
          <li class="${row.isOther ? 'is-other' : ''}"><span>${escapeHtml(row.geography)}</span><strong>${fmt.format(row.count)} 件</strong></li>
        `).join('')}</ul>
      </div>
    </div>
    <p class="method-note">${escapeHtml(drillScopeNote)}</p>
    <p class="method-note">目前為件數細究，尚未除以人口、戶數或日數；縣市比較應避免直接等同於風險排名。</p>
  `;
  container.querySelectorAll('[data-metric]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeMetric = button.dataset.metric;
      renderDashboard();
    });
  });
}

function renderAnnualTabs() {
  const tabs = el('annual-tabs');
  if (!tabs) return;
  const views = [
    ['kpi', '年度 KPI 與 YoY'],
    ['same', '同期間變化拆解'],
    ['full', '完整年度變化拆解'],
  ];
  tabs.innerHTML = views.map(([id, label]) => `
    <button type="button" class="sub-tab ${state.activeAnnualTab === id ? 'is-active' : ''}" data-annual-tab="${id}" role="listitem">
      ${escapeHtml(label)}
    </button>
  `).join('');
  tabs.querySelectorAll('[data-annual-tab]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeAnnualTab = button.dataset.annualTab;
      renderAnnualComparison();
    });
  });
}

function renderAnnualComparison() {
  const container = el('annual-comparison');
  if (!container) return;
  renderAnnualTabs();
  const annual = state.summary?.annual_comparison;
  if (!annual?.rows?.length) {
    container.innerHTML = '<div class="chart-empty compact"><p>年度比較資料不足。</p></div>';
    return;
  }
  const rowsDesc = [...annual.rows].sort((a, b) => Number(b.year) - Number(a.year));
  const latest = rowsDesc[0];
  const previous = rowsDesc.find(row => Number(row.year) === Number(latest.year) - 1) || rowsDesc[1] || null;
  const hasYoy = latest.yoy_pct !== null && latest.yoy_pct !== undefined;
  const yoyClass = hasYoy ? (Number(latest.yoy_pct) >= 0 ? 'up' : 'down') : '';
  const peaks = (annual.peak_months || [])
    .sort((a, b) => Number(b.year) - Number(a.year))
    .map(row => `
    <div class="peak-row">
      <div class="peak-label">
        <span>${escapeHtml(row.year)} 年高峰月：${escapeHtml(formatMonthLabel(row.peak_month))}</span>
        <strong>單月總計 ${fmt.format(row.total)} 件</strong>
        <small>搜尋範圍 ${escapeHtml(row.scope)}</small>
      </div>
      <div class="stacked-track">${renderStackedBarSegments(row.segments, Number(row.total || 0))}</div>
      <div class="segment-legend readonly">${renderSegmentLegend(row.segments, null)}</div>
      <div class="peak-check">
        <span>前 ${peakSegmentLimit} 大合計 ${fmt.format(row.top_metric_sum || 0)} 件</span>
        <span>其餘案類 ${fmt.format(row.other_count || 0)} 件</span>
        <span>檢查：${fmt.format((row.top_metric_sum || 0) + (row.other_count || 0))} / ${fmt.format(row.total || 0)} 件</span>
      </div>
    </div>
  `).join('');
  const renderChangeRows = rows => (rows || []).sort((a, b) => Number(b.year) - Number(a.year)).map(row => {
      const maxDelta = Math.max(...(row.drivers || []).map(item => Math.abs(Number(item.delta || 0))), 1);
      const drivers = (row.drivers || []).map(driver => {
        const direction = deltaClass(driver.delta);
        const width = Math.max((Math.abs(Number(driver.delta || 0)) / maxDelta) * 100, 2);
        return `
          <div class="delta-row">
            <div class="delta-label">
              <i style="background:${safeColor(driver.color)}"></i>
              <span>${escapeHtml(driver.label)}</span>
            </div>
            <div class="delta-track"><b class="${direction}" style="width:${width}%; background:${safeColor(driver.color)}"></b></div>
            <strong class="${direction}">${escapeHtml(formatSignedCount(driver.delta))}</strong>
            <small>${fmt.format(driver.previous || 0)} → ${fmt.format(driver.current || 0)}</small>
          </div>
        `;
      }).join('');
      const direction = deltaClass(row.total_delta);
      return `
        <div class="change-card">
          <div class="change-head">
            <div>
              <span>${escapeHtml(row.year)} vs ${escapeHtml(row.previous_year)}</span>
              <small>${escapeHtml(row.period_label)} · 全部官方案類差額拆解</small>
            </div>
            <strong class="${direction}">${escapeHtml(formatSignedCount(row.total_delta))}</strong>
          </div>
          <div class="delta-list">${drivers}</div>
          <div class="reconcile-line">
            <span>總計差額 ${escapeHtml(formatSignedCount(row.total_delta))}</span>
            <span>案類差額加總 ${escapeHtml(formatSignedCount(row.metric_delta_sum))}</span>
            <span>差額 ${escapeHtml(formatSignedCount(row.reconciliation_delta))}</span>
          </div>
        </div>
      `;
    }).join('');
  const samePeriodChangeRows = renderChangeRows(annual.change_drivers || []);
  const fullYearChangeRows = renderChangeRows(annual.full_year_change_drivers || []);
  const kpiPanel = `
    <div class="annual-summary">
      <div class="mini-stat">
        <span>比較範圍</span>
        <strong>${escapeHtml(annual.period_label)}</strong>
        <small>避免以未完整年度對比全年</small>
      </div>
      <div class="mini-stat">
        <span>${escapeHtml(latest.year)} 同期累計</span>
        <strong>${fmt.format(latest.total)} 件</strong>
        <small>截至 ${escapeHtml(annual.period_label)}</small>
      </div>
      <div class="mini-stat">
        <span>${previous ? `${escapeHtml(previous.year)} 同期累計` : '前一年基準'}</span>
        <strong>${previous ? fmt.format(previous.total) : '無資料'}${previous ? ' 件' : ''}</strong>
        <small>作為 YoY 對照</small>
      </div>
      <div class="mini-stat">
        <span>YoY</span>
        <strong class="${yoyClass}">${escapeHtml(formatPct(latest.yoy_pct))}</strong>
        <small>以最近年度優先呈現</small>
      </div>
    </div>
    <div class="annual-peak-section">
      <span class="subhead">每年高峰月與主要案類</span>
      <div class="peak-list">${peaks}</div>
    </div>
  `;
  const samePeriodPanel = `
    <div class="annual-change-section">
      <span class="subhead">同期間變化拆解：哪些案類推動 KPI YoY？</span>
      <div class="change-list">${samePeriodChangeRows}</div>
    </div>
  `;
  const fullYearPanel = fullYearChangeRows ? `
    <div class="annual-change-section">
      <span class="subhead">完整年度變化拆解：1-12 月總量怎麼變？</span>
      <div class="change-list">${fullYearChangeRows}</div>
    </div>
  ` : '<div class="chart-empty compact"><p>目前尚無足夠完整年度可比較。</p></div>';
  const panels = { kpi: kpiPanel, same: samePeriodPanel, full: fullYearPanel };
  container.innerHTML = `
    ${panels[state.activeAnnualTab] || kpiPanel}
    <p class="method-note">${escapeHtml(annual.note || '')}</p>
  `;
  container.querySelectorAll('[data-metric]').forEach(button => {
    button.disabled = true;
  });
}

function renderViewTabs() {
  const tabs = el('view-tabs');
  if (!tabs) return;
  const views = [
    ['year', '年度比較'],
    ['topics', '案類趨勢'],
    ['local', '縣市細究'],
    ['method', '資料範圍'],
    ['feedback', 'Feedback'],
  ];
  tabs.innerHTML = views.map(([id, label]) => `
    <button type="button" class="view-tab ${state.activeView === id ? 'is-active' : ''}" data-view="${id}">
      ${escapeHtml(label)}
    </button>
  `).join('');
  tabs.querySelectorAll('[data-view]').forEach(button => {
    button.addEventListener('click', () => {
      state.activeView = button.dataset.view;
      renderDashboard();
    });
  });

  document.querySelectorAll('[data-view-panel]').forEach(panel => {
    panel.hidden = panel.dataset.viewPanel !== state.activeView;
  });
}

function renderSourceContext() {
  const quality = state.summary?.quality || {};
  const sourceLink = safeUrl(state.summary?.source_url);
  const metricSum = Number(quality.national_metric_sum || 0);
  const totalCases = Number(state.summary?.total_cases || 0);
  const reconciliationDelta = Number(quality.total_reconciliation_delta || 0);
  const caseMetrics = caseMetricNames();
  const caseMetricList = caseMetrics.map(metric => `<span>${escapeHtml(metric)}</span>`).join('');
  el('source-context').innerHTML = `
    <dl>
      <div><dt>資料月份</dt><dd>${escapeHtml(formatMonth(state.summary.source_month))}</dd></div>
      <div><dt>資料來源</dt><dd>內政部統計查詢網資料集 ${escapeHtml(state.summary.dataset_id || '9603')}</dd></div>
      <div><dt>統計範圍</dt><dd>刑事案件發生件數；不是起訴、判決或定罪件數。</dd></div>
      <div><dt>圖表範圍</dt><dd>全國總案量曲線每一點是該月份單月總計；案類主題是分析入口，可能只含部分案類或跨主題重複。只有「全部類型」可與總案量逐月核對。</dd></div>
      <div><dt>目前不含</dt><dd>裁判書、社群輿情或未驗證爬蟲結果。</dd></div>
      <div><dt>欄位覆蓋</dt><dd>${fmt.format(quality.case_metric_count || Math.max((quality.metric_count || 1) - 1, 0))} 個官方案類欄位、${fmt.format(quality.raw_rows || 0)} 筆地區列。</dd></div>
      <div class="source-wide"><dt>案件類型</dt><dd><p>目前資料庫共有 ${fmt.format(caseMetrics.length || quality.case_metric_count || 0)} 個官方非總計案類：</p><div class="metric-chip-list">${caseMetricList}</div></dd></div>
      <div><dt>案類色彩</dt><dd>${fmt.format(state.summary.metric_styles?.count || 0)} 個官方欄位已建立固定顏色對照。</dd></div>
      <div><dt>加總檢查</dt><dd>全部案類加總 ${fmt.format(metricSum)} 件 / 總計 ${fmt.format(totalCases)} 件，差額 ${escapeHtml(formatSignedCount(reconciliationDelta))}。</dd></div>
    </dl>
    ${sourceLink ? `<a class="text-link" href="${escapeHtml(sourceLink)}" target="_blank" rel="noreferrer">資料來源</a>` : ''}
  `;
}

function renderDashboard() {
  const summary = state.summary;
  if (!summary) return;
  el('header-record-count').textContent = `${formatMonth(summary.source_month)} · ${fmt.format(summary.total_cases)} 件`;
  el('overview-summary').textContent = summary.summary?.text || '官方統計資料已載入。';
  el('total-context').textContent = `全國總案量 ${fmt.format(summary.total_cases)} 件`;
  renderTopicDetail();
  renderAiInsight();
  renderDrilldownDetail();
  renderAnnualComparison();
  renderLineChart('monthly-trend', summary.monthly_counts || []);
  renderSourceContext();
  renderViewTabs();
}

async function loadMonths() {
  const data = await getJson('/api/months');
  const items = data.items?.length ? data.items : [{ source_month: '202604', count: 0 }];
  el('month').innerHTML = items.map(item =>
    `<option value="${escapeHtml(item.source_month)}">${escapeHtml(formatMonth(item.source_month))}</option>`
  ).join('');
}

async function loadSummary() {
  state.summary = await getJson(`/api/official-summary?month=${encodeURIComponent(currentMonth())}`);
  renderDashboard();
}

function bindEvents() {
  el('month').addEventListener('change', () => {
    loadSummary().catch(handleError);
  });
}

function handleError(error) {
  console.error(error);
  showToast(`載入失敗：${error.message || error}`);
}

async function init() {
  try {
    await loadMonths();
    bindEvents();
    await loadSummary();
  } catch (error) {
    handleError(error);
  }
}

init();
