'use client';

import React from 'react';

const fmt = new Intl.NumberFormat('zh-TW');
const allRegionsLabel = '全部縣市';

const segmentOtherRank = (segment) => {
  const metric = String(segment?.metric || '');
  const label = String(segment?.label || '');
  if (metric === '__other__' || label === '其他案件') return 2;
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

export default function RegionRank({
  activeTopic,
  activeRegion,
  setActiveRegion,
  activeMetric,
  setActiveMetric
}) {
  if (!activeTopic) return null;

  const total = Number(activeTopic.total || 0);
  const segments = activeTopic.segments || [];
  const regionBreakdowns = activeTopic.region_breakdowns?.length
    ? activeTopic.region_breakdowns
    : (activeTopic.top_regions || []);

  // National region record
  const nationalRecord = {
    geography: allRegionsLabel,
    total: total,
    share_pct: 100,
    previous_year_total: activeTopic.previous_year_total,
    yoy_pct: activeTopic.yoy_pct,
    segments: orderedSegments(segments),
    isNational: true
  };

  const allRegions = [nationalRecord, ...regionBreakdowns];

  // Top 6 counties for special municipalities display
  const displayedRegions = [nationalRecord, ...regionBreakdowns.slice(0, 6)];

  const renderStackedBar = (itemSegments, itemTotal) => {
    const visible = orderedSegments(itemSegments);
    if (!visible.length || itemTotal <= 0) {
      return <span className="stacked-empty">無資料</span>;
    }
    return visible.map((segment, index) => {
      const segmentWidth = Math.max((Number(segment.count) / itemTotal) * 100, 0.8);
      const title = `${segment.label}: ${fmt.format(segment.count)} 件 (${segment.share_pct || Math.round((segment.count / itemTotal) * 100)}%)`;
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

  const handleRegionClick = (geography) => {
    if (activeRegion === geography) {
      setActiveRegion(null); // Toggle off
    } else {
      setActiveRegion(geography);
    }
  };

  const handleMetricClick = (metric) => {
    if (activeMetric === metric) {
      setActiveMetric(null); // Toggle off
    } else {
      setActiveMetric(metric);
    }
  };

  const formatPct = (value) => {
    if (value === null || value === undefined) return '無資料';
    const num = Number(value);
    return `${num > 0 ? '+' : ''}${num.toFixed(1)}%`;
  };

  return (
    <div className="stack-section">
      <div className="stack-heading">
        <span>全國案件構成比例</span>
        <small>點擊下方案件標籤可篩選統計範圍</small>
      </div>

      <div className="stacked-track national" aria-label="全國案件構成">
        {renderStackedBar(segments, total)}
      </div>

      <div className="segment-legend" id="topic-legend">
        {orderedSegments(segments).map((segment, index) => (
          <button
            key={index}
            type="button"
            className={`segment-key ${segment.metric === activeMetric ? 'is-active' : ''}`}
            onClick={() => handleMetricClick(segment.metric)}
          >
            <i style={{ backgroundColor: safeColor(segment.color) }}></i>
            <span>{segment.label}</span>
            <strong>{fmt.format(segment.count)}</strong>
          </button>
        ))}
      </div>

      <div className="stack-heading" style={{ marginTop: '12px' }}>
        <span>全部縣市與前六縣市</span>
        <small>包含全國總計與前六大主要縣市</small>
      </div>

      <div className="topic-region-list" id="topic-regions">
        {displayedRegions.map((row, index) => (
          <button
            key={index}
            type="button"
            className={`region-row ${row.geography === activeRegion ? 'is-active' : ''} ${row.isNational ? 'is-national' : ''}`}
            onClick={() => handleRegionClick(row.geography)}
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
            <div className="stacked-track" aria-label={`${row.geography} ${activeTopic.label}案件構成`}>
              {renderStackedBar(row.segments, row.total)}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
