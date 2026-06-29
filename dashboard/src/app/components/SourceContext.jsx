'use client';

import React from 'react';

export default function SourceContext({ summary }) {
  const quality = summary?.quality || {};

  return (
    <div className="panel" data-view-panel="method">
      <div className="panel-head">
        <div>
          <h2>資料取得與更新機制說明</h2>
          <p>說明平台治安統計數據的來源範圍、更新自動化管道及完整性檢驗規則</p>
        </div>
      </div>

      <div className="source-context">
        <dl>
          <div>
            <dt>官方資料來源</dt>
            <dd>
              內政部警政署 - 警政統計月報之「刑事案件發生件數」數據集（代號 9603）。
            </dd>
          </div>
          <div>
            <dt>資料更新週期</dt>
            <dd>
              警政署固定於每月中旬（約 15~18 號）發布上一個月份的完整統計。本平台支援即時自動化同步。
            </dd>
          </div>
          <div>
            <dt>案件範疇說明</dt>
            <dd>
              <strong style={{ color: 'var(--danger)' }}>特別澄清</strong>：本平台所呈現之數據均為警政機關<strong>「受理並登記之發生件數」</strong>（Incident Occurrence/Reporting count）。
              這代表案件<strong>「已由警察受理登錄」</strong>，但並不等同於檢察官起訴或法院判決成立罪刑之最終人數。
            </dd>
          </div>
          <div>
            <dt>自動化管線 (n8n)</dt>
            <dd>
              平台串接 <strong>n8n 工作流自動化系統</strong> 實現無人值守運維：
              <ul style={{ margin: '6px 0 0', paddingLeft: '20px', lineHeight: '1.6' }}>
                <li><strong>自動定時檢測</strong>：n8n 透過 Cron 觸發器每逢發布期定時向內政部統計網送出 HTTP Request 檢查新 CSV 是否已發布。</li>
                <li><strong>指令調度執行</strong>：確認發布後，n8n 調度執行本地/雲端之 <code>python scripts/run_daily_update.py</code> 執行數據抓取與清洗。</li>
                <li><strong>Supabase 數據寫入</strong>：Python 腳本將乾淨的資料直接 insert 到雲端 <strong>Supabase (PostgreSQL)</strong> 中，並自動更新預編譯分析結果。</li>
                <li><strong>前端快取重建 (ISR)</strong>：數據寫入完畢後，n8n 發送 Webhook 請求 Next.js 前端，觸發 On-demand Revalidation 即時刷新快取，免去人工重部署。</li>
              </ul>
            </dd>
          </div>
          <div>
            <dt>本地處理腳本</dt>
            <dd>
              <ul>
                <li><code>scripts/run_daily_update.py</code>：主爬蟲，下載 CSV 進行欄位對齊、計算檢驗和並寫入資料庫。</li>
                <li><code>scripts/generate_static_json.py</code>：預計算分析核心，計算月趨勢、六都佔比與 YoY 差額，並將 JSON 以二進位 blob 形式上傳至資料庫，實現 API 的極速回應。</li>
              </ul>
            </dd>
          </div>
          <div className="source-wide">
            <dt>資料完整性檢驗規則 (Data Integrity Controls)</dt>
            <dd>
              <p>平台內建防呆與審計檢驗機制，確保導入的官方原始數據正確無誤，本月檢驗狀態如下：</p>
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '8px', fontSize: '12px' }}>
                <thead>
                  <tr style={{ background: 'var(--surface-muted)', borderBottom: '1px solid var(--line)' }}>
                    <th style={{ padding: '6px', textAlign: 'left' }}>檢驗指標</th>
                    <th style={{ padding: '6px', textAlign: 'left' }}>檢驗邏輯</th>
                    <th style={{ padding: '6px', textAlign: 'right' }}>本月檢驗值</th>
                  </tr>
                </thead>
                <tbody>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '6px' }}>原始列數 (Raw Rows)</td>
                    <td style={{ padding: '6px' }}>CSV 載入之行政區與類別乘積紀錄數</td>
                    <td style={{ padding: '6px', textAlign: 'right', fontFamily: 'monospace' }}>{quality.raw_rows || 0} 行</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '6px' }}>對齊案類數 (Metrics)</td>
                    <td style={{ padding: '6px' }}>成功匹配至 ICCS 分析架構的案類總數</td>
                    <td style={{ padding: '6px', textAlign: 'right', fontFamily: 'monospace' }}>{quality.metric_count || 0} 類</td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '6px' }}>勾稽校對差額 (Reconciliation Delta)</td>
                    <td style={{ padding: '6px' }}>「全國總計」減去「各細項類別加總」的差額，應為 0</td>
                    <td style={{ padding: '6px', textAlign: 'right', color: quality.total_reconciliation_delta === 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 'bold', fontFamily: 'monospace' }}>
                      {quality.total_reconciliation_delta || 0} 件
                    </td>
                  </tr>
                  <tr style={{ borderBottom: '1px solid var(--line)' }}>
                    <td style={{ padding: '6px' }}>勾稽校對狀態</td>
                    <td style={{ padding: '6px' }}>校對結果是否相符</td>
                    <td style={{ padding: '6px', textAlign: 'right', color: quality.total_reconciliation_delta === 0 ? 'var(--success)' : 'var(--danger)', fontWeight: 'bold' }}>
                      {quality.total_reconciliation_delta === 0 ? '✓ 通過 (一致)' : '✗ 未通過 (有差額)'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
