'use client';

import React, { useState } from 'react';

const fmt = new Intl.NumberFormat('zh-TW');

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

const safeColor = (value) => {
  return /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#64748b';
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

const formatSignedCount = (value) => {
  if (value === null || value === undefined) return '0';
  const num = Number(value);
  return `${num > 0 ? '+' : ''}${fmt.format(num)}`;
};

const deltaClass = (value) => {
  const num = Number(value || 0);
  return num > 0 ? 'up' : num < 0 ? 'down' : '';
};

const combineOtherSegments = (segments, total) => {
  let otherCount = 0;
  const filtered = [];
  for (const seg of segments) {
    if (seg.metric === '__other__' || seg.label === '其他案類' || seg.metric === '其他' || seg.label === '其他') {
      otherCount += Number(seg.count || 0);
    } else {
      filtered.push(seg);
    }
  }
  if (otherCount > 0) {
    filtered.push({
      metric: '__other__',
      label: '其他案類',
      count: otherCount,
      share_pct: total ? Number(((otherCount / total) * 100).toFixed(1)) : 0,
      color: '#94a3b8'
    });
  }
  return filtered.sort((a, b) => segmentOtherRank(a) - segmentOtherRank(b) || Number(b.count || 0) - Number(a.count || 0));
};

export default function AnnualComparison({ annualComparison }) {
  const [activeTab, setActiveTab] = useState('kpi'); // 'kpi', 'full', 'same'

  if (!annualComparison || !annualComparison.rows || annualComparison.rows.length === 0) {
    return (
      <div className="chart-empty compact">
        <p>年度比較資料不足。</p>
      </div>
    );
  }

  const rowsDesc = [...annualComparison.rows].sort((a, b) => Number(b.year) - Number(a.year));
  const latest = rowsDesc[0];
  const previous = rowsDesc.find(row => Number(row.year) === Number(latest.year) - 1) || rowsDesc[1] || null;
  
  const hasYoy = latest.yoy_pct !== null && latest.yoy_pct !== undefined;
  const yoyClass = hasYoy ? (Number(latest.yoy_pct) >= 0 ? 'up' : 'down') : '';

  const renderStackedBar = (itemSegments, itemTotal) => {
    const visible = orderedSegments(itemSegments);
    if (!visible.length || itemTotal <= 0) {
      return <span className="stacked-empty">無資料</span>;
    }
    return visible.map((segment, index) => {
      const segmentWidth = Math.max((Number(segment.count) / itemTotal) * 100, 0.8);
      const title = `${segment.label}: ${fmt.format(segment.count)} 件 (${segment.share_pct}%)`;
      return (
        <span
          key={index}
          className="stacked-segment"
          style={{ width: `${segmentWidth}%`, backgroundColor: safeColor(segment.color) }}
          title={title}
        />
      );
    });
  };

  const renderSegmentLegend = (itemSegments) => {
    const visible = orderedSegments(itemSegments);
    return (
      <div className="segment-legend readonly">
        {visible.map((segment, index) => (
          <div key={index} className="segment-key">
            <i style={{ backgroundColor: safeColor(segment.color) }}></i>
            <span>{segment.label}</span>
            <strong>{fmt.format(segment.count)}</strong>
          </div>
        ))}
      </div>
    );
  };

  const renderChangeDrivers = (driversList) => {
    if (!driversList || driversList.length === 0) {
      return <div className="chart-empty compact"><p>目前尚無可比較數據。</p></div>;
    }

    return [...driversList].sort((a, b) => Number(b.year) - Number(a.year)).map((row, index) => {
      const maxDelta = Math.max(...(row.drivers || []).map(item => Math.abs(Number(item.delta || 0))), 1);
      
      const drivers = (row.drivers || []).map((driver, dIdx) => {
        const direction = deltaClass(driver.delta);
        const width = Math.max((Math.abs(Number(driver.delta || 0)) / maxDelta) * 100, 2);
        return (
          <div key={dIdx} className="delta-row">
            <div className="delta-label">
              <i style={{ backgroundColor: safeColor(driver.color) }}></i>
              <span>{driver.label}</span>
            </div>
            <div className="delta-track">
              <b className={direction} style={{ width: `${width}%`, backgroundColor: safeColor(driver.color) }}></b>
            </div>
            <strong className={direction}>{formatSignedCount(driver.delta)}</strong>
            <small>{fmt.format(driver.previous || 0)} → {fmt.format(driver.current || 0)}</small>
          </div>
        );
      });

      const direction = deltaClass(row.total_delta);

      return (
        <div key={index} className="change-card">
          <div className="change-head">
            <div>
              <span>{row.year} 年 與 {row.previous_year} 年對比</span>
              <small>{row.period_label} · 全部官方案類差額拆解</small>
            </div>
            <strong className={direction}>{formatSignedCount(row.total_delta)}</strong>
          </div>
          <div className="delta-list">{drivers}</div>
          <div className="reconcile-line">
            <span>總計差額 <span>{formatSignedCount(row.total_delta)}</span></span>
            <span>案類差額加總 <span>{formatSignedCount(row.metric_delta_sum)}</span></span>
            <span>差額 <span>{formatSignedCount(row.reconciliation_delta)}</span></span>
          </div>
        </div>
      );
    });
  };

  return (
    <div className="panel" data-view-panel="year">
      <div className="panel-head">
        <div>
          <h2>年度累計變化分析</h2>
          <p>觀察統計年度與前一年同期累計變化，分析整體趨勢驅動因子</p>
        </div>
      </div>

      <div className="sub-tabs" id="annual-tabs" role="list">
        <button
          type="button"
          className={`sub-tab ${activeTab === 'kpi' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('kpi')}
        >
          年度 KPI 與 年增率 (YoY)
        </button>
        <button
          type="button"
          className={`sub-tab ${activeTab === 'full' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('full')}
        >
          完整年度變化拆解
        </button>
        <button
          type="button"
          className={`sub-tab ${activeTab === 'same' ? 'is-active' : ''}`}
          onClick={() => setActiveTab('same')}
        >
          同期間變化拆解
        </button>
      </div>

      {activeTab === 'kpi' && (
        <>
          <div className="annual-summary">
            <div className="mini-stat">
              <span>比較範圍</span>
              <strong>{annualComparison.period_label}</strong>
              <small>避免以未完整年度對比全年</small>
            </div>
            <div className="mini-stat">
              <span>{latest.year} 同期累計</span>
              <strong>{fmt.format(latest.total)} 件</strong>
              <small>截至 {annualComparison.period_label}</small>
            </div>
            <div className="mini-stat">
              <span>{previous ? `${previous.year} 同期累計` : '前一年基準'}</span>
              <strong>{previous ? `${fmt.format(previous.total)} 件` : '無資料'}</strong>
              <small>作為 年增率 (YoY) 對照</small>
            </div>
            <div className="mini-stat">
              <span>年增率 (YoY)</span>
              <strong className={yoyClass}>{formatPct(latest.yoy_pct)}</strong>
              <small>以最近年度呈現</small>
            </div>
          </div>

          <div className="annual-peak-section" style={{ marginTop: '14px' }}>
            <span className="subhead">每年高峰月與主要案類</span>
            <div className="peak-list">
              {(annualComparison.peak_months || [])
                .sort((a, b) => Number(b.year) - Number(a.year))
                .map((row, index) => {
                  const combined = combineOtherSegments(row.segments, row.total);
                  let topMetricSum = 0;
                  let otherCount = 0;
                  for (const seg of combined) {
                    if (seg.metric === '__other__' || seg.label === '其他案類') {
                      otherCount += Number(seg.count || 0);
                    } else {
                      topMetricSum += Number(seg.count || 0);
                    }
                  }
                  return (
                    <div key={index} className="peak-row">
                      <div className="peak-label">
                        <span>{row.year} 年高峰月：{formatMonthLabel(row.peak_month)}</span>
                        <strong>單月總計 {fmt.format(row.total)} 件</strong>
                        <small>搜尋範圍 {row.scope}</small>
                      </div>
                      <div className="stacked-track">
                        {renderStackedBar(combined, Number(row.total || 0))}
                      </div>
                      {renderSegmentLegend(combined)}
                      <div className="peak-check">
                        <span>前 10 大合計 {fmt.format(topMetricSum)} 件</span>
                        <span>其餘案類 {fmt.format(otherCount)} 件</span>
                        <span>檢查：{fmt.format(topMetricSum + otherCount)} / {fmt.format(row.total || 0)} 件</span>
                      </div>
                    </div>
                  );
                })}
            </div>
          </div>
        </>
      )}

      {activeTab === 'same' && (
        <div className="annual-change-section">
          <span className="subhead">同期間變化拆解：哪些案類推動 KPI 年增率 (YoY)？</span>
          <div className="change-list">
            {renderChangeDrivers(annualComparison.change_drivers || [])}
          </div>
        </div>
      )}

      {activeTab === 'full' && (
        <div className="annual-change-section">
          <span className="subhead">完整年度變化拆解：1-12 月總量怎麼變？</span>
          <div className="change-list">
            {annualComparison.full_year_change_drivers && annualComparison.full_year_change_drivers.length > 0 ? (
              renderChangeDrivers(annualComparison.full_year_change_drivers)
            ) : (
              <div className="chart-empty compact">
                <p>目前尚無足夠完整年度可比較。</p>
              </div>
            )}
          </div>
        </div>
      )}

      {annualComparison.note && (
        <p className="method-note" style={{ marginTop: '12px' }}>
          {annualComparison.note}
        </p>
      )}
    </div>
  );
}
