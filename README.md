# 台灣地方治安統計數據分析平台 

(Taiwan Local Public Safety Statistics & Data Integrity Audit Platform)

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14.2-black?style=for-the-badge&logo=next.js" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-18-blue?style=for-the-badge&logo=react" alt="React" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License" />
</p>

💡 **本平台是結合 Next.js 數據儀表板與 Python 自動化數據流水線的治安統計分析平台，並使用 n8n 於每月自動抓取內政部刑事案件數據集（代號 9603）進行校對與完整度審計，提供民眾一個方便了解全國所有縣市各類犯罪月度趨勢、六都分布及 YoY 增減變化的視覺化儀表板。**

---

## 🎯 專案核心定位與特色

本專案旨在提供**具備高可信度的官方刑事案件統計儀表板**。本平台核心特色如下：

1. **官方案件範疇定位**：
   呈現數據均為警政機關「受理並登記之刑事案件發生件數」。資料來源為內政部統計月報，保障數據公正性與一致性。
2. **內建數據審計校對（Data Integrity Controls）**：
   數據流水線內建自動化對帳機制，檢驗**「全國刑事發生總計」**是否等於**「各行政區及案件統計加總」**。若發現不一致（校對差額不為 0），則觸發警告。
3. **官網資料庫主動模式 (Database Mode)**：
   連接到 Supabase PostgreSQL 資料庫，提供最即時的數據載入與指標查詢。
4. **離線開發 SQLite 備援模式 (Offline SQLite Fallback)**：
   若無設定 Supabase 連線（系統會自動讀取專案根目錄的 `.env` 檔案以取得連線字串，若無此檔則自動降級），系統會自動切換至本地 `data/local/public_safety.sqlite` 中進行資料庫操作與編譯測試。
5. **無本機儲存限制雲端模式 (Zero-Persistence Cloud Mode)**：
   因應 Serverless、Docker、n8n 等無寫入權限或無狀態託管環境，系統支援全記憶體運作與 direct DB sync。資料由 Python ETL pipeline 直接計算並推送到雲端 Supabase 的 `crime_summary_reports` 與 `crime_summary_payload_cache` 資料表，本機無須留存任何 JSON 檔案，保持 Git 倉庫乾淨輕量。

---

## 🏗️ 系統架構與資料流 (Architecture & Data Flow)

```mermaid
flowchart TD
    subgraph "數據源 (Data Source)"
        A[內政部統計網\n刑事統計數據集 9603]
    end

    subgraph "自動化數據流水線 (n8n / Python ETL)"
        B["run_daily_update.py\n(下載、清洗、寫入 DB)"]
        C["sync_summary_reports.py\n(數據轉型、計算指標與主題包)"]
        A -->|CSV 數據| B
        B -->|官方原始統計數據| D["(Supabase 雲端資料庫 / SQLite)"]
        D -->|拉取並計算彙整指標| C
        C -->|上傳 summary 與 payload cache| D
    end

    subgraph "前端儀表板 (Next.js Web App)"
        F[Next.js API 路由] -->|查詢結構化指標| D
        D -->|提供最新數據| H[React 前端 / Recharts 渲染]
    end
```

---

## 📂 目錄結構與模組說明

```text
├── web/                         # Next.js 數據儀表板 (本專案核心)
│   ├── src/app/                 # App Router (首頁、API 路由、折線與堆疊圖表)
│   ├── src/utils/db.js          # 資料庫連線模組
│   └── package.json             # Next.js 專案依賴設定
├── scripts/                     # Python 數據流水線與編譯工具
│   ├── etl/                     # 結構化 ETL 套件 (核心處理邏輯)
│   │   ├── config.py            # 配置常數、犯罪案件對齊、顏色樣式
│   │   ├── db.py                # 跨資料庫連線 (SQLite & Postgres)
│   │   ├── extract.py           # 抓取並解析 MOI 刑事 CSV 檔
│   │   ├── transform.py         # 聚合月/年指標、YoY 計算、AI 趨勢研判
│   │   └── load.py              # 將彙整結果同步寫入 DB (crime_summary_reports)
│   ├── run_daily_update.py      # [主更新] 下載官方 CSV，對齊並寫入官方原始數據
│   ├── sync_summary_reports.py  # [主編譯] 全記憶體運行，計算指標並同步至 Supabase
│   └── metric_styles.py         # 同步治安指標樣式配置
├── sql/                         # 資料庫結構描述檔 (SQLite / Postgres)
├── ref/                         # 參考文件 (如裁判書開放 API 規格說明)
├── n8n/                         # 自動化排程部署與工作流配置 (Docker / JSON)
└── README.md                    # 本說明文件
```

---

## 🚀 部署與本地開發

