'use client';

import React, { useState } from 'react';

export default function Feedback() {
  const [toastMessage, setToastMessage] = useState('');
  const [showToast, setShowToast] = useState(false);

  const triggerToast = (msg) => {
    setToastMessage(msg);
    setShowToast(true);
    setTimeout(() => setShowToast(false), 3200);
  };

  const handleOpenSource = () => {
    triggerToast('正在轉跳至警政署官方統計網...');
    setTimeout(() => {
      window.open('https://statis.moi.gov.tw/micst/webMain.aspx', '_blank', 'noreferrer');
    }, 800);
  };

  return (
    <div className="panel feedback-panel" data-view-panel="feedback">
      <div className="panel-head">
        <div>
          <h2>意見回饋與聯絡資訊</h2>
          <p>對本治安統計主題視覺化模組有任何改進建議？歡迎與我聯絡</p>
        </div>
      </div>
      <div className="feedback-layout">
        <div className="feedback-block">
          <p style={{ margin: 0, fontSize: '13px', color: 'var(--muted-ink)' }}>
            此平台建立旨在協助民代、媒體輿論及社會大眾可以直觀了解社會治安狀況，尤其育有兒童之家庭可以對社會有高度的預防準備。歡迎提供 any 視覺化改善建議。
          </p>
          <div className="feedback-actions" style={{ marginTop: '12px' }}>
            <button type="button" className="source-button" onClick={handleOpenSource} style={{ display: 'inline-flex', alignItems: 'center' }}>
              <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" style={{ marginRight: '6px' }}><path d="M13.5 1a1.5 1.5 0 0 1 1.5 1.5v11A1.5 1.5 0 0 1 13.5 15h-11A1.5 1.5 0 0 1 1 13.5v-11A1.5 1.5 0 0 1 2.5 1h11zm-11 1a.5.5 0 0 0-.5.5v11a.5.5 0 0 0 .5.5h11a.5.5 0 0 0 .5-.5v-11a.5.5 0 0 0-.5-.5h-11z" /><path d="M4 3h8v1H4V3zm0 3h8v1H4V6zm0 3h8v1H4V9z" /></svg>
              內政部開放統計數據資料庫
            </button>
            <a className="source-button github-button" href="https://github.com/dec591nyc/Public-Safety-Integrity-Analytics/issues" target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center' }}>
              <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" style={{ marginRight: '6px' }}><path d="M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3z" /><path fillRule="evenodd" d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zM1.5 8a6.5 6.5 0 1 1 13 0 6.5 6.5 0 0 1-13 0z" /></svg>
              提出 Issue
            </a>
            <a className="source-button" href="https://github.com/dec591nyc/Public-Safety-Integrity-Analytics" target="_blank" rel="noreferrer" style={{ display: 'inline-flex', alignItems: 'center' }}>
              <svg viewBox="0 0 16 16" width="14" height="14" fill="currentColor" style={{ marginRight: '6px' }}><path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.35 3.1 1.07-.01.7-.01 1.29-.01 1.48 0 .21-.15.47-.55.38A8.013 8.013 0 0 1 0 8c0-4.42 3.58-8 8-8z" /></svg>
              查看 GitHub
            </a>
          </div>
        </div>
        <div className="feedback-block">
          <dl className="feedback-paths">
            <div>
              <dt>平台維護單位</dt>
              <dd>17 君</dd>
            </div>
            <div>
              <dt>更新週期</dt>
              <dd>每月定期</dd>
            </div>
            <div>
              <dt>專案版本</dt>
              <dd>v1.0.0</dd>
            </div>
          </dl>
        </div>
      </div>
      {showToast && (
        <div className="toast is-visible">
          {toastMessage}
        </div>
      )}
    </div>
  );
}
