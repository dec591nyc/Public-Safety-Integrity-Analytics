'use client';

import React from 'react';

export default function Header({ totalCases, sourceMonth }) {
  const formatMonth = (m) => {
    if (!m) return '';
    if (m.endsWith('_annual')) {
      const year = m.split('_')[0];
      if (year === '2026') {
        return `${year} 年累計`;
      }
      return `${year} 完整年度`;
    }
    const y = m.substring(0, 4);
    const mm = m.substring(4, 6);
    return `${y} 年 ${parseInt(mm, 10)} 月`;
  };

  const formattedCases = totalCases ? new Intl.NumberFormat('zh-TW').format(totalCases) : '0';

  return (
    <header className="app-header">
      <div className="brand-block">
        <div className="eyebrow">NATIONAL / REGIONAL PUBLIC SAFETY</div>
        <h1>地方治安主題統計與趨勢</h1>
        <p className="subtitle">內政部受理案件統計數據指標分析</p>
      </div>
      <div className="status-group">
        <div className="status-dot"></div>
        <span>與官方 API 同步完成</span>
        <div className="status-divider"></div>
        <span id="header-record-count">
          {sourceMonth ? `${formatMonth(sourceMonth)} · ${formattedCases} 件` : '載入中'}
        </span>
      </div>
    </header>
  );
}