### 1. 雲端資料庫模式（Supabase / PostgreSQL）
1. 進入 Supabase 控制台的 **SQL Editor**，執行 `sql/schema_postgres.sql` 的內容以初始化資料表結構。
2. 取得您的 Supabase PostgreSQL 連線 URL，寫入 `.env` 檔案或設為環境變數：
   ```env
   PUBLIC_SAFETY_DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres"
   ```
3. 在部署 Next.js 網頁時，亦請在託管平台（如 Vercel）後台填寫此環境變數。

### 2. 資料庫更新與編譯
```bash
# 安裝 Python 依賴
pip install psycopg2-binary requests

# 1. 抓取最新月份官方資料並寫入資料庫
py scripts/run_daily_update.py --skip-existing --min-release-day 8

# 2. 自動編譯指標並直接上傳至 Supabase
py scripts/sync_summary_reports.py --latest-only
```

### 3. 本地啟動前端開發服務
```bash
cd web
npm install
npm run dev
```
啟動後訪問 `http://localhost:3000` 即可預覽。

### 4. n8n 自動化排程與歷史回填 (n8n Scheduling & Backfill)
本專案提供 `n8n/PSJJV_n8n.json` 作為自動化資料更新的工作流配置：
1. **每月定時更新**：預設在每月 25 號自動抓取最新月份（當月及上月）的警政署資料，並編譯更新 Supabase。
2. **手動歷史回填 (One-time Backfill)**：由於新部署的 Supabase 資料庫是空表，網頁可能無法顯示過去年份的下拉選單與年度比較。您可透過 n8n 執行一次性回填：
   * 在 n8n 中將 `Execute Command` 節點的指令暫時修改為：
     ```bash
     cd /home/node/public-safety-dashboard && python3 scripts/run_daily_update.py --backfill 201801 && python3 scripts/sync_summary_reports.py --full-refresh
     ```
     *(可將 `201801` 替換為您需要的起始年份月份)*
   * 若只是補年度報表或年度比較欄位，不需要重算所有月報，可改用：
     ```bash
     cd /home/node/public-safety-dashboard && python3 scripts/sync_summary_reports.py --annual-only --from-year 2018 --to-year 2026
     ```
     批次重算會自動先將官方統計載入記憶體，減少對 Supabase 的重複查詢；只有診斷或比對舊流程時才需要加上 `--no-preload`。
   * 點擊 **Execute Node** 執行一次，即可完整下載並計算歷史統計數據寫入 Supabase。
   * 執行完畢後，記得將指令**改回預設**（移除 `--backfill` 參數，保留 `--skip-existing --min-release-day 8`），以保持每月的增量輕量更新。

---

## 🧠 專案開發收穫與小小的心路歷程 (Key Takeaways & Developer Journey)

透過專案的不斷重構與優化，實踐數據工程與前端架構中的幾個重要決策：

1. **尋找可信數據的起點與轉變 (The Pivot to Credible Data)**
   在開發初期，我一直在尋找能夠忠實反映地方治安狀況且具備公信力的數據源，反覆思索如何設計一個不僅自己關心、其他民眾也同樣關注的統計指標。最初嘗試從司法裁判書（判決書）中抓取與提取統計資料，但因擔心觸犯個人隱私法條，促使做出架構調整：改以內政部的官方開放數據集作為核心數據源。藉由直接讀取官方統計，成功建立起一個即時性、涵蓋全國縣市的治安指標儀表板。
2. **嚴謹的「數據完整性校對」防錯機制 (Rigorous Data Integrity Verification)**
   處理政府開放數據（Open Data）時，常會遇到欄位對齊不一、數據缺漏或四捨五入所造成的統計誤差。為了建立民眾能放心信賴的數據，在數據流水線中加入了自動化的「全國加總校驗機制」。系統會即時檢驗並比對「官方發布的全國刑事案量總數」是否完全等於「各地方縣市所有細分案類的加總數」。若兩者存在任何差額，便會即時觸發除錯警報，保證展示數據的百分之百嚴謹與一致，確保前端呈現的每一筆數據都經過完整性審計。
3. **本地開發與雲端部署的環境自動適應 (Environment Auto-Adaptation for Local and Cloud)**
   建立起了一套能自適應執行環境的混合資料庫架構。當系統偵測到雲端連線字串時，會自動將更新結果同步寫入 Supabase 雲端資料庫供網頁即時查詢；在無網路或離線測試時，則自動切換為本地 SQLite 進行儲存。這讓 Next.js 前端網頁與 Python 計算管線不再需要硬性綁定雲端環境，在保障開發敏捷度的同時，也達成了正式環境 100% 雲端驅動的流暢維護體驗。
