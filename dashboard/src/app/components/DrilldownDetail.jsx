'use client';

import React from 'react';

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

const formatPct = (value) => {
  if (value === null || value === undefined) return '無資料';
  const num = Number(value);
  return `${num > 0 ? '+' : ''}${num.toFixed(1)}%`;
};

const deltaClass = (value) => {
  const num = Number(value || 0);
  return num > 0 ? 'up' : num < 0 ? 'down' : '';
};

const segmentCount = (segments, metric) => {
  if (!segments || !metric) return 0;
  const match = segments.find(s => s.metric === metric);
  return match ? Number(match.count || 0) : 0;
};

export default function DrilldownDetail({
  activeTopic,
  activeRegion,
  setActiveRegion,
  activeMetric,
  setActiveMetric
}) {
  if (!activeTopic) {
    return (
      <div className="chart-empty compact">
        <p>請先選擇一個治安主題。</p>
      </div>
    );
  }

  const regionBreakdowns = activeTopic.region_breakdowns?.length
    ? activeTopic.region_breakdowns
    : (activeTopic.top_regions || []);

  const nationalRecord = {
    geography: '全部縣市',
    total: Number(activeTopic.total || 0),
    share_pct: 100,
    previous_year_total: activeTopic.previous_year_total,
    yoy_pct: activeTopic.yoy_pct,
    segments: orderedSegments(activeTopic.segments || []),
    isNational: true
  };

  const allRegions = [nationalRecord, ...regionBreakdowns];
  
  // Find selected region or fallback to national
  const selectedRegionRecord = allRegions.find(r => r.geography === activeRegion) || nationalRecord;

  // Find selected metric or fallback to the first segment
  const sortedSegments = orderedSegments(activeTopic.segments || []);
  const selectedMetricRecord = sortedSegments.find(s => s.metric === activeMetric) || sortedSegments[0] || null;

  const countyMetricCount = segmentCount(selectedRegionRecord?.segments, selectedMetricRecord?.metric);
  const nationalMetricCount = segmentCount(activeTopic.segments, selectedMetricRecord?.metric);
  const scopeLabel = selectedRegionRecord?.isNational ? '全國' : '縣市';

  const drillScopeNote = activeTopic.is_total_scope
    ? `目前「${activeTopic.label}」為全部官方案類加總；「${selectedMetricRecord?.label || '未選案類'}」是其中一個單一案類。`
    : activeTopic.is_residual_scope
      ? `目前「${activeTopic.label}」為前六個分析主題之外的官方案類集合；「${selectedMetricRecord?.label || '未選案類'}」是其中一個單一案類。`
      : `目前「${activeTopic.label}」為主題包合計；「${selectedMetricRecord?.label || '未選案類'}」是單一案類。兩者資料範圍不同，例如性犯罪與家庭會把妨害性自主罪、妨害風化、妨害家庭及婚姻、遺棄合併。`;

  // Get all counties ranking for the selected metric
  const countyMetricRows = regionBreakdowns
    .map(row => ({ geography: row.geography, count: segmentCount(row.segments, selectedMetricRecord?.metric) }))
    .filter(row => row.count > 0)
    .sort((a, b) => b.count - a.count);

  const top6Counties = countyMetricRows.slice(0, 6);
  const otherCountyCount = countyMetricRows.slice(6).reduce((sum, row) => sum + row.count, 0);
  const countyRankRows = otherCountyCount > 0
    ? [...top6Counties, { geography: '其他縣市', count: otherCountyCount, isOther: true }]
    : top6Counties;

  const renderStackedBar = (itemSegments, itemTotal) => {
    const visible = orderedSegments(itemSegments);
    if (!visible.length || itemTotal <= 0) {
      return <span className="stacked-empty">無資料</span>;
    }
    return visible.map((segment, index) => {
      const segmentWidth = Math.max((Number(segment.count) / itemTotal) * 100, 0.8);
      const title = `${segment.label}: ${fmt.format(segment.count)} 件 (${segment.share_pct || Math.round((segment.count/itemTotal)*100)}%)`;
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
      <div className="segment-legend">
        {visible.map((segment, index) => (
          <button
            key={index}
            type="button"
            className={`segment-key ${segment.metric === selectedMetricRecord?.metric ? 'is-active' : ''}`}
            onClick={() => setActiveMetric(segment.metric)}
          >
            <i style={{ backgroundColor: safeColor(segment.color) }}></i>
            <span>{segment.label}</span>
            <strong>{fmt.format(segment.count)}</strong>
          </button>
        ))}
      </div>
    );
  };

  return (
    <>
      <div className="metric-picker">
        <span className="subhead">案類選擇</span>
        {renderSegmentLegend(activeTopic.segments)}
      </div>

      <div className="drill-path" aria-label="目前細究路徑" style={{ margin: '10px 0' }}>
        <span>{activeTopic.label}</span>
        <b>›</b>
        <span>{selectedRegionRecord?.geography || '未選縣市'}</span>
        <b>›</b>
        <span>{selectedMetricRecord?.label || '未選案類'}</span>
      </div>

      <div className="mini-stat-grid drill-stats">
        <div className="mini-stat">
          <span>{scopeLabel}主題案量</span>
          <strong>{selectedRegionRecord ? fmt.format(selectedRegionRecord.total) : '0'} 件</strong>
          <small>
            {selectedRegionRecord?.isNational
              ? '全部縣市合計'
              : `占本主題 ${selectedRegionRecord.share_pct || '0'}%`}
          </small>
        </div>
        <div className="mini-stat">
          <span>{scopeLabel} 年增率 (YoY)</span>
          <strong className={deltaClass(selectedRegionRecord?.yoy_pct)}>
            {formatPct(selectedRegionRecord?.yoy_pct)}
          </strong>
          <small>與去年同月同資料範圍比較</small>
        </div>
        <div className="mini-stat">
          <span>{scopeLabel}選定案類</span>
          <strong>{fmt.format(countyMetricCount)} 件</strong>
          <small>{selectedMetricRecord ? selectedMetricRecord.label : '未選案類'}</small>
        </div>
        <div className="mini-stat">
          <span>全國選定案類</span>
          <strong>{fmt.format(nationalMetricCount)} 件</strong>
          <small>官方刑事案件發生件數</small>
        </div>
        <div className="mini-stat">
          <span>{scopeLabel}案類占比</span>
          <strong>
            {selectedRegionRecord?.total
              ? ((countyMetricCount / selectedRegionRecord.total) * 100).toFixed(1)
              : '0.0'}%
          </strong>
          <small>占目前範圍本主題</small>
        </div>
      </div>

      <div className="drill-columns" style={{ marginTop: '12px' }}>
        <div>
          <span className="subhead">
            {selectedRegionRecord?.isNational ? '全國案類構成' : '該縣市案類構成'}
          </span>
          <div className="stacked-track national">
            {renderStackedBar(selectedRegionRecord?.segments, selectedRegionRecord?.total || 0)}
          </div>
          <div className="segment-legend" style={{ marginTop: '8px' }}>
            {orderedSegments(selectedRegionRecord?.segments).map((segment, index) => (
              <button
                key={index}
                type="button"
                className={`segment-key ${segment.metric === selectedMetricRecord?.metric ? 'is-active' : ''}`}
                onClick={() => setActiveMetric(segment.metric)}
              >
                <i style={{ backgroundColor: safeColor(segment.color) }}></i>
                <span>{segment.label}</span>
                <strong>{fmt.format(segment.count)}</strong>
              </button>
            ))}
          </div>
        </div>
        <div>
          <span className="subhead">此案類前六縣市與其他縣市</span>
          <ul className="rank-list">
            {countyRankRows.map((row, index) => (
              <li key={index} className={row.isOther ? 'is-other' : ''}>
                <span>{row.geography}</span>
                <strong>{fmt.format(row.count)} 件</strong>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <p className="method-note" style={{ marginTop: '12px' }}>{drillScopeNote}</p>
      <p className="method-note">目前為件數細究，尚未除以人口、戶數或日數；縣市比較應避免直接等同於風險排名。</p>
    </>
  );
}
