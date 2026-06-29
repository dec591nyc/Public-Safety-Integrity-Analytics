'use client';

import React from 'react';
import {
  ResponsiveContainer,
  LineChart as RechartLine,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip
} from 'recharts';

export default function LineChart({ data = [], compact = false }) {
  const trendData = data.slice(-12);

  if (!trendData || trendData.length === 0) {
    return (
      <div className={`chart-empty ${compact ? 'compact' : ''}`}>
        <span>無可用的趨勢數據</span>
      </div>
    );
  }

  // Format month text: 202604 -> 04月 or 2026/04
  const formatXAxis = (tickItem) => {
    if (!tickItem) return '';
    const m = String(tickItem);
    if (m.length === 6) {
      return `${m.substring(4, 6)}月`;
    }
    return m;
  };

  const CustomTooltip = ({ active, payload, label }) => {
    if (active && payload && payload.length) {
      const val = payload[0].value;
      const formattedMonth = label && label.length === 6
        ? `${label.substring(0, 4)}年${parseInt(label.substring(4, 6), 10)}月`
        : label;
      return (
        <div style={{
          backgroundColor: 'rgba(9, 26, 51, 0.95)',
          border: '1px solid #d97706',
          padding: '8px 12px',
          borderRadius: '4px',
          color: '#ffffff',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.15)',
          fontFamily: 'sans-serif'
        }}>
          <p style={{ margin: 0, fontSize: '12px', opacity: 0.8 }}>{formattedMonth}</p>
          <p style={{ margin: '4px 0 0 0', fontSize: '15px', fontWeight: 'bold', color: '#fbbf24' }}>
            {new Intl.NumberFormat('zh-TW').format(val)} 件
          </p>
        </div>
      );
    }
    return null;
  };

  return (
    <div className={`line-chart ${compact ? 'compact' : ''}`} style={{ width: '100%', height: compact ? '200px' : '260px' }}>
      <ResponsiveContainer width="100%" height="100%">
        <RechartLine
          data={trendData}
          margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="#e0e6dd" vertical={false} />
          <XAxis
            dataKey="month"
            tickFormatter={formatXAxis}
            tick={{ fill: '#6b766e', fontSize: 11 }}
            axisLine={{ stroke: '#c8c8bd' }}
            tickLine={{ stroke: '#c8c8bd' }}
          />
          <YAxis
            tick={{ fill: '#6b766e', fontSize: 11 }}
            axisLine={{ stroke: '#c8c8bd' }}
            tickLine={{ stroke: '#c8c8bd' }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Line
            type="monotone"
            dataKey="count"
            stroke="#0f294a"
            strokeWidth={3}
            dot={{ r: 4, stroke: '#0f294a', strokeWidth: 2, fill: '#ffffff' }}
            activeDot={{ r: 6, stroke: '#d97706', strokeWidth: 2, fill: '#ffffff' }}
          />
        </RechartLine>
      </ResponsiveContainer>
    </div>
  );
}
