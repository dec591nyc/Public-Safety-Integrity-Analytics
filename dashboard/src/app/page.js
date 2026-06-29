'use client';

import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import LineChart from './components/LineChart';
import RegionRank from './components/RegionRank';
import AnnualComparison from './components/AnnualComparison';
import SourceContext from './components/SourceContext';
import Feedback from './components/Feedback';
import DrilldownDetail from './components/DrilldownDetail';

const fmt = new Intl.NumberFormat('zh-TW');
const allRegionsLabel = '全部縣市';
const trendWindowMonths = 12;

const priorityTopics = [
  'all_types',
  'property_fraud',
  'drug_public_safety',
  'violence_personal',
  'sexual_safety',
  'integrity_governance',
  'digital_ip',
  'other_types'
];

const segmentOtherRank = (segment) => {
  const metric = String(segment?.metric || '');
  const label = String(segment?.label || '');
  if (metric === '__other__' || label === '其他案類') return 2;
  if (metric === '其他' || label === '其他') return 1;
  return 0;
};

const orderedSegments = (segments) => {
  return [...(segments || [])]
    .filter(segment => Number(segment.count) > 0)
    .sort((a, b) => {
      const rankDiff = segmentOtherRank(a) - segmentOtherRank(b);
      if (rankDiff !== 0) return rankDiff;

      const countDiff = Number(b.count || 0) - Number(a.count || 0);
      if (countDiff !== 0) return countDiff;

      return String(a.label || '').localeCompare(String(b.label || ''), 'zh-Hant');
    });
};

const deltaClass = (value) => {
  const num = Number(value || 0);
  return num > 0 ? 'up' : num < 0 ? 'down' : '';
};

const formatSignedCount = (value) => {
  if (value === null || value === undefined) return '0';
  const num = Number(value);
  return `${num > 0 ? '+' : ''}${fmt.format(num)}`;
};

const formatMonthLabel = (value) => {
  if (/^\d{6}$/.test(value)) {
    return `${value.slice(0, 4)}/${value.slice(4, 6)}`;
  }
  if (/^\d{4}_annual$/.test(value)) {
    return `${value.slice(0, 4)} 年累計`;
  }
  return value;
};

const formatPct = (value) => {
  if (value === null || value === undefined) return '無資料';
  const num = Number(value);
  return `${num > 0 ? '+' : ''}${num.toFixed(1)}%`;
};

