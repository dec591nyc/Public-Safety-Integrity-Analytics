const fmt = new Intl.NumberFormat('zh-TW');

const categoryLabels = {
  fraud: '詐欺／詐騙',
  money_laundering: '洗錢',
  sexual_offense: '妨害性自主／性侵',
  injury: '傷害／重傷',
  traffic_injury: '交通傷害',
  public_integrity: '貪污／瀆職／圖利／賄賂',
  election_law: '選罷法／賄選'
};

const domainLabels = {
  civil: '民事',
  criminal: '刑事',
  administrative: '行政',
  constitutional: '憲法',
  disciplinary: '懲戒',
  other: '其他',
  unknown: '未分類'
};

const chartColors = ['#1d4ed8', '#0891b2', '#15803d', '#b45309', '#be123c', '#6d28d9', '#475569'];
const categoryShortLabels = {
  fraud: '詐欺', money_laundering: '洗錢', sexual_offense: '性自主', injury: '傷害／重傷',
  traffic_injury: '交通傷害', public_integrity: '廉政／貪污', election_law: '選罷法'
};
const state = { summary: null, opinion: null, offset: 0, pageSize: 25, loading: false };

function el(id) { return document.getElementById(id); }
function currentMonth() { return el('month').value || '202604'; }
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}
function safeUrl(value) {
  try {
    const url = new URL(value);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch { return ''; }
}
function formatMonth(value) {
  return /^\d{6}$/.test(value) ? `${value.slice(0, 4)} 年 ${Number(value.slice(4))} 月` : value;
}
function formatMonthLabel(value) {
  if (/^\d{6}$/.test(value)) return `${value.slice(0, 4)}/${value.slice(4, 6)}`;
  return value;
}
function formatChange(value) {
  if (value === null || value === undefined) return '無前月基準';
  const sign = value > 0 ? '+' : '';
  return `較前月 ${sign}${value}%`;
}
function showToast(message) {
  const toast = el('toast');
  toast.textContent = message;
  toast.classList.add('is-visible');
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => toast.classList.remove('is-visible'), 3200);
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

function setLoading(button, loading, label) {
  if (!button) return;
  button.disabled = loading;
  button.dataset.label ||= button.textContent;
  button.textContent = loading ? label : button.dataset.label;
}

function switchRoute(route) {
  document.querySelectorAll('.tab').forEach(tab => {
    const active = tab.dataset.route === route;
    tab.classList.toggle('is-active', active);
    active ? tab.setAttribute('aria-current', 'page') : tab.removeAttribute('aria-current');
  });
  document.querySelectorAll('.page').forEach(page => {
    page.classList.toggle('is-active', page.dataset.page === route);
  });
  history.replaceState(null, '', `#${route}`);
  if (route === 'opinion') loadOpinion().catch(handleError);
  if (route === 'truth') renderCrossObservation();
  if (route === 'database') loadCases().catch(handleError);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function categoryCount(category) {
  return state.summary?.category_counts?.find(item => item.category === category)?.count || 0;
}

function categoryItem(category) {
  return state.summary?.category_counts?.find(item => item.category === category) || {};
}

async function loadMonths() {
  const data = await getJson('/api/months');
  const items = data.items?.length ? data.items : [{ source_month: '202604', count: 0 }];
  const options = items.map(item =>
    `<option value="${escapeHtml(item.source_month)}">${escapeHtml(formatMonth(item.source_month))} · ${fmt.format(item.count)} 件</option>`
  ).join('');
  el('month').innerHTML = options;
  el('opinion-month').innerHTML = options;
}

function renderMetrics() {
  const items = [
    ['刑事案件總量', state.summary.total_cases, formatChange(state.summary.total_change_pct), 'neutral'],
    ['詐欺背信', categoryCount('fraud'), formatChange(categoryItem('fraud').change_pct), 'blue'],
    ['傷害', categoryCount('injury'), formatChange(categoryItem('injury').change_pct), 'amber'],
    ['妨害性自主罪', categoryCount('sexual_offense'), formatChange(categoryItem('sexual_offense').change_pct), 'red']
  ];
  el('metrics').innerHTML = items.map(([label, value, note, tone]) => `
    <article class="metric metric-${tone}">
      <span>${escapeHtml(label)}</span>
      <strong>${fmt.format(value)}</strong>
      <small>${escapeHtml(note)}</small>
    </article>`).join('');
}

function renderLineChart(rows) {
  const container = el('monthly-trend');
  if (!rows.length) {
    container.innerHTML = '<div class="chart-empty"><strong>沒有月份資料</strong><p>下載並驗證官方統計後才會顯示每月趨勢。</p></div>';
    return;
  }
  const width = 900;
  const height = 280;
  const pad = { top: 18, right: 24, bottom: 36, left: 62 };
  
  const counts = rows.map(row => row.count);
  const minCount = Math.min(...counts);
  const maxCount = Math.max(...counts);
  
  // Calculate dynamic bounds to avoid flat horizontal line
  let minVal, maxVal;
  if (maxCount === minCount) {
    minVal = Math.max(0, Math.floor(minCount * 0.9));
    maxVal = Math.ceil(maxCount * 1.1);
  } else {
    const diff = maxCount - minCount;
    minVal = Math.max(0, Math.floor(minCount - diff * 0.15));
    maxVal = Math.ceil(maxCount + diff * 0.15);
  }
  if (maxVal === minVal) maxVal = minVal + 1; // avoid divide by zero
  
  const x = index => rows.length === 1
    ? (pad.left + width - pad.right) / 2
    : pad.left + (index * (width - pad.left - pad.right)) / (rows.length - 1);
  const y = value => height - pad.bottom - ((value - minVal) / (maxVal - minVal)) * (height - pad.top - pad.bottom);
  const points = rows.map((row, index) => `${x(index)},${y(row.count)}`).join(' ');
  
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const grids = yTicks.map(ratio => {
    const val = minVal + (maxVal - minVal) * ratio;
    const yy = y(val);
    return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" class="grid-line" />
      <text x="${pad.left - 10}" y="${yy + 4}" text-anchor="end">${fmt.format(Math.round(val))}</text>`;
  }).join('');
  
  const labelStep = Math.max(Math.ceil(rows.length / 6), 1);
  const xLabels = rows.map((row, index) => index % labelStep === 0 || index === rows.length - 1
    ? `<text x="${x(index)}" y="${height - 10}" text-anchor="middle">${escapeHtml(formatMonthLabel(row.month))}</text>` : '').join('');
  const dots = rows.map((row, index) => `<circle cx="${x(index)}" cy="${y(row.count)}" r="4" tabindex="0">
    <title>${escapeHtml(formatMonth(row.month))}：${fmt.format(row.count)} 件</title></circle>`).join('');
  
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true" preserveAspectRatio="none">
    ${grids}${xLabels}
    <polyline points="${points}" class="trend-line" />
    ${dots}
  </svg>`;
  
  el('monthly-table').innerHTML = `<div class="table-wrap"><table><thead><tr><th>月份</th><th class="numeric">件數</th></tr></thead><tbody>${rows.map(row =>
    `<tr><td>${escapeHtml(formatMonth(row.month))}</td><td class="numeric">${fmt.format(row.count)}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderCategoryBars(rows) {
  const max = Math.max(...rows.map(row => row.count), 1);
  el('category-bars').innerHTML = rows.map((row, index) => `
    <div class="bar-row">
      <div class="bar-label">
        <span title="${escapeHtml(row.label)}">${escapeHtml(row.label)}</span>
        <strong>${fmt.format(row.count)}</strong>
      </div>
      <div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${Math.max((row.count / max) * 100, 1)}%;background:${chartColors[index % chartColors.length]}"></div></div>
      <small>${escapeHtml(formatChange(row.change_pct))}</small>
    </div>`).join('');
}

function renderRegionBars(rows) {
  const max = Math.max(...rows.map(row => row.count), 1);
  el('region-list').innerHTML = rows.slice(0, 10).map(row => `
    <div class="bar-row">
      <div class="bar-label"><span>${escapeHtml(row.geography)}</span><strong>${fmt.format(row.count)}</strong></div>
      <div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${Math.max((row.count / max) * 100, 1)}%"></div></div>
    </div>`).join('');
}

function renderQualityTable(quality) {
  const checks = [
    ['有效資料列', `${fmt.format(quality.selected_rows)} / 原始 ${fmt.format(quality.raw_rows)}`, quality.selected_rows > 0],
    ['排除重複區間列', fmt.format(quality.duplicate_rows_dropped), quality.duplicate_rows_dropped >= 0],
    ['分項吻合全國總計', `${fmt.format(quality.matched_metric_totals)} / ${fmt.format(quality.metric_count)}`, quality.matched_metric_totals === quality.metric_count],
    ['非法儲存格', fmt.format(quality.invalid_cells), quality.invalid_cells === 0],
    ['來源「-」轉換為 0', fmt.format(quality.dash_zero_cells), true]
  ];
  el('quality-table').innerHTML = checks.map(([label, value, passed]) => `<tr>
    <td>${escapeHtml(label)}</td><td class="numeric">${escapeHtml(value)}</td>
    <td><span class="state-chip ${passed ? 'state-ready' : 'state-pending'}">${passed ? '通過' : '待檢查'}</span></td>
  </tr>`).join('');
}

async function loadSummary() {
  state.summary = await getJson(`/api/official-summary?month=${encodeURIComponent(currentMonth())}`);
  el('header-record-count').textContent = `${formatMonth(state.summary.source_month)} · ${fmt.format(state.summary.total_cases)} 件`;
  el('overview-summary').textContent = state.summary.summary.text;
  const sourceLink = el('official-source-link');
  sourceLink.href = safeUrl(state.summary.source_url) || '#';
  renderMetrics();
  renderLineChart(state.summary.monthly_counts || []);
  renderCategoryBars(state.summary.category_counts || []);
  renderRegionBars(state.summary.region_counts || []);
  renderQualityTable(state.summary.quality || {});
  renderCrossObservation();
}

async function loadOpinion() {
  const selectedMonth = el('opinion-month').value || currentMonth();
  state.opinion = await getJson(`/api/opinion?month=${encodeURIComponent(selectedMonth)}`);
  const ready = state.opinion.status === 'ready';
  el('opinion-status-badge').textContent = ready ? '資料已更新' : '爬蟲尚未啟動';
  el('opinion-status-badge').classList.toggle('is-pending', !ready);
  el('opinion-metrics').innerHTML = [
    ['本月文章', 0, '尚未收集'], ['已接來源', 0, `共 ${state.opinion.sources.length} 個規劃來源`],
    ['已分類文章', 0, '等待類別標記'], ['可比月份', 0, '等待輿論資料']
  ].map(([label, value, note]) => `<article class="metric"><span>${label}</span><strong>${fmt.format(value)}</strong><small>${escapeHtml(note)}</small></article>`).join('');
  el('opinion-trend').innerHTML = `<strong>尚無可繪製的討論資料</strong><p>${escapeHtml(state.opinion.message)}</p>`;
  el('opinion-sources').innerHTML = state.opinion.sources.map(source => `<article class="source-card">
    <div><h4>${escapeHtml(source.name)}</h4><p>完成來源條款檢查後接入</p></div><span class="source-status">待設定</span>
  </article>`).join('');
  el('opinion-summaries').innerHTML = `<div class="empty-state"><strong>${escapeHtml(formatMonth(selectedMonth))} 尚無輿論摘要</strong>
    <p>n8n 排程接入後，這裡會依議題顯示討論焦點、來源連結、時間分布與摘要方法。</p></div>`;
}

function renderCrossObservation() {
  if (!state.summary) return;
  const opinionReady = state.opinion?.status === 'ready';
  el('cross-metrics').innerHTML = [
    ['官方案件統計', state.summary.total_cases, '已接入'],
    ['輿論文章', 0, opinionReady ? '已接入' : '尚未接入'],
    ['可比月份', 0, '等待同月份輿論資料'],
    ['官方來源', 1, `資料集 ${state.summary.dataset_id}`]
  ].map(([label, value, note]) => `<article class="metric"><span>${label}</span><strong>${fmt.format(value)}</strong><small>${escapeHtml(note)}</small></article>`).join('');

  const topics = [
    ['fraud', '等待同月份詐欺相關討論量'],
    ['injury', '等待同月份傷害相關討論量'],
    ['sexual_offense', '等待同月份妨害性自主討論量'],
    ['public_integrity', '等待同月份廉政議題討論量'],
    ['election_law', '案件量低，需同時顯示絕對數']
  ];
  el('cross-table').innerHTML = topics.map(([key, action]) => `<tr>
    <td><strong>${escapeHtml(categoryLabels[key])}</strong></td>
    <td class="numeric">${fmt.format(categoryCount(key))}</td>
    <td class="numeric">—</td>
    <td><span class="state-chip state-pending">不可比較</span></td>
    <td>${escapeHtml(action)}</td>
  </tr>`).join('');
  el('cross-summary').innerHTML = `<strong>目前只有官方案件統計，尚不能計算輿論關注差距。</strong>
    <p>${escapeHtml(state.summary.summary.text)}</p>`;
}

function activeCaseParams() {
  const params = new URLSearchParams({ month: currentMonth(), limit: String(state.pageSize), offset: String(state.offset) });
  const fields = {
    category: el('category-filter').value,
    domain: el('domain-filter').value,
    q: el('search').value.trim() || el('query-search').value.trim()
  };
  Object.entries(fields).forEach(([key, value]) => value && params.set(key, value));
  return params;
}

function renderCases(data) {
  const page = Math.floor(state.offset / state.pageSize) + 1;
  const pages = Math.max(Math.ceil(data.total / state.pageSize), 1);
  el('case-count').textContent = `共 ${fmt.format(data.total)} 筆符合條件；目前顯示第 ${page} 頁的 ${fmt.format(data.items.length)} 筆。`;
  el('page-status').textContent = `第 ${page} / ${pages} 頁`;
  el('previous-page').disabled = state.offset === 0;
  el('next-page').disabled = state.offset + state.pageSize >= data.total;
  el('search-warnings').innerHTML = (data.warnings || []).map(message => `<div class="warning-box">${escapeHtml(message)}</div>`).join('');
  el('cases').innerHTML = data.items.map(item => {
    const flags = Object.entries(item.category_flags || {}).filter(([, value]) => value)
      .map(([key]) => `<span class="tag">${escapeHtml(categoryLabels[key] || key)}</span>`).join('');
    const keywords = (item.matched_keywords || []).slice(0, 5)
      .map(keyword => `<span class="keyword">${escapeHtml(keyword)}</span>`).join('');
    const pdf = safeUrl(item.jpdf);
    const evidence = (item.summary?.evidence_snippets || []).map(snippet => `<li>${escapeHtml(snippet)}</li>`).join('');
    return `<article class="case-card">
      <div class="case-record">
        <div class="case-topline">
          <div>
            <h3>${escapeHtml(item.jtitle || '未標示案由')}</h3>
            <p class="case-meta">${escapeHtml(item.jdate || '日期未載')} · ${escapeHtml(item.court_folder || '法院未載')} · ${escapeHtml(domainLabels[item.case_domain] || item.case_domain || '')}</p>
          </div>
          <span class="jid">${escapeHtml(item.jid)}</span>
        </div>
        <div class="record-summary">
          <div class="summary-title"><strong>規則式摘要</strong><span>低可信度 · 需人工複核</span></div>
          <p>${escapeHtml(item.summary?.text || '沒有可用摘要。')}</p>
        </div>
        <div class="tags">${flags}${keywords}</div>
        ${evidence ? `<details class="evidence"><summary>查看摘要證據片段</summary><ul>${evidence}</ul></details>` : ''}
      </div>
      <div class="case-actions">
        ${pdf ? `<a href="${escapeHtml(pdf)}" target="_blank" rel="noreferrer">開啟 PDF 來源</a>` : '<span>無 PDF 連結</span>'}
      </div>
    </article>`;
  }).join('') || '<div class="empty-state"><strong>沒有符合條件的裁判</strong><p>請放寬月份、案由、法院或當事人條件後再試。</p></div>';
}

async function loadCases() {
  if (state.loading) return;
  state.loading = true;
  el('cases').setAttribute('aria-busy', 'true');
  try {
    const data = await getJson(`/api/judgments?${activeCaseParams().toString()}`);
    renderCases(data);
  } finally {
    state.loading = false;
    el('cases').setAttribute('aria-busy', 'false');
  }
}

function clearFilters() {
  ['query-search', 'search'].forEach(id => { el(id).value = ''; });
  el('category-filter').value = '';
  el('domain-filter').value = '';
  state.offset = 0;
  loadCases().catch(handleError);
}

function handleError(error) {
  console.error(error);
  showToast(`資料載入失敗：${error.message}`);
}

let searchTimer;
function scheduleCaseLoad() {
  clearTimeout(searchTimer);
  state.offset = 0;
  searchTimer = setTimeout(() => loadCases().catch(handleError), 280);
}

function bindEvents() {
  document.querySelectorAll('.tab').forEach(tab => tab.addEventListener('click', () => switchRoute(tab.dataset.route)));
  el('global-query').addEventListener('submit', event => {
    event.preventDefault();
    el('search').value = el('query-search').value.trim();
    state.offset = 0;
    switchRoute('database');
  });
  el('month').addEventListener('change', async () => {
    el('opinion-month').value = currentMonth();
    state.offset = 0;
    try { await loadSummary(); if (location.hash === '#database') await loadCases(); } catch (error) { handleError(error); }
  });
  el('opinion-filters').addEventListener('submit', event => { event.preventDefault(); loadOpinion().catch(handleError); });
  ['category-filter', 'domain-filter'].forEach(id => el(id).addEventListener('change', scheduleCaseLoad));
  el('search').addEventListener('input', () => {
    el('query-search').value = el('search').value;
    scheduleCaseLoad();
  });
  el('clear-filters').addEventListener('click', clearFilters);
  el('previous-page').addEventListener('click', () => { state.offset = Math.max(0, state.offset - state.pageSize); loadCases().catch(handleError); });
  el('next-page').addEventListener('click', () => { state.offset += state.pageSize; loadCases().catch(handleError); });
}

async function init() {
  await loadMonths();
  bindEvents();
  await loadSummary();
  await loadOpinion();
  const rawRoute = location.hash.replace('#', '') || 'overview';
  const route = rawRoute === 'cross-observation' ? 'truth' : rawRoute;
  switchRoute(['overview', 'opinion', 'truth', 'database'].includes(route) ? route : 'overview');
}

init().catch(handleError);
