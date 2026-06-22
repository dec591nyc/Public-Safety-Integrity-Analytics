# Public Safety & Integrity Analytics (公共安全與廉政司法數據對照平台)

💡 **以數據為基石，探索官方犯罪統計與公眾輿論聲量之間的維度偏差與聚焦關聯。**

🔗 [**Live Demo 網頁展示**](https://dec591nyc.github.io/Public-Safety-Integrity-Analytics/)

---

## 專案簡介 (Overview)

本專案是一個**數據整合與對照儀表板平台**。其宗旨非重建或儲存海量的裁判書全文倉儲，而是透過自動化數據管道（Data Pipeline），提取並對照兩大核心維度：

1. **官方統計數據 (Official Statistics)**：自動對接內政部警政統計單月刑事案件（資料集編號 9603），清洗、去重並以聯合國 ICCS 標準進行案類分類，並結合刑責嚴重度（Severity Score）權重計算「各縣市加權治安風險指標」。
2. **輿論聲量指標 (Public Opinion Metrics)**：以有限度且符合爬蟲規範（Robots.txt）之方式抓取社群論壇（如 PTT、Dcard）、新聞及司法評論之元數據，計算討論聲量與情緒標籤，呈現公眾對於各類型犯罪（如詐欺、貪污等）的關注趨勢。

藉由將兩者置於同一時間軸（如本機示範之 `2026/04`），平台能以量化圖表與對照矩陣，客觀呈現「高官方件數、低輿論關注」或「低官方件數、高輿論關注」之**關注度落差 (Attention Gaps)**。

---

## 系統架構與資料流 (Architecture & Data Flow)

本專案採用輕量、高性能且易於部署的技術架構：

*   **前端展示**：採用 Vanilla HTML / CSS / JavaScript 打造單頁應用程式 (SPA)，具備現代化高密度數據儀表板視覺風格、毛玻璃光影效果與全響應式設計。
*   **後端服務**：由 Python 提供資料存取 API，支援 SQLite 本地開發模式與 PostgreSQL / Supabase 雲端生產模式。
*   **數據排程**：可與 n8n 自動化整合，進行每月定時的官方統計下載與輿論聲量分析。

```mermaid
flowchart TD
    subgraph 數據源 Ingestion
        A[內政部警政統計 API / CSV] -->|ingest_official_statistics.py| C[(SQLite / PostgreSQL)]
        B[論壇 / 新聞輿情 metadata] -->|collect_opinion_metrics.py| C
        D[司法機關裁判書樣本文檔] -->|build_judgment_index.py| C
    end

    subgraph 後端 API 服務
        C --> E[serve_review_dashboard.py]
    end

    subgraph 前端展示 (SPA)
        E -->|API 數據傳輸| F[vanilla JS app.js]
        F --> G[官方統計 - ICCS 分類及風險排行]
        F --> H[輿論情報 - 情感分析與議題摘要]
        F --> I[數據對照 - 關注度差距矩陣]
        F --> J[裁判資料庫 - 案由搜尋與規則摘要]
    end

    subgraph 靜態 Live Demo 模式
        C -->|generate_static_json.py| K[static_api/*.json]
        K -->|自動降級加載| F
    end
```

---

## 技術亮點 (Technical Highlights)

1.  **聯合國 ICCS 案類分類與加權風險**
    將台灣警政繁複的案由對接至聯合國 ICCS（國際犯罪分類）框架，並為不同案件指派嚴重度權重分，計算出更具參考價值的「加權治安風險排行」，而非單純堆疊案件件數。
2.  **可追溯之規則式法律摘要 (Traceable Extractive Summary)**
    在裁判資料庫中，不使用隨機黑盒模型進行自由發揮，而是使用確定性演算法（Extractive Rule-based）篩選裁判書中的主文、關鍵句與案由關鍵字，產出附帶證據片段的精確摘要。
3.  **無後端靜態 Live Demo 降級方案**
    前端 `app.js` 具備自適應偵測機制。當專案部署於 GitHub Pages 等靜態託管平台、或本地後端伺服器未啟動時，會自動改為載入 `static_api/` 目錄中預先匯出的 JSON 資料，並在前端以**記憶體內（In-Memory）過濾與分頁技術**實現無縫的關鍵字檢索與頁面互動。

---

## 本地執行指南 (Local Setup Guide)

### 方式一：Windows 一鍵啟動 (推薦)

在專案根目錄下直接點擊執行：
```bat
run.bat
```
在隨後出現的選單中：
*   輸入 `1` 即可啟動本地 Web 伺服器並載入 SQLite 資料庫。
*   開啟瀏覽器訪問 `http://127.0.0.1:8765` 即可使用完整功能。
*   輸入 `2` 可手動啟動內政部統計抓取與輿情生成管道。

### 方式二：手動啟動

1.  **安裝依賴與初始化資料庫**
    專案主要使用 Python 3 標準庫。若需執行後端 API，可直接執行：
    ```bash
    # 初始化資料庫並抓取 2026/04 資料
    python scripts/run_daily_update.py --month 202604
    ```

2.  **開啟本地 Web Server**
    ```bash
    python scripts/serve_review_dashboard.py --db data/local/public_safety.sqlite
    ```
    伺服器啟動後，訪問 `http://127.0.0.1:8765`。

3.  **生成靜態 Demo 資料** (若欲進行靜態部署)
    ```bash
    python scripts/generate_static_json.py
    ```
    該指令會將資料庫中 202604 的官方統計、輿情及前 150 筆裁判明細匯出至 `web/static_api/` 中。

---

## 目錄結構 (Directory Structure)

```text
Public-Safety-Integrity-Analytics/
├── config/                      # 系統與案類權重配置
├── data/
│   └── local/                   # 本地 SQLite 資料庫 (public_safety.sqlite)
├── output/
│   └── official_statistics/     # 歷史下載的官方統計 JSON 快照
├── sql/
│   ├── schema_sqlite.sql        # SQLite 資料表結構
│   └── schema_postgres.sql      # PostgreSQL / Supabase 資料表結構
├── scripts/
│   ├── run_daily_update.py      # 統一數據排程抓取主腳本
│   ├── serve_review_dashboard.py# 本地 Python API 伺服器
│   ├── generate_static_json.py  # 匯出靜態展示 API 檔腳本
│   └── build_judgment_index.py  # 裁判書樣本索引建立腳本
├── web/                         # 前端 SPA 網頁資源
│   ├── static_api/              # 靜態降級 API JSON 目錄
│   ├── index.html               # 儀表板 HTML 頁面
│   ├── styles.css               # 數據密集儀表板 CSS
│   └── app.js                   # 前端路由與數據處理邏輯
├── run.bat                      # Windows 一鍵啟動腳本
└── README.md                    # 本說明文件
```

---

## 授權說明 (License)

本專案僅供學術探討、個人職涯作品集展示與技術驗證使用。請勿將其產出的輿情聲量模擬或預算數據直接引用為司法不公或犯罪現狀之實體結論。
