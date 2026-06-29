# 台灣地方治安統計數據分析平台 

(Taiwan Local Public Safety Statistics & Data Integrity Audit Platform)

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14.2-black?style=for-the-badge&logo=next.js" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-18-blue?style=for-the-badge&logo=react" alt="React" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License" />
</p>

💡 **本平台是結合 Next.js 數據儀表板與 Python 自動化數據管道的治安統計分析平台，並採用 n8n 於內政部刑事案件數據集（代號 9603）實現自動化資料撈取、校對與完整度審計，研判各類犯罪的月度趨勢、六都分布及 YoY 增減變化。**

---

## 🎯 專案核心定位與特色

本專案專注於提供**具備高可信度的官方刑事統計儀表板**。本平台核心特色如下：

1. **官方案件範疇定位**：
   呈現數據均為警政機關「受理並登記之刑事案件發生件數」。資料來源為內政部統計月報，保障數據公正性與一致性。
2. **內建數據審計校對（Data Integrity Controls）**：
   管線內建自動化對帳機制，檢驗**「全國刑事發生總計」**是否等於**「各行政區及案類統計加總」**。若發現不一致（校對差額不為 0），則觸發警告。
3. **高可用雙模架構 (Dual-Mode Design)**：
   * **資料庫主動模式 (Database Mode)**：連接到 Supabase PostgreSQL 資料庫，提供最即時的數據載入。
   * **靜態快取備份模式 (Static API Fallback)**：自動降級至讀取本地編譯的 `public/static_api/*.json` 檔案，確保零成本部署時依然 100% 正常運作。
4. **無本機儲存限制雲端模式 (Zero-Persistence Cloud Mode)**：
   因應 Serverless、Docker、n8n 等無寫入權限或無狀態託管環境，系統支援全記憶體運作。資料可直接由爬蟲下載並推送到雲端 Supabase，本機無須留存任何 SQLite 資料庫或 JSON 檔案。

---

## 🏗️ 系統架構與資料流 (Architecture & Data Flow)

```mermaid
flowchart TD
    subgraph "數據源 (Data Source)"
        A[內政部統計網\n刑事統計數據集 9603]
    end

    subgraph "自動化管線 (n8n / Python)"
        B["run_daily_update.py\n(下載、清洗、寫入 Supabase)"]
        C["generate_static_json.py\n(臨時 SQLite 鏡像計算 & 編譯)"]
        A -->|CSV 數據| B
        B -->|更新 Postgres 表| D["(Supabase 雲端資料庫)"]
        D -->|拉取計算| C
        C -->|自動上傳 JSONB| D
    end

    subgraph "前端儀表板 (Next.js App)"
        F[Next.js API 路由] -->|1. 優先查詢 JSONB| D
        F -->|2. 資料庫不可用時自動降級| G[public/static_api/*.json]
        G --> H[React 前端 / Recharts 渲染]
        D -->|提供最新資料| H
    end

    subgraph "純靜態版 (GitHub Pages SPA)"
        C -->|非雲端模式時複製| I[docs/static_api/*.json]
        J[Vanilla JS app.js] -->|讀取| I
    end
```

---

## 📂 目錄結構與模組說明

```text
├── dashboard/                   # Next.js 數據儀表板 (本專案核心)
│   ├── src/app/                 # App Router (首頁、API 路由、折線與堆疊圖表)
│   ├── public/static_api/       # 靜態降級 API 快取目錄 (無資料庫模式的 fallback)
│   └── next.config.mjs          # Next.js 配置與排除 Webpack 打包
├── scripts/                     # Python 數據管道與編譯工具
│   ├── run_daily_update.py      # [主更新] 下載官方 CSV，對齊並寫入 SQLite/Postgres
│   ├── generate_static_json.py  # [主編譯] 將資料編譯為 JSON，並自動上傳至 Supabase
│   ├── upload_to_supabase.py    # [上傳模組] 將彙整 JSON 寫入 Supabase 的 official_summaries
│   └── serve_review_dashboard.py# 舊版本地 Python API 伺服器 (供 Vanilla 測試)
├── docs/                        # 用於 GitHub Pages 託管的 Vanilla JS 靜態版
├── sql/                         # 資料庫結構描述檔 (SQLite / Postgres)
└── README.md                    # 本說明文件
```

---

## 🚀 部署與本地開發

### 1. 雲端資料庫模式（Supabase / PostgreSQL）
1. 進入 Supabase 控制台的 **SQL Editor**，執行 `sql/schema_postgres.sql` 的內容以初始化資料表結構。
2. 取得您的 Supabase PostgreSQL 連線 URL。
3. 在終端機中設定環境變數：
   ```powershell
   $env:PUBLIC_SAFETY_DATABASE_URL="postgresql://postgres:[PASSWORD]@db.[PROJECT].supabase.co:5432/postgres"
   ```
4. 在 Vercel 部署 Next.js 儀表板時，亦請在 Vercel 後台填寫此環境變數。

### 2. 資料庫更新與編譯
```bash
# 安裝 Python 依賴
pip install psycopg2-binary

# 1. 抓取最新月份官方資料並寫入資料庫
py scripts/run_daily_update.py

# 2. 自動編譯 JSON 彙整檔並直接上傳至 Supabase（全自動化，免去手動上傳）
py scripts/generate_static_json.py
```

### 3. 本地啟動前端開發服務
```bash
cd dashboard
npm install
npm run dev
```
啟動後訪問 `http://localhost:3000` 即可預覽。

---

## 🧠 專案開發收穫 (Key Takeaways)

透過專案的重構與優化，實踐了現代數據工程與前端架構中的幾個重要解決方案：

1. **嚴謹的「對帳與審計」數據工程思維**
   處理政府開放數據（Open Data）時，欄位對齊、缺漏與四捨五入往往會造成統計誤差。在 Python 管道中加入了對帳檢驗（Reconciliation Check），利用「全國總計」與「地方行政區加總」的差值對照，實現了數據落地的檢驗保證，在源頭杜絕了髒數據污染。
2. **適應唯讀環境（Read-Only System）的無本機儲存設計**
   面對 Serverless 與自動化排程器（如 n8n）可能沒有本地硬碟寫入權限的問題，實現了「以記憶體和臨時空間鏡像運算」的策略。藉由 Python 建立臨時 SQLite 進行高速 SQL 計算、完成後上傳 Supabase 並自動清理本機磁碟，確保了系統可以在任何限制環境中 100% 正常運行。
3. **優雅的雙模容錯架構（Active-Fallback Design）**
   Next.js 後端 API 設計了雙重降級保護。優先以高響應速度的 Supabase PostgreSQL 提供服務，若資料庫發生異常或為零成本託管，會自動無縫切換至本地的靜態 JSON API 快取。前端 React 與 Vanilla JS 能在無感的情況下繼續渲染，大幅強化了系統的韌性。
