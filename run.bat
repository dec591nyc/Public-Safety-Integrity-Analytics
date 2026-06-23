@echo off
rem Project Launcher Batch File for Windows
setlocal enabledelayedexpansion

:menu
cls
echo ===================================================
echo   JusticeWatch: Public Safety & Integrity Tracker Launcher
echo ===================================================
echo.
echo Please select an action:
echo   [1] Start Review Dashboard (Web Server)
echo   [2] Run Unified Daily Ingestion (MOI, Opinions, Judicial Scraper)
echo   [3] [Legacy] Download Judgment Archives (Judicial Yuan Open Data)
echo   [4] [Legacy] Fetch Real-time Judgment Metadata in Parallel (API)
echo   [5] [Legacy] Build SQLite Index from raw JSON files
echo   [6] Exit
echo.
set /p opt="Enter choice (1-6): "

if "!opt!"=="1" (
    echo.
    echo Starting Review Dashboard...
    echo Access it at: http://127.0.0.1:8765
    python scripts\serve_review_dashboard.py --db data\local\public_safety.sqlite
    pause
    goto menu
)

if "!opt!"=="2" (
    echo.
    echo ===================================================
    echo   Run Unified Daily Update
    echo ===================================================
    echo.
    echo Please select an ingestion mode:
    echo   [A] Daily Incremental Update - Update current and previous month
    echo   [B] Historical Backfill - From a specific month to present
    echo   [C] Single Month Update - Update a specific month only
    echo.
    set /p subopt="Select option [A/B/C, default A]: "
    if /i "!subopt!"=="B" (
        set /p start_month="Enter start month for backfill [YYYYMM, e.g., 199301]: "
        if not "!start_month!"=="" (
            echo.
            echo Running statistics backfill since !start_month!...
            python scripts\run_daily_update.py --backfill !start_month!
        )
    ) else if /i "!subopt!"=="C" (
        set /p single_month="Enter month to update [YYYYMM, e.g., 202604]: "
        if not "!single_month!"=="" (
            echo.
            echo Running statistics update for !single_month!...
            python scripts\run_daily_update.py --month !single_month!
        )
    ) else (
        echo.
        echo Running default daily update...
        python scripts\run_daily_update.py
    )
    pause
    goto menu
)

if "!opt!"=="3" (
    echo.
    echo ===================================================
    echo   Download Judgment Archives - Judicial Yuan
    echo ===================================================
    echo.
    set /p start_yr="Enter start year Gregorian, e.g. 1996 [default 1996]: "
    if "!start_yr!"=="" set start_yr=1996
    
    set /p limit="Enter download limit - number of files, optional: "
    set limit_opt=
    if not "!limit!"=="" set limit_opt=--limit !limit!
    
    echo.
    echo [Session Authentication Cookie]
    echo   - Required to bypass WAF blocks for bulk downloads.
    echo   - If you have a cookie file, enter its path e.g. cookie.txt.
    echo   - If you do not have a cookie, press Enter to download public metadata.
    echo.
    set /p cookie_file="Enter path to cookie text file, optional: "
    set cookie_opt=
    if not "!cookie_file!"=="" set cookie_opt=--session-cookie !cookie_file!
    
    echo.
    echo Running downloader - Start year: !start_yr!...
    python scripts\sync_judgment_archives.py --start-year !start_yr! !limit_opt! !cookie_opt!
    pause
    goto menu
)

if "!opt!"=="4" (
    echo.
    echo ===================================================
    echo   Fetch Real-time Judgment Metadata via API
    echo ===================================================
    echo.
    set /p user="Enter Judicial Yuan API Username: "
    set /p password="Enter Judicial Yuan API Password: "
    
    set /p workers="Enter number of parallel workers [default 16]: "
    set workers_opt=
    if not "!workers!"=="" set workers_opt=--workers !workers!
    
    echo.
    echo Running API metadata downloader...
    python scripts\sync_judgment_api.py --user "!user!" --password "!password!" !workers_opt!
    pause
    goto menu
)

if "!opt!"=="5" (
    echo.
    set /p src_dir="Enter source directory containing Judicial JSON files: "
    set /p month="Enter month [YYYYMM]: "
    if "!src_dir!"=="" (
        echo Source directory cannot be empty.
        pause
        goto menu
    )
    if "!month!"=="" (
        echo Month cannot be empty.
        pause
        goto menu
    )
    echo Building SQLite Index...
    python scripts\build_judgment_index.py --source-dir "!src_dir!" --month !month!
    pause
    goto menu
)

if "!opt!"=="6" (
    exit /b
)

echo Invalid choice.
pause
goto menu
