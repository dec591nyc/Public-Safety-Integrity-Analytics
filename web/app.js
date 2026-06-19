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
function formatDateLabel(value) {
  if (/^\d{8}$/.test(value)) return `${value.slice(4, 6)}/${value.slice(6, 8)}`;
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return value.slice(5).replace('-', '/');
  return value;
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
  if (route === 'cross-observation') renderCrossObservation();
  if (route === 'database') loadCases().catch(handleError);
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function categoryCount(category) {
  return state.summary?.category_counts?.find(item => item.category === category)?.count || 0;
}

async function loadMonths() {
  const data = await getJson('/api/months');
  const items = data.items?.length ? data.items : [{ source_month: '202604', count: 0 }];
  const options = items.map(item =>
    `<option value="${escapeHtml(item.source_month)}">${escapeHtml(formatMonth(item.source_month))} · ${fmt.format(item.count)} 筆</option>`
  ).join('');
  el('month').innerHTML = options;
  el('opinion-month').innerHTML = options;
}

function renderMetrics() {
  const items = [
    ['裁判總量', state.summary.total_judgments, formatMonth(state.summary.source_month), 'neutral'],
    ['詐欺候選', categoryCount('fraud'), '全文關鍵字候選', 'blue'],
    ['傷害／重傷候選', categoryCount('injury'), '不與交通傷害重複加總', 'amber'],
    ['廉政訊號', categoryCount('public_integrity') + categoryCount('election_law'), '需逐案人工複核', 'red']
  ];
  el('metrics').innerHTML = items.map(([label, value, note, tone]) => `
    <article class="metric metric-${tone}">
      <span>${escapeHtml(label)}</span>
      <strong>${fmt.format(value)}</strong>
      <small>${escapeHtml(note)}</small>
    </article>`).join('');
}

function renderLineChart(rows) {
  const container = el('daily-trend');
  if (!rows.length) {
    container.innerHTML = '<div class="chart-empty"><strong>沒有趨勢資料</strong><p>所選月份沒有可用日期。</p></div>';
    return;
  }
  const width = 900;
  const height = 280;
  const pad = { top: 18, right: 24, bottom: 36, left: 58 };
  const max = Math.max(...rows.map(row => row.count), 1);
  const x = index => pad.left + (index * (width - pad.left - pad.right)) / Math.max(rows.length - 1, 1);
  const y = value => height - pad.bottom - (value / max) * (height - pad.top - pad.bottom);
  const points = rows.map((row, index) => `${x(index)},${y(row.count)}`).join(' ');
  const yTicks = [0, 0.25, 0.5, 0.75, 1];
  const grids = yTicks.map(ratio => {
    const yy = y(max * ratio);
    return `<line x1="${pad.left}" y1="${yy}" x2="${width - pad.right}" y2="${yy}" class="grid-line" />
      <text x="${pad.left - 10}" y="${yy + 4}" text-anchor="end">${fmt.format(Math.round(max * ratio))}</text>`;
  }).join('');
  const labelStep = Math.max(Math.ceil(rows.length / 6), 1);
  const xLabels = rows.map((row, index) => index % labelStep === 0 || index === rows.length - 1
    ? `<text x="${x(index)}" y="${height - 10}" text-anchor="middle">${escapeHtml(formatDateLabel(row.date))}</text>` : '').join('');
  const dots = rows.map((row, index) => `<circle cx="${x(index)}" cy="${y(row.count)}" r="4" tabindex="0">
    <title>${escapeHtml(row.date)}：${fmt.format(row.count)} 筆</title></circle>`).join('');
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" aria-hidden="true" preserveAspectRatio="none">
    ${grids}${xLabels}
    <polyline points="${points}" class="trend-line" />
    ${dots}
  </svg>`;
  el('daily-table').innerHTML = `<div class="table-wrap"><table><thead><tr><th>日期</th><th class="numeric">件數</th></tr></thead><tbody>${rows.map(row =>
    `<tr><td>${escapeHtml(row.date)}</td><td class="numeric">${fmt.format(row.count)}</td></tr>`).join('')}</tbody></table></div>`;
}

function renderDonut(rows) {
  const total = rows.reduce((sum, row) => sum + row.count, 0) || 1;
  const radius = 72;
  const circumference = 2 * Math.PI * radius;
  let offset = 0;
  const circles = rows.map((row, index) => {
    const length = (row.count / total) * circumference;
    const circle = `<circle cx="100" cy="100" r="${radius}" fill="none" stroke="${chartColors[index % chartColors.length]}" stroke-width="28" stroke-dasharray="${length} ${circumference - length}" stroke-dashoffset="${-offset}" />`;
    offset += length;
    return circle;
  }).join('');
  el('category-donut').innerHTML = `<svg viewBox="0 0 200 200" aria-hidden="true">
    <circle cx="100" cy="100" r="${radius}" fill="none" stroke="#e2e8f0" stroke-width="28" />
    <g transform="rotate(-90 100 100)">${circles}</g>
    <text x="100" y="94" text-anchor="middle" class="donut-value">${fmt.format(total)}</text>
    <text x="100" y="118" text-anchor="middle" class="donut-label">候選標記</text>
  </svg>`;
  el('category-legend').innerHTML = rows.map((row, index) => `
    <div class="legend-row">
      <span class="legend-swatch" style="background:${chartColors[index % chartColors.length]}"></span>
      <span title="${escapeHtml(row.label)}">${escapeHtml(categoryShortLabels[row.category] || row.label)}</span>
      <strong>${fmt.format(row.count)}</strong>
    </div>`).join('');
}

function renderCourtBars(rows) {
  const max = Math.max(...rows.map(row => row.count), 1);
  el('court-list').innerHTML = rows.map(row => `
    <div class="bar-row">
      <div class="bar-label"><span title="${escapeHtml(row.court_folder)}">${escapeHtml(row.court_folder)}</span><strong>${fmt.format(row.count)}</strong></div>
      <div class="bar-track" aria-hidden="true"><div class="bar-fill" style="width:${Math.max((row.count / max) * 100, 1)}%"></div></div>
    </div>`).join('');
}

function renderTitleTable(rows) {
  el('title-table').innerHTML = rows.map((row, index) => `<tr>
    <td class="rank-cell">${index + 1}</td><td>${escapeHtml(row.jtitle || '未標示案由')}</td><td class="numeric">${fmt.format(row.count)}</td>
  </tr>`).join('');
}

async function loadSummary() {
  state.summary = await getJson(`/api/summary?month=${encodeURIComponent(currentMonth())}`);
  el('header-record-count').textContent = `${formatMonth(state.summary.source_month)} · ${fmt.format(state.summary.total_judgments)} 筆`;
  el('overview-summary').textContent = state.summary.summary.text;
  renderMetrics();
  renderLineChart(state.summary.daily_counts || []);
  renderDonut(state.summary.category_counts || []);
  renderCourtBars(state.summary.top_courts || []);
  renderTitleTable(state.summary.top_titles || []);
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
    ['已連結裁判', 0, '等待 JID 比對'], ['摘要完成', 0, '等待資料輸入']
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
    ['裁判索引', state.summary.total_judgments, '已接入'],
    ['輿論文章', 0, opinionReady ? '已接入' : '尚未接入'],
    ['已抽取事實', 0, '等待第二張表'],
    ['人工複核', 0, '流程待建立']
  ].map(([label, value, note]) => `<article class="metric"><span>${label}</span><strong>${fmt.format(value)}</strong><small>${escapeHtml(note)}</small></article>`).join('');

  const topics = [
    ['fraud', '先抽取金額、被害人數與帳戶角色'],
    ['traffic_injury', '比較判賠金額與過失比例'],
    ['sexual_offense', '先去識別化，再進行逐案審閱'],
    ['public_integrity', '比對公職身分與裁判證據鏈'],
    ['election_law', '樣本少，採逐案人工複核']
  ];
  el('cross-table').innerHTML = topics.map(([key, action]) => `<tr>
    <td><strong>${escapeHtml(categoryLabels[key])}</strong></td>
    <td class="numeric">${fmt.format(categoryCount(key))}</td>
    <td><span class="state-chip state-pending">待接入</span></td>
    <td><span class="state-chip state-pending">未開始</span></td>
    <td>${escapeHtml(action)}</td>
  </tr>`).join('');
  el('cross-summary').innerHTML = `<strong>目前只能確認裁判候選量，不能判斷輿論是否與判決結果一致。</strong>
    <p>${escapeHtml(state.summary.summary.text)}</p>
    <p>需完成當事人、主文、法條、金額與結果抽取，再接入每月輿論資料，才能形成可審閱的交叉訊號。</p>`;
}

function activeCaseParams() {
  const params = new URLSearchParams({ month: currentMonth(), limit: String(state.pageSize), offset: String(state.offset) });
  const fields = {
    category: el('category-filter').value,
    domain: el('domain-filter').value,
    q: el('search').value.trim(),
    title: el('query-title-input').value.trim(),
    court: el('query-court').value.trim(),
    plaintiff: el('query-plaintiff').value.trim(),
    defendant: el('query-defendant').value.trim()
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
  ['query-title-input', 'query-court', 'query-plaintiff', 'query-defendant', 'search'].forEach(id => { el(id).value = ''; });
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
  el('search').addEventListener('input', scheduleCaseLoad);
  el('clear-filters').addEventListener('click', clearFilters);
  el('previous-page').addEventListener('click', () => { state.offset = Math.max(0, state.offset - state.pageSize); loadCases().catch(handleError); });
  el('next-page').addEventListener('click', () => { state.offset += state.pageSize; loadCases().catch(handleError); });
}

async function init() {
  await loadMonths();
  bindEvents();
  await loadSummary();
  await loadOpinion();
  const route = location.hash.replace('#', '') || 'overview';
  switchRoute(['overview', 'opinion', 'cross-observation', 'database'].includes(route) ? route : 'overview');
}

init().catch(handleError);