export default function DashboardPage() {
  const [activeView, setActiveView] = useState('year'); // 'year', 'topics', 'local', 'method', 'feedback'
  const [dataMode, setDataMode] = useState('month'); // 'month', 'year'
  const [allMonths, setAllMonths] = useState([]);
  const [selectedMonth, setSelectedMonth] = useState('');
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);

  // Active topic states (used in topics and local views)
  const [activeTopic, setActiveTopic] = useState('all_types');
  const [activeRegion, setActiveRegion] = useState(null);
  const [activeMetric, setActiveMetric] = useState(null);

  // Toast state
  const [toastMessage, setToastMessage] = useState('');
  const [showToast, setShowToast] = useState(false);

  const triggerToast = (msg) => {
    setToastMessage(msg);
    setShowToast(true);
    setTimeout(() => setShowToast(false), 3200);
  };

  // 1. Fetch available months list
  useEffect(() => {
    const fetchMonths = async () => {
      try {
        const res = await fetch('/api/months');
        const data = await res.json();
        const rawItems = data.items?.length ? data.items : [];
        const items = rawItems.filter(item => /^\d{6}$/.test(item.source_month));
        setAllMonths(items);
        
        if (items.length > 0) {
          setSelectedMonth(items[0].source_month);
        } else {
          setAllMonths([{ source_month: '202605', count: 0 }]);
          setSelectedMonth('202605');
        }
      } catch (err) {
        console.error("Failed to load months:", err);
        setAllMonths([{ source_month: '202605', count: 0 }]);
        setSelectedMonth('202605');
      }
    };
    fetchMonths();
  }, []);

  // 2. Adjust selectedMonth when dataMode changes
  const handleDataModeChange = (mode) => {
    setDataMode(mode);
    if (allMonths.length > 0) {
      if (mode === 'year') {
        let year = selectedMonth;
        if (/^\d{6}$/.test(selectedMonth)) {
          year = selectedMonth.slice(0, 4);
        } else if (selectedMonth.endsWith('_annual')) {
          year = selectedMonth.split('_')[0];
        } else {
          year = allMonths[0].source_month.slice(0, 4);
        }
        setSelectedMonth(`${year}_annual`);
      } else {
        let year = allMonths[0].source_month.slice(0, 4);
        if (selectedMonth.endsWith('_annual')) {
          year = selectedMonth.split('_')[0];
        } else if (/^\d{6}$/.test(selectedMonth)) {
          year = selectedMonth.slice(0, 4);
        }
        const matchingMonth = allMonths.find(item => item.source_month.startsWith(year));
        if (matchingMonth) {
          setSelectedMonth(matchingMonth.source_month);
        } else {
          setSelectedMonth(allMonths[0].source_month);
        }
      }
    }
  };

  // 3. Fetch summary for selectedMonth
  useEffect(() => {
    if (!selectedMonth) return;
    const fetchSummary = async () => {
      setLoading(true);
      try {
        const res = await fetch(`/api/official-summary?month=${encodeURIComponent(selectedMonth)}`);
        const data = await res.json();
        setSummary(data);
      } catch (err) {
        console.error("Failed to load summary:", err);
      } finally {
        setLoading(false);
      }
    };
    fetchSummary();
  }, [selectedMonth]);

  // Derived variables
  const topicList = summary?.topic_drilldowns || [];
  const activeTopicList = priorityTopics
    .map(id => topicList.find(topic => topic.id === id))
    .filter(Boolean);
  const activeTopicRecord = activeTopicList.find(t => t.id === activeTopic) || activeTopicList[0] || null;

  const uniqueYears = Array.from(new Set(
    allMonths
      .map(item => item.source_month.slice(0, 4))
      .filter(y => /^\d{4}$/.test(y))
  )).sort((a, b) => b.localeCompare(a));

  const handleTopicChange = (topicId) => {
    setActiveTopic(topicId);
    setActiveRegion(null);
    setActiveMetric(null);
  };

  // AI trends observation context builder
  const renderTopicAiAnalysis = (topic) => {
    if (!topic || !topic.trend || topic.trend.length < 3) {
      return (
        <div className="chart-empty compact">
          <p>主題趨勢月份不足，暫不產生分析。</p>
        </div>
      );
    }

    const series = [...topic.trend].slice(-trendWindowMonths);
    const latest = series[series.length - 1];
    const previous = series[series.length - 2];
    const latestCount = Number(latest.count || 0);
    const previousCount = Number(previous.count || 0);
    const average = series.reduce((sum, row) => sum + Number(row.count || 0), 0) / series.length;
    const peak = [...series].sort((a, b) => Number(b.count || 0) - Number(a.count || 0))[0];
    const low = [...series].sort((a, b) => Number(a.count || 0) - Number(b.count || 0))[0];
    const mainSegment = orderedSegments(topic.segments)[0];
    const topRegion = topic.region_breakdowns?.length ? topic.region_breakdowns[0] : (topic.top_regions?.[0] || null);
    const delta = latestCount - previousCount;

    const scopeNote = topic.is_total_scope
      ? '此分頁採全部官方案類加總，資料範圍可與全國總案量曲線核對。'
      : topic.is_residual_scope
        ? '此分頁收納未放入前六個分析主題的官方案類，用來補足主題分類外的案件。'
        : '此分頁是民眾關注主題包，非完整分類表；不同主題間不應直接相加。';

    const monthNum = Number(latest.month.slice(4));
    let temporalFactor = '';
    if (monthNum === 2) {
      temporalFactor = '2月份受限於全月天數最少，且適逢農曆春節連續假期，司法機關登錄工作天數減少、社會活動亦多轉入家庭內部，通常會呈現季節性的顯著低谷。';
    } else if (monthNum === 7 || monthNum === 8) {
      temporalFactor = `${monthNum}月份正值暑期長假，青少年與學生族群戶外活動與網路使用時間顯著增加，在時空背景上往往與網路詐騙、涉毒或群聚人身安全案件的波動週期高度吻合。`;
    } else if (monthNum === 12 || monthNum === 1) {
      temporalFactor = `${monthNum === 12 ? '12月年底' : '1月年初'}適逢節慶尾牙與跨年大型活動，社會流動頻繁，治安機關通常會加強掃蕩與專案執法，同時也伴隨行政機關年度結案的申報效應，使得數據出現集中增減。`;
    } else {
      temporalFactor = `${monthNum}月份處於常態社會運作週期，案件量主要受當月工作天數與警政常態執法強度影響。`;
    }

    let trendSlope = '';
    if (delta > 0) {
      const pct = ((delta / previousCount) * 100).toFixed(1);
      trendSlope = `相較於前月，本月數量增加了 ${fmt.format(delta)} 件（增幅約 ${pct}%），`;
    } else if (delta < 0) {
      const pct = (Math.abs(delta) / previousCount * 100).toFixed(1);
      trendSlope = `相較於前月，本月數量減少了 ${fmt.format(Math.abs(delta))} 件（降幅約 ${pct}%），`;
    } else {
      trendSlope = `相較於前月，本月數量持平，`;
    }

    let levelCompare = '';
    if (latestCount >= peak.count * 0.95) {
      levelCompare = `目前案量已逼近近一年內的高峰值（${formatMonthLabel(peak.month)} 的 ${fmt.format(peak.count)} 件），需密切防範該類問題擴大。`;
    } else if (latestCount <= low.count * 1.05) {
      levelCompare = `目前案量處於近一年內的相對低點（接近 ${formatMonthLabel(low.month)} 的 ${fmt.format(low.count)} 件），呈現穩定態勢。`;
    } else {
      levelCompare = `目前案量在近一年平均線（${fmt.format(Math.round(average))} 件）上下波動。`;
    }

    let spatialFactor = '';
    if (topRegion) {
      spatialFactor = `在地域分佈上，${topRegion.geography} 以 ${fmt.format(topRegion.total)} 件（佔該主題全國 ${topRegion.share_pct}%）居於首位，這反映了人口密度高、都會區治安特性對整體統計量能的拉動效應。`;
    }

    const mainCategoryNote = mainSegment ? `最新月之主要案類為「${mainSegment.label}」（${fmt.format(mainSegment.count)} 件）。` : '';
    const explanation = `${trendSlope}${temporalFactor}${levelCompare}${spatialFactor}${mainCategoryNote}${scopeNote}此研判僅以官方刑事發生數之時空特徵為導向進行解讀，不宜直接推定為犯罪成因 or 治安惡化之單一論斷。`;

    return (
      <div className="topic-ai-analysis">
        <div className="topic-analysis-head">
          <span className="subhead">AI 案件趨勢分析</span>
          <strong>{topic.label}：{formatMonthLabel(latest.month)} {fmt.format(latestCount)} 件</strong>
        </div>
        <div className="evidence-grid compact" style={{ margin: '10px 0' }}>
          <div className="evidence-chip">
            <span>較前月</span>
            <strong className={deltaClass(delta)}>{formatSignedCount(delta)}</strong>
          </div>
          <div className="evidence-chip">
            <span>近 12 月平均</span>
            <strong>{fmt.format(Math.round(average))} 件</strong>
          </div>
          <div className="evidence-chip">
            <span>高峰月</span>
            <strong>{formatMonthLabel(peak.month)} · {fmt.format(Number(peak.count || 0))}</strong>
          </div>
          <div className="evidence-chip">
            <span>低點月</span>
            <strong>{formatMonthLabel(low.month)} · {fmt.format(Number(low.count || 0))}</strong>
          </div>
        </div>
        <p style={{ fontSize: '13px', color: 'var(--muted-ink)', lineHeight: '1.6' }}>{explanation}</p>
      </div>
    );
  };

  const renderAiInsightPanel = () => {
    const insight = summary?.ai_insight;
    if (!insight || insight.status !== 'ready') {
      return (
        <div className="chart-empty compact">
          <p>趨勢月份不足，暫不產生研判。</p>
        </div>
      );
    }

    return (
      <div className="ai-insight">
        <div className="insight-head">
          <span className={`severity ${insight.severity === 'high' ? 'high' : insight.severity === 'medium' ? 'medium' : ''}`}>
            {insight.severity === 'high' ? '顯著異常' : insight.severity === 'medium' ? '中度波動' : '常態觀察'}
          </span>
          <strong style={{ fontSize: '16px', display: 'block', marginTop: '6px' }}>{insight.title}</strong>
        </div>
        <p style={{ marginTop: '8px', fontSize: '13px', color: 'var(--muted-ink)', lineHeight: '1.6' }}>
          {insight.abstract}
        </p>

        <span className="subhead" style={{ marginTop: '12px', display: 'block' }}>研判依據指標</span>
        <div className="evidence-grid compact" style={{ marginTop: '6px' }}>
          {(insight.evidence || []).map((item, idx) => (
            <div key={idx} className="evidence-chip">
              <span>{item.label}</span>
              <strong className={item.delta !== undefined ? deltaClass(item.delta) : ''}>
                {item.display}
              </strong>
            </div>
          ))}
        </div>

        <span className="subhead" style={{ marginTop: '14px', display: 'block' }}>主要治安觀察案類</span>
        <ul className="rank-list" style={{ marginTop: '6px' }}>
          {(insight.topic_observations || []).map((row, idx) => (
            <li key={idx}>
              <span>{row.label}</span>
              <strong>{fmt.format(row.count)} 件</strong>
              <em className={deltaClass(row.change_pct)}>
                {row.change_pct === null || row.change_pct === undefined
                  ? '無前月基準'
                  : `${row.change_pct > 0 ? '+' : ''}${row.change_pct}%`}
              </em>
            </li>
          ))}
        </ul>
        <p className="method-note" style={{ marginTop: '14px' }}>{insight.conclusion}</p>
      </div>
    );
  };

  const formatMonth = (m) => {
    if (!m) return '';
    if (m.endsWith('_annual')) {
      return `${m.split('_')[0]} 完整年度`;
    }
    const y = m.substring(0, 4);
    const mm = m.substring(4, 6);
    return `${y}年${parseInt(mm, 10)}月`;
  };

  return (
    <div>
      {/* Header section */}
      <Header totalCases={summary?.total_cases} sourceMonth={summary?.source_month} />

      {/* Main Container */}
      <main id="main-content">
        {/* Navigation Tabs */}
        <nav id="view-tabs" className="view-tabs" aria-label="資料視覺分頁">
          {[
            ['year', '年度比較'],
            ['topics', '案類趨勢'],
            ['local', '縣市細究'],
            ['method', '資料範圍與更新機制'],
            ['feedback', '意見回饋']
          ].map(([id, label]) => (
            <button
              key={id}
              type="button"
              className={`view-tab ${activeView === id ? 'is-active' : ''}`}
              onClick={() => setActiveView(id)}
            >
              {label}
            </button>
          ))}
        </nav>

        {/* Global Selectors */}
        {activeView !== 'feedback' && (
          <section className="query-shell" aria-labelledby="query-title">
            <div>
              <span id="query-title">{dataMode === 'year' ? '資料年度' : '資料月份'}</span>
              <small>切換後，目前分頁會同步更新。</small>
            </div>
            <form id="global-query" className="query-grid" onSubmit={e => e.preventDefault()}>
              <div className="mode-selector-group">
                <span className="field-label">資料顯示模式</span>
                <div className="segmented-control">
                  <button
                    type="button"
                    className={`mode-btn ${dataMode === 'month' ? 'is-active' : ''}`}
                    onClick={() => handleDataModeChange('month')}
                  >
                    單月數據
                  </button>
                  <button
                    type="button"
                    className={`mode-btn ${dataMode === 'year' ? 'is-active' : ''}`}
                    onClick={() => handleDataModeChange('year')}
                  >
                    年度累計
                  </button>
                </div>
              </div>
              <label id="month-select-label">
                {dataMode === 'year' ? '選擇年度' : '選擇月份'}
                <select
                  id="month"
                  name="month"
                  aria-label={dataMode === 'year' ? '資料年度' : '資料月份'}
                  value={selectedMonth}
                  onChange={e => setSelectedMonth(e.target.value)}
                >
                  {dataMode === 'year' ? (
                    uniqueYears.map(year => (
                      <option key={year} value={`${year}_annual`}>
                        {`${year}年度`}
                      </option>
                    ))
                  ) : (
                    allMonths.map(item => (
                      <option key={item.source_month} value={item.source_month}>
                        {formatMonth(item.source_month)}
                      </option>
                    ))
                  )}
                </select>
              </label>
            </form>
          </section>
        )}

        {loading ? (
          <div className="chart-empty">
            <span style={{ fontSize: '18px', fontWeight: 'bold' }}>資料載入中...</span>
          </div>
        ) : (
          <>
            {/* 1. Year View Panel */}
            {activeView === 'year' && (
              <section className="dashboard-grid intelligence-grid" aria-label="年度比較與 AI 研判">
                <AnnualComparison annualComparison={summary?.annual_comparison} />
                <article className="panel ai-panel">
                  <div className="panel-head">
                    <div>
                      <p className="section-kicker">AI 輔助趨勢研判</p>
                      <h3>趨勢異常研判</h3>
                      <p>依官方統計與最近 12 個月趨勢產生可追溯的提示，不作為犯罪原因定論。</p>
                    </div>
                    <span className="chart-type">證據 + 限制</span>
                  </div>
                  {renderAiInsightPanel()}
                </article>
              </section>
            )}

            {/* 2. Topics View Panel */}
            {activeView === 'topics' && (
              <section className="dashboard-grid topic-workspace">
                <article className="panel topic-panel">
                  <div className="panel-head">
                    <div>
                      <p className="section-kicker">治安主題詳情</p>
                      <h3>案類主題趨勢與構成</h3>
                      <p>選擇一個治安主題，查看近月走勢與主要案類來源。</p>
                    </div>
                    <span className="chart-type">12 個月 MoM 趨勢</span>
                  </div>

                  {/* Topic button grid */}
                  <div className="topic-tabs compact" role="list">
                    {activeTopicList.map(topic => (
                      <button
                        key={topic.id}
                        type="button"
                        className={`topic-tab ${topic.id === activeTopic ? 'is-active' : ''}`}
                        onClick={() => handleTopicChange(topic.id)}
                      >
                        <span>{topic.label}</span>
                        <strong>{fmt.format(topic.total)}</strong>
                      </button>
                    ))}
                  </div>

                  {activeTopicRecord ? (
                    <>
                      <div className="topic-narrative" style={{ marginBottom: '16px', marginTop: '16px' }}>
                        <h4>{activeTopicRecord.label}</h4>
                        <p style={{ marginTop: '6px', marginBottom: '12px' }}>{activeTopicRecord.description}</p>
                        <div className="mini-stat-grid">
                          <div className="mini-stat">
                            <span>主題案量</span>
                            <strong>{fmt.format(activeTopicRecord.total)} 件</strong>
                            <small>占總案量 {activeTopicRecord.share_pct || '0'}%</small>
                          </div>
                          <div className="mini-stat">
                            <span>近月變化</span>
                            <strong className={deltaClass(activeTopicRecord.trend?.[activeTopicRecord.trend.length - 1]?.count - activeTopicRecord.trend?.[activeTopicRecord.trend.length - 2]?.count)}>
                              {activeTopicRecord.trend ? latestTrendChange(activeTopicRecord.trend) : '無資料'}
                            </strong>
                            <small>與前一個月相比</small>
                          </div>
                          <div className="mini-stat">
                            <span>主要案類</span>
                            <strong>
                              {orderedSegments(activeTopicRecord.segments)[0]
                                ? orderedSegments(activeTopicRecord.segments)[0].label
                                : '無資料'}
                            </strong>
                            <small>
                              {orderedSegments(activeTopicRecord.segments)[0]
                                ? `${fmt.format(orderedSegments(activeTopicRecord.segments)[0].count)} 件`
                                : ''}
                            </small>
                          </div>
                          <div className="mini-stat">
                            <span>範圍 年增率</span>
                            <strong>
                              {activeTopicRecord.yoy_pct !== null && activeTopicRecord.yoy_pct !== undefined
                                ? formatPct(activeTopicRecord.yoy_pct)
                                : '無資料'}
                            </strong>
                            <small>與去年同月相比</small>
                          </div>
                        </div>
                      </div>
                      
                      {/* Render Recharts line chart */}
                      <LineChart data={activeTopicRecord.trend} compact={true} />

                      {/* AI interpretation of the topic trend */}
                      {renderTopicAiAnalysis(activeTopicRecord)}
                    </>
                  ) : (
                    <div className="chart-empty compact">
                      <p>無主題資料</p>
                    </div>
                  )}
                </article>

                <aside className="panel region-rank-panel">
                  {activeTopicRecord && (
                    <RegionRank
                      activeTopic={activeTopicRecord}
                      activeRegion={activeRegion}
                      setActiveRegion={setActiveRegion}
                      activeMetric={activeMetric}
                      setActiveMetric={setActiveMetric}
                    />
                  )}
                </aside>
              </section>
            )}

            {/* 3. Local (County Detail) View Panel */}
            {activeView === 'local' && (
              <section className="dashboard-grid local-workspace">
                <article className="panel drill-panel">
                  <div className="panel-head">
                    <div>
                      <p className="section-kicker">縣市細究路徑</p>
                      <h3>縣市與案類細究</h3>
                      <p>選擇主題、縣市與案類後，查看該縣市案件類型的比例與排名。</p>
                    </div>
                    <span className="chart-type">主題 / 縣市 / 案類</span>
                  </div>

                  <div className="topic-tabs compact" role="list">
                    {activeTopicList.map(topic => (
                      <button
                        key={topic.id}
                        type="button"
                        className={`topic-tab ${topic.id === activeTopic ? 'is-active' : ''}`}
                        onClick={() => handleTopicChange(topic.id)}
                      >
                        <span>{topic.label}</span>
                        <strong>{fmt.format(topic.total)}</strong>
                      </button>
                    ))}
                  </div>

                  <DrilldownDetail
                    activeTopic={activeTopicRecord}
                    activeRegion={activeRegion}
                    setActiveRegion={setActiveRegion}
                    activeMetric={activeMetric}
                    setActiveMetric={setActiveMetric}
                  />
                </article>

                <aside className="panel region-panel">
                  <div className="panel-head">
                    <div>
                      <p className="section-kicker">縣市觀測選擇</p>
                      <h3>縣市選擇</h3>
                      <p>點選縣市後，左側比例與排名會同步更新。</p>
                    </div>
                  </div>
                  <div className="topic-region-list">
                    {activeTopicRecord && [
                      { geography: '全部縣市', total: activeTopicRecord.total, isNational: true },
                      ...(activeTopicRecord.region_breakdowns || activeTopicRecord.top_regions || [])
                    ].map((row, idx) => (
                      <button
                        key={idx}
                        type="button"
                        className={`region-row ${row.geography === (activeRegion || '全部縣市') ? 'is-active' : ''} ${row.isNational ? 'is-national' : ''}`}
                        onClick={() => setActiveRegion(row.geography === '全部縣市' ? null : row.geography)}
                      >
                        <div className="region-label">
                          <span>{row.geography}</span>
                          <strong>{fmt.format(row.total)} 件</strong>
                          <small>
                            {row.isNational
                              ? '全國範圍'
                              : `年增率 (YoY) ${formatPct(row.yoy_pct)} · 占本主題 ${row.share_pct || '0'}%`}
                          </small>
                        </div>
                      </button>
                    ))}
                  </div>
                </aside>
              </section>
            )}

            {/* 4. Method / Data Scope Panel */}
            {activeView === 'method' && (
              <section className="dashboard-grid context-grid">
                <article className="panel">
                  <div className="panel-head">
                    <div>
                      <p className="section-kicker">全國總案量背景</p>
                      <h3>全國總案量趨勢</h3>
                      <p>總案量不作為首頁主 KPI，只用來理解各主題占比與統計範圍。</p>
                    </div>
                    <span className="chart-type">12 個月 MoM 趨勢</span>
                  </div>
                  {/* Total monthly trend Recharts line chart */}
                  <LineChart data={summary?.monthly_counts} compact={false} />
                  <p className="method-note inline" style={{ marginTop: '12px' }}>
                    此曲線每一點代表該月份全國總案量；不同月份不可相加後拿來對照目前選取月份的案類構成。
                  </p>
                </article>
                <SourceContext summary={summary} />
              </section>
            )}

            {/* 5. Feedback Panel */}
            {activeView === 'feedback' && (
              <Feedback />
            )}
          </>
        )}
      </main>

      {showToast && (
        <div className="toast is-visible" role="status" aria-live="polite">
          {toastMessage}
        </div>
      )}
    </div>
  );
}

// Helper calculation functions
const latestTrendChange = (rows) => {
  if (!rows || rows.length < 2) return '無資料';
  const latest = rows[rows.length - 1];
  const previous = rows[rows.length - 2];
  return formatChange(latest.count, previous.count);
};

const formatChange = (current, previous) => {
  if (!previous) return '無前月基準';
  const change = ((current - previous) / previous) * 100;
  const sign = change > 0 ? '+' : '';
  return `${sign}${change.toFixed(1)}%`;
};
