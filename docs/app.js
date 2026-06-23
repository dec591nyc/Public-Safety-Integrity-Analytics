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
  const isStaticDemo = window.location.hostname.endsWith('github.io') || 
                       window.location.hostname.endsWith('vercel.app') || 
                       window.location.protocol === 'file:' || 
                       window.location.port === '5500' || // Common live servers
                      !window.location.port; // General static page view

  let fetchUrl = url;
  if (isStaticDemo) {
    if (url === '/api/months') {
      fetchUrl = 'static_api/months.json';
    } else if (url.startsWith('/api/official-summary')) {
      const parts = url.split('?');
      const month = parts[1] ? (new URLSearchParams(parts[1]).get('month') || '202604') : '202604';
      fetchUrl = `static_api/official-summary_${month}.json`;
    } else if (url.startsWith('/api/opinion')) {
      const parts = url.split('?');
      const month = parts[1] ? (new URLSearchParams(parts[1]).get('month') || '202604') : '202604';
      fetchUrl = `static_api/opinion_${month}.json`;
    } else if (url.startsWith('/api/judgments/')) {
      const jid = url.split('/api/judgments/')[1];
      const cleanJid = encodeURIComponent(jid).replace(/%/g, '_');
      fetchUrl = `static_api/judgments_detail_${cleanJid}.json`;
    } else if (url.startsWith('/api/judgments')) {
      const parts = url.split('?');
      const month = parts[1] ? (new URLSearchParams(parts[1]).get('month') || '202604') : '202604';
      fetchUrl = `static_api/judgments_${month}.json`;
    }
  }

  try {
    const response = await fetch(fetchUrl);
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    const data = await response.json();

    // In-memory filtering logic for judgments list if we are in static mode
    if (isStaticDemo && url.startsWith('/api/judgments') && !url.startsWith('/api/judgments/')) {
      const parts = url.split('?');
      const searchParams = new URLSearchParams(parts[1] || '');
      const category = searchParams.get('category') || '';
      const domain = searchParams.get('domain') || '';
      const q = (searchParams.get('q') || '').toLowerCase();
      const limit = parseInt(searchParams.get('limit') || '25', 10);
      const offset = parseInt(searchParams.get('offset') || '0', 10);
      
      let items = data.items || [];
      if (category) {
        items = items.filter(item => item.category_flags && item.category_flags[category] === 1);
      }
      if (domain) {
        items = items.filter(item => item.case_domain === domain);
      }
      if (q) {
        items = items.filter(item => 
          (item.jid && item.jid.toLowerCase().includes(q)) ||
          (item.jtitle && item.jtitle.toLowerCase().includes(q)) ||
          (item.court_folder && item.court_folder.toLowerCase().includes(q)) ||
          (item.excerpt && item.excerpt.toLowerCase().includes(q)) ||
          (item.matched_keywords && item.matched_keywords.some(kw => kw.toLowerCase().includes(q)))
        );
      }
      
      const total = items.length;
      const slicedItems = items.slice(offset, offset + limit);
      
      return {
        total: total,
        limit: limit,
        offset: offset,
        items: slicedItems,
        warnings: data.warnings || [],
        search_capabilities: {
          title: "static_in_memory",
          court: "static_in_memory",
          plaintiff: "static_in_memory",
          defendant: "static_in_memory"
        }
      };
    }

    return data;
  } catch (error) {
    // If the call failed and we were not using static fallback, try static fallback as last resort
    if (!isStaticDemo && fetchUrl === url) {
      console.warn("API request failed, trying static fallback...", error);
      let fallbackUrl = url;
      if (url === '/api/months') {
        fallbackUrl = 'static_api/months.json';
      } else if (url.startsWith('/api/official-summary')) {
        const parts = url.split('?');
        const month = parts[1] ? (new URLSearchParams(parts[1]).get('month') || '202604') : '202604';
        fallbackUrl = `static_api/official-summary_${month}.json`;
      } else if (url.startsWith('/api/opinion')) {
        const parts = url.split('?');
        const month = parts[1] ? (new URLSearchParams(parts[1]).get('month') || '202604') : '202604';
        fallbackUrl = `static_api/opinion_${month}.json`;
      } else if (url.startsWith('/api/judgments/')) {
        const jid = url.split('/api/judgments/')[1];
        const cleanJid = encodeURIComponent(jid).replace(/%/g, '_');
        fallbackUrl = `static_api/judgments_detail_${cleanJid}.json`;
      } else if (url.startsWith('/api/judgments')) {
        const parts = url.split('?');
        const month = parts[1] ? (new URLSearchParams(parts[1]).get('month') || '202604') : '202604';
        fallbackUrl = `static_api/judgments_${month}.json`;
      }
      
      const response = await fetch(fallbackUrl);
      if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
      return response.json();
    }
    throw error;
  }
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
  const fs = state.summary.flags_summary || { cyber: 0, weapon: 0, domestic: 0, organized_fraud: 0 };
  const items = [
    ['加權治安指數', state.summary.safety_index || 0, '嚴重度乘以件數計算之治安安全指標', 'red'],
    ['刑事案件總量', state.summary.total_cases, formatChange(state.summary.total_change_pct), 'neutral'],
    ['特徵：網路犯罪', fs.cyber, '手法涉及網路、電腦之案件量', 'blue'],
    ['特徵：暴力槍枝', fs.weapon, '涉及槍枝、暴力手法之案件量', 'amber'],
    ['特徵：家庭暴力', fs.domestic, '標記為家暴、家庭衝突之案件量', 'purple'],
    ['特徵：詐欺集團', fs.organized_fraud, '涉及詐欺集團、組織性詐騙之案件量', 'red']
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

function renderIccsClassification(iccs) {
  const container = el('iccs-container');
  if (!container) return;
  if (!iccs || !iccs.length) {
    container.innerHTML = '<div class="chart-empty"><p>暫無聯合國 ICCS 分類資料</p></div>';
    return;
  }
  
  const maxVal = Math.max(...iccs.map(item => item.count), 1);
  
  container.innerHTML = iccs.map((item, index) => {
    const isExpanded = state.expandedIccs === item.code;
    const childrenHtml = isExpanded ? `
      <div class="iccs-children">
        <table>
          <thead>
            <tr>
              <th>本地法規案類 (Level 2)</th>
              <th class="numeric">件數</th>
              <th class="numeric">嚴重度權重</th>
              <th class="numeric">加權分數</th>
            </tr>
          </thead>
          <tbody>
            ${item.children.map(child => `
              <tr>
                <td>${escapeHtml(child.metric)}</td>
                <td class="numeric">${fmt.format(child.count)}</td>
                <td class="numeric">${child.severity_score}</td>
                <td class="numeric">${fmt.format(child.weighted_score)}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    ` : '';
    
    return `
      <div class="iccs-row-group">
        <div class="iccs-main-row" onclick="toggleIccs('${item.code}')" role="button" aria-expanded="${isExpanded}">
          <div class="iccs-header-info">
            <span class="iccs-code-badge">Div ${escapeHtml(item.code)}</span>
            <span class="iccs-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span>
            <span class="iccs-count-badge">${fmt.format(item.count)} 件 / 權重分 ${fmt.format(item.weighted_score)}</span>
          </div>
          <div class="iccs-progress-container">
            <div class="iccs-progress-bar" style="width: ${Math.max((item.count / maxVal) * 100, 1)}%; background: ${chartColors[index % chartColors.length]}"></div>
          </div>
          <div class="iccs-toggle-icon">${isExpanded ? '▼' : '▶'}</div>
        </div>
        ${childrenHtml}
      </div>
    `;
  }).join('');
}

window.toggleIccs = function(code) {
  if (state.expandedIccs === code) {
    state.expandedIccs = null;
  } else {
    state.expandedIccs = code;
  }
  renderIccsClassification(state.summary.iccs_breakdown);
};

function renderRegionBars(rows) {
  if (!rows || !rows.length) {
    el('region-list').innerHTML = '<div class="chart-empty"><p>暫無地區加權治安排行資料</p></div>';
    return;
  }
  const max = Math.max(...rows.map(row => row.weighted_score), 1);
  el('region-list').innerHTML = rows.slice(0, 10).map(row => `
    <div class="bar-row">
      <div class="bar-label">
        <span>${escapeHtml(row.geography)}</span>
        <strong>權重分: ${fmt.format(row.weighted_score)}</strong>
      </div>
      <div class="bar-track" aria-hidden="true">
        <div class="bar-fill" style="width:${Math.max((row.weighted_score / max) * 100, 1)}%; background: linear-gradient(90deg, #3b82f6, #ef4444)"></div>
      </div>
      <small>案件量: ${fmt.format(row.count)} 件</small>
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

function renderCategoryBars(containerId, dict, fillColor) {
  const container = el(containerId);
  if (!container) return;
  
  const entries = Object.entries(dict || {})
    .map(([key, value]) => ({ key, value: Number(value) }))
    .sort((a, b) => b.value - a.value);
    
  if (entries.length === 0) {
    container.innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">無資料</p></div>';
    return;
  }
  
  const sum = entries.reduce((acc, curr) => acc + curr.value, 0);
  const max = Math.max(...entries.map(e => e.value), 1);
  
  const translateKey = (k) => {
    if (k === 'Unknown' || k === 'unknown' || k === 'null' || !k) return '未詳／未知';
    if (k === 'Under 20') return '20歲以下';
    if (k === '60+') return '60歲以上';
    return k;
  };

  container.innerHTML = entries.map(entry => {
    const percentOfTotal = sum > 0 ? ((entry.value / sum) * 100).toFixed(1) : '0.0';
    const fillPercent = max > 0 ? (entry.value / max) * 100 : 0;
    return `
      <div class="demo-bar-row">
        <div class="demo-bar-info">
          <span class="demo-bar-label" title="${escapeHtml(entry.key)}">${escapeHtml(translateKey(entry.key))}</span>
          <span class="demo-bar-value">${fmt.format(entry.value)} 筆 (${percentOfTotal}%)</span>
        </div>
        <div class="demo-bar-track">
          <div class="demo-bar-fill" style="width: ${Math.max(fillPercent, 1)}%; background: ${fillColor}"></div>
        </div>
      </div>
    `;
  }).join('');
}

function renderAgeBars(containerId, ageData, fillColor) {
  const container = el(containerId);
  if (!container) return;
  
  const order = ['Under 20', '20-29', '30-39', '40-49', '50-59', '60+', 'Unknown'];
  const entries = order.map(key => ({
    key,
    value: Number(ageData?.[key] || 0)
  })).filter(e => e.value > 0);
  
  if (entries.length === 0) {
    container.innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">無資料</p></div>';
    return;
  }
  
  const sum = entries.reduce((acc, curr) => acc + curr.value, 0);
  const max = Math.max(...entries.map(e => e.value), 1);
  
  const translateKey = (k) => {
    if (k === 'Unknown') return '未詳／未知';
    if (k === 'Under 20') return '20歲以下';
    if (k === '60+') return '60歲以上';
    return k + ' 歲';
  };

  container.innerHTML = entries.map(entry => {
    const percentOfTotal = sum > 0 ? ((entry.value / sum) * 100).toFixed(1) : '0.0';
    const fillPercent = max > 0 ? (entry.value / max) * 100 : 0;
    return `
      <div class="demo-bar-row">
        <div class="demo-bar-info">
          <span class="demo-bar-label">${escapeHtml(translateKey(entry.key))}</span>
          <span class="demo-bar-value">${fmt.format(entry.value)} 筆 (${percentOfTotal}%)</span>
        </div>
        <div class="demo-bar-track">
          <div class="demo-bar-fill" style="width: ${Math.max(fillPercent, 1)}%; background: ${fillColor}"></div>
        </div>
      </div>
    `;
  }).join('');
}

function renderGenderBar(containerId, genderData) {
  const container = el(containerId);
  if (!container) return;
  
  const male = Number(genderData?.Male || genderData?.male || genderData?.['男'] || 0);
  const female = Number(genderData?.Female || genderData?.female || genderData?.['女'] || 0);
  const unknown = Number(genderData?.Unknown || genderData?.unknown || genderData?.['Unknown'] || genderData?.['unknown'] || 0);
  const total = male + female + unknown;
  
  if (total === 0) {
    container.innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">無資料</p></div>';
    return;
  }
  
  const pMale = ((male / total) * 100).toFixed(1);
  const pFemale = ((female / total) * 100).toFixed(1);
  const pUnknown = ((unknown / total) * 100).toFixed(1);
  
  container.innerHTML = `
    <div class="gender-bar-wrapper">
      <div class="gender-bar">
        ${male > 0 ? `<div class="gender-segment male" style="width: ${pMale}%" title="男性: ${male} 筆 (${pMale}%)">${pMale}%</div>` : ''}
        ${female > 0 ? `<div class="gender-segment female" style="width: ${pFemale}%" title="女性: ${female} 筆 (${pFemale}%)">${pFemale}%</div>` : ''}
        ${unknown > 0 ? `<div class="gender-segment unknown" style="width: ${pUnknown}%" title="未知: ${unknown} 筆 (${pUnknown}%)">${pUnknown}%</div>` : ''}
      </div>
      <div class="gender-legend">
        <div class="gender-legend-item">
          <span class="gender-dot male"></span>
          <span>男: <strong>${fmt.format(male)}</strong> 筆</span>
        </div>
        <div class="gender-legend-item">
          <span class="gender-dot female"></span>
          <span>女: <strong>${fmt.format(female)}</strong> 筆</span>
        </div>
        <div class="gender-legend-item">
          <span class="gender-dot unknown"></span>
          <span>未知: <strong>${fmt.format(unknown)}</strong> 筆</span>
        </div>
      </div>
    </div>
  `;
}

function renderDemographics(demographics) {
  if (!demographics) {
    el('demographics-gender').innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">暫無資料</p></div>';
    el('demographics-age').innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">暫無資料</p></div>';
    el('demographics-occupation').innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">暫無資料</p></div>';
    el('demographics-education').innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">暫無資料</p></div>';
    el('demographics-income').innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">暫無資料</p></div>';
    el('demographics-city').innerHTML = '<div class="chart-empty" style="min-height: 80px; padding: 10px;"><p style="font-size:12px; margin:0;">暫無資料</p></div>';
    return;
  }
  
  renderGenderBar('demographics-gender', demographics.gender);
  renderAgeBars('demographics-age', demographics.age, 'linear-gradient(90deg, #0284c7, #0369a1)');
  renderCategoryBars('demographics-occupation', demographics.occupation, 'linear-gradient(90deg, #818cf8, #4f46e5)');
  renderCategoryBars('demographics-education', demographics.education, 'linear-gradient(90deg, #34d399, #059669)');
  renderCategoryBars('demographics-income', demographics.income_level, 'linear-gradient(90deg, #fbbf24, #d97706)');
  renderCategoryBars('demographics-city', demographics.birth_city, 'linear-gradient(90deg, #94a3b8, #475569)');
}

async function loadSummary() {
  state.summary = await getJson(`/api/official-summary?month=${encodeURIComponent(currentMonth())}`);
  el('header-record-count').textContent = `${formatMonth(state.summary.source_month)} · ${fmt.format(state.summary.total_cases)} 件`;
  el('overview-summary').textContent = state.summary.summary.text;
  const sourceLink = el('official-source-link');
  sourceLink.href = safeUrl(state.summary.source_url) || '#';
  renderMetrics();
  renderLineChart(state.summary.monthly_counts || []);
  renderIccsClassification(state.summary.iccs_breakdown || []);
  renderRegionBars(state.summary.region_weighted_counts || []);
  renderQualityTable(state.summary.quality || {});
  renderDemographics(state.summary.demographics);
  renderCrossObservation();
}

async function loadOpinion() {
  const selectedMonth = el('opinion-month').value || currentMonth();
  const selectedTopic = el('opinion-topic').value;
  const selectedSource = el('opinion-source').value;
  
  // Construct query url with active filters
  let url = `/api/opinion?month=${encodeURIComponent(selectedMonth)}`;
  if (selectedTopic) url += `&topic=${encodeURIComponent(selectedTopic)}`;
  if (selectedSource) url += `&source=${encodeURIComponent(selectedSource)}`;
  
  state.opinion = await getJson(url);
  const ready = state.opinion.status === 'ready';
  el('opinion-status-badge').textContent = ready ? '資料已更新' : '爬蟲尚未啟動';
  el('opinion-status-badge').classList.toggle('is-pending', !ready);
  
  const postCount = state.opinion.topic_summaries?.length || 0;
  el('opinion-metrics').innerHTML = [
    ['本月文章', postCount, ready ? '已完成排程抓取' : '尚未收集'], 
    ['已接來源', state.opinion.sources.length, ready ? '已上線運作中' : `共 ${state.opinion.sources.length} 個規劃來源`],
    ['已分類文章', postCount, ready ? '依犯罪類別完成標記' : '等待類別標記'], 
    ['可比月份', ready ? 1 : 0, ready ? '提供對照與差距計算' : '等待輿論資料']
  ].map(([label, value, note]) => `<article class="metric"><span>${label}</span><strong>${typeof value === 'number' ? fmt.format(value) : value}</strong><small>${escapeHtml(note)}</small></article>`).join('');
  
  if (ready && state.opinion.daily_counts?.length) {
    const maxVal = Math.max(...state.opinion.daily_counts.map(d => d.count), 1);
    el('opinion-trend').innerHTML = `
      <div class="bars" style="padding:10px 0; max-height:220px; overflow-y:auto;">
        ${state.opinion.daily_counts.map(d => `
          <div class="bar-row">
            <div class="bar-label" style="width:70px;"><span>${d.day} 日</span><strong>${d.count} 篇</strong></div>
            <div class="bar-track" aria-hidden="true" style="height:10px;"><div class="bar-fill" style="width:${(d.count/maxVal)*100}%; height:100%; background:#0891b2;"></div></div>
          </div>
        `).join('')}
      </div>
    `;
  } else {
    el('opinion-trend').innerHTML = `<div class="chart-empty"><strong>尚無可繪製的討論資料</strong><p>${escapeHtml(state.opinion.message)}</p></div>`;
  }
  
  el('opinion-sources').innerHTML = state.opinion.sources.map(source => `
    <article class="source-card">
      <div>
        <h4>${escapeHtml(source.name)}</h4>
        <p>${ready ? '已連接資料庫實時更新' : '完成來源條款檢查後接入'}</p>
      </div>
      <span class="source-status ${ready ? 'state-ready' : ''}">${ready ? '已連線' : '待設定'}</span>
    </article>
  `).join('');
  
  if (ready && state.opinion.topic_summaries?.length) {
    el('opinion-summaries').innerHTML = state.opinion.topic_summaries.map(item => {
      const sentimentText = item.sentiment < -0.4 ? '顯著負面' : (item.sentiment < 0 ? '微幅負面' : (item.sentiment > 0.4 ? '顯著正面' : (item.sentiment > 0 ? '微幅正面' : '中性')));
      const sentimentClass = item.sentiment < 0 ? 'state-pending' : 'state-ready';
      return `
        <article class="case-card" style="margin-bottom:12px; padding:15px; border:1px solid #dce2e7; border-radius:6px; background:#fff;">
          <div class="case-record">
            <div class="case-topline" style="display:flex; justify-content:space-between; align-items:flex-start;">
              <div>
                <h3 style="margin:0 0 6px 0; font-size:16px;">
                  <a href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noreferrer" style="color:#075e54; text-decoration:none; font-weight:bold;">${escapeHtml(item.title)}</a>
                </h3>
                <p class="case-meta" style="margin:0; font-size:12px; color:#607080;">發布日期：${escapeHtml(item.publish_date)} · 來源：${escapeHtml(item.source)}</p>
              </div>
              <span class="state-chip ${sentimentClass}" style="font-size:11px; padding:3px 8px; border-radius:4px;">${sentimentText} (${item.sentiment})</span>
            </div>
            <div class="record-summary" style="margin-top:10px; font-size:13px; line-height:1.5; color:#17212b;">
              <p style="margin:0;">${escapeHtml(item.excerpt)}</p>
            </div>
            <div class="tags" style="margin-top:10px; display:flex; gap:6px; flex-wrap:wrap;">
              <span class="tag" style="background:#e8edf1; color:#075e54; font-size:11px; padding:2px 8px; border-radius:4px;">${escapeHtml(categoryLabels[item.topic] || item.topic)}</span>
              ${(item.keywords || []).map(kw => `<span class="keyword" style="background:#f4f6f8; color:#607080; font-size:11px; padding:2px 6px; border-radius:4px; border:1px solid #e3e7ea;">${escapeHtml(kw)}</span>`).join('')}
            </div>
          </div>
        </article>
      `;
    }).join('');
  } else {
    el('opinion-summaries').innerHTML = `<div class="empty-state"><strong>${escapeHtml(formatMonth(selectedMonth))} 尚無輿論摘要</strong>
      <p>${escapeHtml(state.opinion.message)}</p></div>`;
  }
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
    
    // Demographic details string
    const demoItems = [];
    if (item.gender) demoItems.push(`性別: ${item.gender === 'Male' ? '男' : item.gender === 'Female' ? '女' : '未詳'}`);
    if (item.age) demoItems.push(`年齡: ${item.age}歲`);
    if (item.occupation && item.occupation !== 'Unknown') demoItems.push(`職業: ${item.occupation}`);
    if (item.education && item.education !== 'Unknown') demoItems.push(`教育: ${item.education}`);
    if (item.income_level && item.income_level !== 'Unknown') demoItems.push(`收入: ${item.income_level}`);
    if (item.birth_city && item.birth_city !== 'Unknown') demoItems.push(`出生地: ${item.birth_city}`);
    const demoText = demoItems.length > 0 ? `<p class="case-meta" style="margin-top: 4px; color: var(--primary); font-weight: 550;">被告特徵：${escapeHtml(demoItems.join(' · '))}</p>` : '';

    return `<article class="case-card">
      <div class="case-record">
        <div class="case-topline">
          <div>
            <h3>${escapeHtml(item.jtitle || '未標示案由')}</h3>
            <p class="case-meta">${escapeHtml(item.jdate || '日期未載')} · ${escapeHtml(item.court_folder || '法院未載')} · ${escapeHtml(domainLabels[item.case_domain] || item.case_domain || '')}</p>
            ${demoText}
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
