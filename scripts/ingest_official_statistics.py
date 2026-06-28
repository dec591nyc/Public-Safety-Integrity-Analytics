#!/usr/bin/env python
"""Download and profile one month of MOI criminal-case statistics."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


DATASET_ID = "9603"
BASE_URL = "https://statis.moi.gov.tw/micst/webMain.aspx"
BASE_PARAMS = {
    "sys": "220",
    "kind": "21",
    "type": "1",
    "funid": "c0620101",
    "cycle": "41",
    "outmode": "12",
    "utf": "1",
    "compmode": "0",
    "outkind": "3",
    "fldspc": "0,2,4,3,9,3,14,4,22,1,25,4,34,4,40,31,",
    "codspc0": "0,2,3,2,6,1,9,1,12,1,15,17,",
    "rdm": "public-safety-integrity-analytics",
}
FOCUS_METRICS = [
    "總計",
    "傷害",
    "詐欺背信",
    "妨害性自主罪",
    "違反選罷法",
    "違反貪污治罪條例",
    "瀆職",
]


def parse_month(value: str) -> tuple[str, str]:
    if len(value) != 6 or not value.isdigit():
        raise argparse.ArgumentTypeError("month must use YYYYMM")
    year = int(value[:4])
    month = int(value[4:])
    if year <= 1911 or not 1 <= month <= 12:
        raise argparse.ArgumentTypeError("month must be a valid Taiwan Gregorian month")
    return value, f"{year - 1911:03d}{month:02d}"


def build_url(roc_month: str) -> str:
    params = {**BASE_PARAMS, "ym": roc_month, "ymt": roc_month}
    return f"{BASE_URL}?{urlencode(params)}"


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = Request(url, headers={"User-Agent": "Public-Safety-Integrity-Analytics/0.1"})
    with urlopen(request, timeout=60) as response:
        if response.status != 200:
            raise RuntimeError(f"download failed with HTTP {response.status}")
        with tempfile.NamedTemporaryFile(delete=False, dir=destination.parent) as temp:
            shutil.copyfileobj(response, temp)
            temp_path = Path(temp.name)
    temp_path.replace(destination)


def parse_value(value: str) -> tuple[int | None, str]:
    cleaned = value.strip().replace(",", "")
    if cleaned == "-":
        return 0, "dash_zero"
    if cleaned == "":
        return None, "empty"
    try:
        return int(cleaned), "numeric"
    except ValueError:
        return None, "invalid"


def read_source(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise RuntimeError("CSV has no header")
        rows = list(reader)
    if not rows:
        raise RuntimeError("CSV has no data rows")
    return list(reader.fieldnames), rows


def geography_name(row_label: str) -> str:
    return row_label.rsplit("/", 1)[-1].strip()


def row_label_month(row_label: str) -> str | None:
    range_match = re.search(r"(\d{2,3})年\s*\((\d{1,2})~(\d{1,2})月\)", row_label)
    if range_match:
        roc_year = int(range_match.group(1))
        start_month = int(range_match.group(2))
        end_month = int(range_match.group(3))
        if start_month == end_month:
            return f"{roc_year + 1911}{end_month:02d}"
        return None
    single_match = re.search(r"(\d{2,3})年\s*(\d{1,2})月", row_label)
    if single_match:
        return f"{int(single_match.group(1)) + 1911}{int(single_match.group(2)):02d}"
    return None


def select_month_rows(
    dimension_name: str, rows: list[dict[str, str]]
) -> tuple[list[dict[str, str]], int]:
    """Prefer explicit monthly rows over duplicate single-month range rows."""
    # Monthly rows always contain something like "12月/" or "4月/"
    # Range rows either contain "年/" (for December accumulated year) or "(1~6月)/"
    monthly_rows = [row for row in rows if re.search(r"\d+月/", row[dimension_name])]
    range_rows = [row for row in rows if not re.search(r"\d+月/", row[dimension_name])]
    
    monthly_geographies = {geography_name(row[dimension_name]) for row in monthly_rows}
    range_geographies = {geography_name(row[dimension_name]) for row in range_rows}
    if monthly_rows and range_rows and monthly_geographies == range_geographies:
        return monthly_rows, len(range_rows)
    return rows, 0


def write_long_csv(
    path: Path,
    month: str,
    dimension_name: str,
    metrics: list[str],
    rows: list[dict[str, str]],
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "dataset_id",
                "source_month",
                "geography",
                "metric",
                "value",
                "source_value",
                "value_status",
            ],
        )
        writer.writeheader()
        for row in rows:
            geography = geography_name(row[dimension_name])
            for metric in metrics:
                value, status = parse_value(row.get(metric, ""))
                writer.writerow(
                    {
                        "dataset_id": DATASET_ID,
                        "source_month": month,
                        "geography": geography,
                        "metric": metric,
                "value": "" if value is None else value,
                "source_value": row.get(metric, "").strip(),
                "value_status": status,
                    }
                )
                written += 1
    return written


def build_profile(
    month: str,
    source_url: str,
    raw_path: Path,
    headers: list[str],
    raw_rows: list[dict[str, str]],
    rows: list[dict[str, str]],
    duplicate_rows_dropped: int,
    long_rows: int,
) -> dict:
    dimension = headers[0]
    metrics = headers[1:]
    dash_count = 0
    empty_count = 0
    invalid: list[dict[str, str]] = []
    metric_profiles = []

    for metric in metrics:
        numeric_count = 0
        dash_rows = 0
        empty_rows = 0
        values: list[int] = []
        for row in rows:
            value, status = parse_value(row.get(metric, ""))
            if status in {"numeric", "dash_zero"} and value is not None:
                numeric_count += 1
                values.append(value)
                if status == "dash_zero":
                    dash_rows += 1
                    dash_count += 1
            elif status == "empty":
                empty_rows += 1
                empty_count += 1
            else:
                invalid.append({"geography": geography_name(row[dimension]), "metric": metric})
        total_value, total_status = parse_value(rows[0].get(metric, ""))
        component_values = [parse_value(row.get(metric, ""))[0] for row in rows[1:]]
        component_sum = sum(value for value in component_values if value is not None)
        metric_profiles.append(
            {
                "metric": metric,
                "numeric_rows": numeric_count,
                "dash_rows": dash_rows,
                "empty_rows": empty_rows,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "total_value": total_value if total_status in {"numeric", "dash_zero"} else None,
                "component_sum": component_sum,
                "components_match_total": total_status in {"numeric", "dash_zero"}
                and total_value == component_sum,
            }
        )

    total_row = rows[0]
    focus = {}
    for metric in FOCUS_METRICS:
        if metric in headers:
            value, status = parse_value(total_row.get(metric, ""))
            focus[metric] = value if status in {"numeric", "dash_zero"} else None

    return {
        "dataset_id": DATASET_ID,
        "source_month": month,
        "source_url": source_url,
        "raw_file": str(raw_path),
        "raw_bytes": raw_path.stat().st_size,
        "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "dimension_column": dimension,
        "raw_row_count": len(raw_rows),
        "row_count": len(rows),
        "duplicate_single_month_range_rows_dropped": duplicate_rows_dropped,
        "column_count": len(headers),
        "metric_count": len(metrics),
        "long_row_count": long_rows,
        "geographies": [geography_name(row[dimension]) for row in rows],
        "focus_national_totals": focus,
        "dash_value_count": dash_count,
        "empty_value_count": empty_count,
        "invalid_cells": invalid,
        "metrics": metric_profiles,
        "visualization_readiness": {
            "category_bar": True,
            "geography_bar": len(rows) > 1,
            "geography_metric_heatmap": len(rows) > 1 and len(metrics) > 1,
            "monthly_trend": False,
            "monthly_trend_reason": "Only one month was downloaded.",
            "pie_chart": "Requires confirmation that displayed categories are mutually exclusive.",
        },
    }


def render_report(profile: dict) -> str:
    focus = profile["focus_national_totals"]
    month = profile["source_month"]
    display_month = f"{month[:4]} 年 {int(month[4:])} 月" if len(month) == 6 and month.isdigit() else month
    max_focus = max((value or 0) for key, value in focus.items() if key != "總計") or 1
    bars = []
    for label, value in focus.items():
        if label == "總計":
            continue
        width = 0 if value is None else max(1, round(value / max_focus * 100))
        bars.append(
            f'<div class="bar-row"><span>{html.escape(label)}</span>'
            f'<div class="track"><i style="width:{width}%"></i></div>'
            f'<strong>{"-" if value is None else f"{value:,}"}</strong></div>'
        )

    metric_rows = "".join(
        "<tr>"
        f"<td>{html.escape(item['metric'])}</td>"
        f"<td>{item['numeric_rows']}</td>"
        f"<td>{item['dash_rows']}</td>"
        f"<td>{item['empty_rows']}</td>"
        f"<td>{'-' if item['min'] is None else item['min']}</td>"
        f"<td>{'-' if item['max'] is None else item['max']}</td>"
        f"<td>{'是' if item['components_match_total'] else '否'}</td>"
        "</tr>"
        for item in profile["metrics"]
    )
    geographies = "、".join(profile["geographies"])
    source_url = html.escape(profile["source_url"], quote=True)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>官方統計單月資料檢查</title>
  <style>
    *{{box-sizing:border-box}} body{{margin:0;background:#f4f6f8;color:#17212b;font-family:Arial,'Noto Sans TC',sans-serif}}
    main{{max-width:1100px;margin:0 auto;padding:28px 20px 56px}} h1{{font-size:28px;margin:0 0 8px}} h2{{font-size:18px;margin:30px 0 12px}}
    .muted{{color:#607080}} .kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:22px}}
    .kpi{{background:white;border:1px solid #dce2e7;border-radius:6px;padding:16px}} .kpi strong{{display:block;font-size:24px;margin-top:8px}}
    .panel{{background:white;border:1px solid #dce2e7;border-radius:6px;padding:18px;margin-top:12px}}
    .bar-row{{display:grid;grid-template-columns:150px 1fr 80px;gap:12px;align-items:center;margin:10px 0}}
    .track{{height:12px;background:#e8edf1}} .track i{{display:block;height:100%;background:#237b69}}
    table{{width:100%;border-collapse:collapse;font-size:14px}} th,td{{padding:9px 10px;border-bottom:1px solid #e3e7ea;text-align:right}}
    th:first-child,td:first-child{{text-align:left}} .scroll{{overflow:auto;max-height:520px}}
    a{{color:#075e54}} ul{{line-height:1.7}} @media(max-width:720px){{.kpis{{grid-template-columns:1fr 1fr}}.bar-row{{grid-template-columns:110px 1fr 65px}}}}
  </style>
</head>
<body><main>
  <h1>{html.escape(display_month)}官方刑事案件統計</h1>
  <p class="muted">資料集 9603，這是資料檢查報告，不是最終 Dashboard。</p>
  <section class="kpis">
    <div class="kpi">全國總計<strong>{focus.get('總計', 0):,}</strong></div>
    <div class="kpi">資料列<strong>{profile['row_count']}</strong></div>
    <div class="kpi">統計欄位<strong>{profile['metric_count']}</strong></div>
    <div class="kpi">來源「-」格數<strong>{profile['dash_value_count']}</strong></div>
  </section>
  <h2>關注類別：全國件數</h2><div class="panel">{''.join(bars)}</div>
  <h2>可視覺化判斷</h2><div class="panel"><ul>
    <li>類別比較長條圖：可行。</li><li>縣市／機關比較：可行。</li>
    <li>月份趨勢折線圖：目前不可行，因為只有一個月份。</li>
    <li>圓餅圖：需先確認選取類別互斥且能構成完整分母。</li>
    <li>來源同時回傳單月區間彙總與月資料；正規化已排除 {profile['duplicate_single_month_range_rows_dropped']} 筆重複彙總列。</li>
  </ul></div>
  <h2>資料涵蓋區域</h2><div class="panel">{html.escape(geographies)}</div>
  <h2>實際欄位完整度</h2><div class="panel scroll"><table><thead><tr><th>來源欄位</th><th>數值列</th><th>「-」列</th><th>空白列</th><th>最小</th><th>最大</th><th>分項吻合總計</th></tr></thead><tbody>{metric_rows}</tbody></table></div>
  <h2>來源</h2><div class="panel"><a href="{source_url}" target="_blank" rel="noreferrer">開啟內政部原始 CSV</a><p>SHA-256：<code>{profile['sha256']}</code></p></div>
</main></body></html>"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--month", required=True, help="Gregorian month in YYYYMM")
    parser.add_argument("--source-file", type=Path, help="Profile an existing CSV instead of downloading")
    parser.add_argument("--data-root", type=Path, default=Path("data/official/moi_9603"))
    parser.add_argument("--output-root", type=Path, default=Path("output/official_statistics"))
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    month, roc_month = parse_month(args.month)
    source_url = build_url(roc_month)
    data_dir = args.data_root / month
    output_dir = args.output_root / month
    raw_path = data_dir / "raw.csv"
    long_path = output_dir / "normalized_long.csv"
    profile_path = output_dir / "profile.json"
    report_path = output_dir / "report.html"

    if args.source_file:
        data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.source_file, raw_path)
    elif args.force or not raw_path.exists():
        download(source_url, raw_path)

    headers, raw_rows = read_source(raw_path)
    rows, duplicate_rows_dropped = select_month_rows(headers[0], raw_rows)
    returned_months = {row_label_month(row[headers[0]]) for row in rows}
    returned_months.discard(None)
    if month not in returned_months:
        display_months = ", ".join(sorted(returned_months)) or "unknown"
        raise SystemExit(
            f"official export for requested {month} returned month(s): {display_months}; "
            "refusing to write mislabeled profile"
        )
    rows = [row for row in rows if row_label_month(row[headers[0]]) == month]
    long_rows = write_long_csv(long_path, month, headers[0], headers[1:], rows)
    profile = build_profile(
        month,
        source_url,
        raw_path,
        headers,
        raw_rows,
        rows,
        duplicate_rows_dropped,
        long_rows,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path.write_text(render_report(profile), encoding="utf-8")
    print(
        json.dumps(
            {
                "month": month,
                "raw": str(raw_path),
                "normalized": str(long_path),
                "profile": str(profile_path),
                "report": str(report_path),
                "rows": profile["row_count"],
                "columns": profile["column_count"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
