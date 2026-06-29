# 公眾治安與司法正義檢視網 (Public Safety & Judicial Justice Analytics)

<p align="center">
  <img src="https://img.shields.io/badge/Next.js-14.2-black?style=for-the-badge&logo=next.js" alt="Next.js" />
  <img src="https://img.shields.io/badge/React-18-blue?style=for-the-badge&logo=react" alt="React" />
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E?style=for-the-badge&logo=supabase&logoColor=white" alt="Supabase" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="MIT License" />
</p>

💡 **一個結合 Next.js 現代化儀表板與 Python 自動化數據管道的治安統計主題視覺化平台。以數據為基石，探索台灣治安趨勢、案類佔比與縣市分布特徵。**

---

## 🎯 專案核心定位

本專案非重建或儲存海量的裁判書全文庫，而是透過輕量、高效的自動化數據管道（Data Pipeline），提取並對照兩大核心維度：
1. **司法裁判與案類特徵數據**：透過 Python 解析司法院刑事判決元數據，統計各類犯罪（如詐欺、人身安全等）的月份趨勢、縣市分布、增減率（YoY）與佔比關係。
2. **高可用雙模架構 (Dual-Mode Design)**：
   * **資料庫主動模式 (Database Mode)**：連接到 Supabase PostgreSQL 資料庫，即時載入最新月度與年度統計。
   * **靜態備份模式 (Static API Fallback)**：當資料庫連線中斷或為零成本託管時，系統會自動降級讀取本地預先編譯的 `public/static_api/*.json` 靜態快取，確保服務 100% 不中斷。

---

## 🏗️ 系統架構與資料流 (Architecture & Data Flow)

```mermaid
flowchart TD
    subgraph 數據獲取與處理 (Data Pipeline)
        A[司法院公開刑事數據 / API] -->|generate_static_json.py| B[編譯輸出 static_api JSON]
        B -->|upload_to_supabase.py| C[(Supabase Postgres Database)]
    end

    subgraph 儀表板服務 (Next.js Dashboard)
        D[Next.js API Routes] -->|優先讀取| C
        D -->|連線失敗/缺省時自動降級| E[dashboard/public/static_api/*.json]
        E --> F[React 前端展示 / Recharts 渲染]
        C --> F
    end

    subgraph 靜態演示 (GitHub Pages SPA)
        B -->|同步複製| G[docs/static_api/*.json]
        H[Vanilla JS app.js] -->|直接載入| G
    end
```

---

## 🛠️ 目錄結構說明

```text
├── dashboard/                   # Next.js 14 現代化數據儀表板 (本專案核心)
│   ├── src/app/                 # App Router (首頁、API 路由、折線與堆疊圖表)
│   ├── public/static_api/       # 靜態降級 API 快取目錄 (由 Python 自動生成與同步)
│   └── next.config.mjs          # 排除原生 pg 套件 Webpack 打包配置
├── scripts/                     # Python 數據管道與編譯工具
│   ├── generate_static_json.py  # [最重要] 爬蟲數據編譯與導出 (已 bypass ICCS 提速)
│   ├── upload_to_supabase.py    # 同步 static_api 至 Supabase Database 腳本
│   └── serve_review_dashboard.py# 舊版本地 Python API 伺服器 (供 Vanilla 測試)
├── docs/                        # 用於 GitHub Pages 託管的 Vanilla JS 靜態版
├── sql/                         # 資料庫結構描述檔 (SQLite / Postgres)
└── README.md                    # 本說明文件
```

---

## 🚀 部署指南 (Deployment Guide)

### 第一步：Supabase 資料庫設定與資料遷移

1. **建立 Supabase 專案**：
   前往 [Supabase](https://supabase.com) 註冊並新建一個資料庫專案。
2. **匯入資料表結構**：
   進入 Supabase 後台的 **SQL Editor**，複製並執行 `sql/schema_postgres.sql` 的內容，或直接建立存放彙整資料的 `official_summaries` 表：
   ```sql
   CREATE TABLE IF NOT EXISTS official_summaries (
     source_month TEXT PRIMARY KEY,
     summary_json JSONB NOT NULL,
     updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
   );
   ```
3. **執行 Python 資料上傳**：
   在本地將資料庫連線字串設定至環境變數中，並執行遷移腳本將現有月份資料一次性同步至 Supabase：
   ```bash
   # 設定 Supabase 連線 URL
   $env:PUBLIC_SAFETY_DATABASE_URL="your_supabase_postgresql_connection_string"
   
   # 執行上傳
   python scripts/upload_to_supabase.py
   ```

---

### 第二步：部署 Next.js 儀表板至 Vercel

本專案完全支援 Vercel 一鍵部署：

1. **將專案推送到您的 GitHub 儲存庫**：
   請確保已將 `.env.local` 加入 `.gitignore` 中，**切勿將敏感私鑰推送到 GitHub**。
2. **在 Vercel 中匯入專案**：
   * 登入 Vercel 點選 **Add New > Project**，選取您的 GitHub 專案。
   * 將 Root Directory 設定為 `dashboard`。
3. **配置環境變數 (Environment Variables)**：
   在 Vercel 專案設定的 Environment Variables 中，新增以下變數：
   * **名稱**：`PUBLIC_SAFETY_DATABASE_URL`
   * **值**：您的 Supabase PostgreSQL 連線字串（例如 `postgresql://postgres:password@db.xxxx.supabase.co:5432/postgres`）。
4. **點擊 Deploy**：
   部署完成後即可獲得專屬的線上儀表板連結！

> [!NOTE]  
> **無資料庫託管模式**：如果您在 Vercel 上不設定 `PUBLIC_SAFETY_DATABASE_URL` 環境變數，Next.js 會自動啟用備用模式，直接讀取並提供 `dashboard/public/static_api/` 下的 JSON 快取檔案。這適合用於低負擔、零成本的展示網站。

---

### 第三步：靜態網頁託管至 GitHub Pages

本專案的 `docs` 目錄已預先同步了前端 Vanilla SPA 及完整的靜態快取資料。若您只想託管純靜態頁面：

1. 前往 GitHub 該專案儲存庫的 **Settings** 頁面。
2. 點選左欄 **Pages**。
3. 在 Build and deployment 中，將 Source 設定為 **Deploy from a branch**。
4. Branch 選擇 `main` (或您的主分支)，資料夾選取 **`/docs`** 點選 Save。
5. 數分鐘後即可透過 `https://<username>.github.io/<repo-name>/` 存取靜態版治安檢視網！

---

## 💻 本地開發指南 (Local Development)

### 1. 啟動 Next.js 數據儀表板
```bash
# 進入 dashboard 資料夾
cd dashboard

# 安裝 Node 依賴項目
npm install

# 啟動開發伺服器
npm run dev
```
啟動後訪問 `http://localhost:3000` 即可進行預覽與修改。

### 2. 重新編譯本地靜態快取
當資料庫有更新或需要生成全新快取檔時，請在專案根目錄下執行：
```bash
python scripts/generate_static_json.py
```
*腳本會自動將產出的 JSON 檔案同步到 `docs/static_api/` 及 `dashboard/public/static_api/` 中。*

---

## 📝 授權與宣告 (License & Disclaimer)

* 本專案開源授權採用 **MIT License**。
* 本專案僅供學術探討、個人職涯作品集展示與技術驗證使用。請勿將其產出的輿情聲量模擬或預算數據直接引用為司法不公或犯罪現狀之實體結論。
