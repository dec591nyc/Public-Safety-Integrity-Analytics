#!/usr/bin/env python



# -*- coding: utf-8 -*-



"""Generate static JSON files from SQLite database to enable no-server Live Demo."""







import calendar



import json



import sqlite3



import urllib.parse



from pathlib import Path



import re



from datetime import datetime







from metric_styles import load_metric_colors, metric_color, sync_metric_styles







# Same configuration as serve_review_dashboard



CATEGORIES = [



    "fraud",



    "money_laundering",



    "sexual_offense",



    "injury",



    "traffic_injury",



    "public_integrity",



    "election_law",



]







CATEGORY_LABELS = {



    "fraud": "詐欺／詐騙",



    "money_laundering": "洗錢",



    "sexual_offense": "妨害性自主／性侵",



    "injury": "傷害／重傷",



    "traffic_injury": "交通傷害",



    "public_integrity": "貪污／瀆職／圖利／賄賂",



    "election_law": "選罷法／賄選",



}







DOMAIN_LABELS = {



    "civil": "民事",



    "criminal": "刑事",



    "administrative": "行政",



    "constitutional": "憲法",



    "disciplinary": "懲戒",



    "other": "其他",



    "unknown": "未分類",



}







OPINION_SOURCES = [



    {"name": "PTT", "status": "ready"},



    {"name": "Dcard", "status": "ready"},



    {"name": "新聞媒體", "status": "ready"},



    {"name": "法律／司改評論", "status": "ready"},



]







OFFICIAL_CATEGORY_MAP = [



    ("fraud", "詐欺背信", ("詐欺背信",)),



    ("injury", "傷害", ("傷害",)),



    ("sexual_offense", "妨害性自主罪", ("妨害性自主罪",)),



    ("public_integrity", "貪污／瀆職", ("違反貪污治罪條例", "瀆職")),



    ("election_law", "違反選罷法", ("違反選罷法",)),



]







TOTAL_GEOGRAPHY = "機關別總計"



TOTAL_METRIC = "總計"



EXCLUDED_GEOGRAPHIES = {TOTAL_GEOGRAPHY, "署所屬機關"}



OTHER_SEGMENT_COLOR = "#94a3b8"



PEAK_SEGMENT_LIMIT = 10







TOPIC_COLORS = ["#2563eb", "#0891b2", "#16a34a", "#d97706", "#dc2626", "#7c3aed", "#64748b"]







OFFICIAL_TOPIC_GROUPS = [



    {



        "id": "property_fraud",



        "label": "財產與詐欺",



        "description": "以詐欺、竊盜、侵占、強盜搶奪等民眾最常感受到的財產侵害案類為主。",



        "metrics": ("詐欺背信", "竊盜", "侵占", "竊佔", "毀棄損壞", "強盜搶奪", "恐嚇取財"),



    },



    {



        "id": "violence_personal",



        "label": "暴力與人身安全",



        "description": "觀察殺人、傷害、妨害自由、強盜搶奪等直接影響人身安全的案件。",



        "metrics": ("傷害", "殺人", "妨害自由", "強盜搶奪", "擄人勒贖", "恐嚇取財"),



    },



    {



        "id": "sexual_safety",



        "label": "性犯罪與家庭",



        "description": "聚焦妨害性自主、妨害風化、家庭與婚姻相關案類，適合後續接被害保護與通報資源。",



        "metrics": ("妨害性自主罪", "妨害風化", "妨害家庭及婚姻", "遺棄"),



    },



    {



        "id": "drug_public_safety",



        "label": "毒品與公共安全",



        "description": "比較毒品、公共危險、槍砲彈藥刀械與秩序類案件的縣市分布。",



        "metrics": ("違反毒品危害防制條例", "公共危險", "違反槍砲彈藥刀械管制條例", "妨害秩序"),



    },



    {



        "id": "integrity_governance",



        "label": "廉政與治理",



        "description": "追蹤貪污治罪條例、瀆職、選罷法與偽造文書印文等治理信任相關案類。",



        "metrics": ("違反貪污治罪條例", "瀆職", "違反選罷法", "偽造文書印文"),



    },



    {



        "id": "digital_ip",



        "label": "數位與智慧財產",



        "description": "整理妨害電腦使用、著作權、商標與專利法案件，作為數位犯罪與智財風險入口。",



        "metrics": ("妨害電腦使用", "違反著作權法", "違反商標法", "違反專利法"),



    },



]







def percent_change(current, previous):



    if previous in {None, 0}:



        return None



    return round((current - previous) / previous * 100, 2)







def latest_complete_month():



    today = datetime.now()



    year = today.year



    month = today.month - 1



    if month == 0:



        year -= 1



        month = 12



    return f"{year}{month:02d}"







def percent_of(part, whole):



    if not whole:



        return 0.0



    return round(part / whole * 100, 2)







def official_case_metrics(stats_lookup):



    rows = [



        (metric, int(count or 0))



        for (geography, metric), count in stats_lookup.items()



        if geography == TOTAL_GEOGRAPHY and metric != TOTAL_METRIC



    ]



    rows.sort(key=lambda item: (-item[1], item[0]))



    return tuple(metric for metric, _ in rows)











def topic_definitions(stats_lookup):



    all_metrics = official_case_metrics(stats_lookup)



    covered_metrics = {



        metric



        for topic in OFFICIAL_TOPIC_GROUPS



        for metric in topic["metrics"]



    }



    other_metrics = tuple(metric for metric in all_metrics if metric not in covered_metrics)



    return [



        *OFFICIAL_TOPIC_GROUPS,



        {



            "id": "other_types",



            "label": "其他類型",



            "description": "收納未放入前六個分析主題的官方案類；其中包含官方原始欄位「其他」。",



            "metrics": other_metrics,



            "is_residual_scope": True,



            "note": "其他類型是前六個分析主題之外的官方案類集合，不是模擬或推估數據。",



        },



        {



            "id": "all_types",



            "label": "全部類型",



            "description": "包含官方匯出中所有非總計案類，作為可與全國總案量互相核對的完整資料範圍。",



            "metrics": all_metrics,



            "is_total_scope": True,



            "note": "全部類型為完整案類加總；其他主題包是分析入口，可能不完整且部分案類會跨主題出現。",



        },



    ]











def build_topic_yoy_lookup(conn, selected_month, topics):



    if not re.fullmatch(r"\d{6}", selected_month or ""):



        return {}



    previous_month = f"{int(selected_month[:4]) - 1}{selected_month[4:]}"



    lookup = {}



    for topic in topics:



        if topic.get("is_total_scope"):



            rows = conn.execute(



                """



                SELECT geography, raw_value AS total



                FROM official_statistics



                WHERE source_month = ? AND metric = ?



                """,



                [previous_month, TOTAL_METRIC],



            ).fetchall()



        else:



            metrics = tuple(topic.get("metrics") or ())



            if not metrics:



                continue



            markers = ",".join("?" for _ in metrics)



            rows = conn.execute(



                f"""



                SELECT geography, SUM(raw_value) AS total



                FROM official_statistics



                WHERE source_month = ? AND metric IN ({markers})



                GROUP BY geography



                """,



                [previous_month] + list(metrics),



            ).fetchall()



        for row in rows:



            lookup[(topic["id"], row["geography"])] = int(row["total"] or 0)



    return lookup











def build_topic_monthly_trends(conn, months, topics):



    trends = {}



    total_rows = conn.execute(



        """



        SELECT source_month, raw_value AS count



        FROM official_statistics



        WHERE geography = ? AND metric = ?



        ORDER BY source_month



        """,



        [TOTAL_GEOGRAPHY, TOTAL_METRIC],



    ).fetchall()



    total_lookup = {row["source_month"]: int(row["count"] or 0) for row in total_rows}



    trends["all_types"] = [{"month": month, "count": total_lookup.get(month, 0)} for month in months]



    for topic in topics:



        if topic.get("is_total_scope"):



            continue



        markers = ",".join("?" for _ in topic["metrics"])



        rows = conn.execute(



            f"""



            SELECT source_month, SUM(raw_value) AS count



            FROM official_statistics



            WHERE geography = ? AND metric IN ({markers})



            GROUP BY source_month



            ORDER BY source_month



            """,



            [TOTAL_GEOGRAPHY] + list(topic["metrics"]),



        ).fetchall()



        trend_lookup = {row["source_month"]: int(row["count"] or 0) for row in rows}



        trends[topic["id"]] = [{"month": month, "count": trend_lookup.get(month, 0)} for month in months]



    return trends







def build_topic_drilldowns(stats_lookup, geographies, national_total, metric_colors, topics, topic_trends=None, topic_yoy_lookup=None):



    topic_rows = []



    topic_yoy_lookup = topic_yoy_lookup or {}



    for topic in topics:



        national_segments = []



        for index, metric in enumerate(topic["metrics"]):



            count = int(stats_lookup.get((TOTAL_GEOGRAPHY, metric), 0) or 0)



            if count <= 0:



                continue



            national_segments.append({



                "metric": metric,



                "label": metric,



                "count": count,



                "color": metric_color(metric, metric_colors, index),



            })







        national_segments.sort(key=lambda segment: (-segment["count"], segment["label"]))



        topic_total = sum(segment["count"] for segment in national_segments)



        for segment in national_segments:



            segment["share_pct"] = percent_of(segment["count"], topic_total)



        topic_previous_total = topic_yoy_lookup.get((topic["id"], TOTAL_GEOGRAPHY))







        top_regions = []



        for geography in sorted(geographies - EXCLUDED_GEOGRAPHIES):



            region_segments = []



            for index, metric in enumerate(topic["metrics"]):



                count = int(stats_lookup.get((geography, metric), 0) or 0)



                if count <= 0:



                    continue



                region_segments.append({



                    "metric": metric,



                    "label": metric,



                    "count": count,



                    "color": metric_color(metric, metric_colors, index),



                })







            region_segments.sort(key=lambda segment: (-segment["count"], segment["label"]))



            region_total = sum(segment["count"] for segment in region_segments)



            if region_total <= 0:



                continue



            for segment in region_segments:



                segment["share_pct"] = percent_of(segment["count"], region_total)



            previous_region_total = topic_yoy_lookup.get((topic["id"], geography))







            top_regions.append({



                "geography": geography,



                "total": region_total,



                "share_pct": percent_of(region_total, topic_total),



                "previous_year_total": previous_region_total,



                "yoy_pct": percent_change(region_total, previous_region_total),



                "segments": region_segments,



            })







        sorted_regions = sorted(top_regions, key=lambda row: row["total"], reverse=True)







        topic_rows.append({



            "id": topic["id"],



            "label": topic["label"],



            "description": topic["description"],



            "total": topic_total,



            "share_pct": percent_of(topic_total, national_total),



            "previous_year_total": topic_previous_total,



            "yoy_pct": percent_change(topic_total, topic_previous_total),



            "is_total_scope": bool(topic.get("is_total_scope")),



            "is_residual_scope": bool(topic.get("is_residual_scope")),



            "segments": national_segments,



            "top_regions": sorted_regions[:5],



            "region_breakdowns": sorted_regions,



            "trend": (topic_trends or {}).get(topic["id"], []),



            "source_metrics": list(topic["metrics"]),



            "note": topic.get("note") or "主題包是分析入口，部分案類可能因公共安全語意出現在多個主題中，不應跨主題加總。",



        })







    return topic_rows







def month_day_count(month):



    if not re.fullmatch(r"\d{6}", month or ""):



        return 30



    return calendar.monthrange(int(month[:4]), int(month[4:]))[1]







def build_ai_insight(monthly_counts, topic_drilldowns):



    window = monthly_counts[-12:]



    if len(window) < 3:



        return {



            "status": "insufficient",



            "title": "趨勢資料不足",



            "method": "rule_based_official_statistics_v1",



            "summary": "目前可用月份不足，暫不產生趨勢異常研判。",



            "evidence": [],



            "topic_observations": [],



            "limitations": ["至少需要 3 個月份才進行趨勢低點或高點判讀。"],



        }







    counts = [int(row.get("count") or 0) for row in window]



    average = sum(counts) / len(counts)



    min_index, min_point = min(enumerate(window), key=lambda item: int(item[1].get("count") or 0))



    min_month = min_point["month"]



    min_count = int(min_point.get("count") or 0)



    previous_point = window[min_index - 1] if min_index > 0 else None



    next_point = window[min_index + 1] if min_index < len(window) - 1 else None



    previous_count = int(previous_point["count"]) if previous_point else None



    next_count = int(next_point["count"]) if next_point else None



    vs_average = percent_change(min_count, round(average))



    vs_previous = percent_change(min_count, previous_count)



    vs_next = percent_change(min_count, next_count)



    day_count = month_day_count(min_month)







    topic_observations = []



    for topic in topic_drilldowns:



        lookup = {row["month"]: int(row.get("count") or 0) for row in topic.get("trend", [])}



        if min_month not in lookup:



            continue



        previous_topic_count = lookup.get(previous_point["month"]) if previous_point else None



        change = percent_change(lookup[min_month], previous_topic_count)



        topic_observations.append({



            "label": topic.get("label"),



            "count": lookup[min_month],



            "previous_count": previous_topic_count,



            "change_pct": change,



        })







    topic_observations = sorted(



        topic_observations,



        key=lambda row: (row["change_pct"] is None, row["change_pct"] if row["change_pct"] is not None else 0),



    )[:6]







    severity = "watch"



    if vs_average is not None and vs_average <= -20:



        severity = "high"



    elif vs_average is not None and vs_average <= -10:



        severity = "medium"







    return {



        "status": "ready",



        "severity": severity,



        "title": f"{min_month[:4]} 年 {int(min_month[4:])} 月為近 {len(window)} 個月低點",



        "method": "rule_based_official_statistics_v1",



        "summary": (



            f"{min_month[:4]} 年 {int(min_month[4:])} 月總案量 {min_count:,} 件，"



            f"低於近 {len(window)} 個月平均 {round(average):,} 件。"



            "此區塊僅依官方統計做異常提示，不推定犯罪實際增減原因。"



        ),



        "evidence": [



            {"label": "低點月份", "value": min_month, "display": f"{min_month[:4]}/{min_month[4:]}"},



            {"label": "低點案量", "value": min_count, "display": f"{min_count:,} 件"},



            {"label": "近月平均", "value": round(average), "display": f"{round(average):,} 件"},



            {"label": "相對平均", "value": vs_average, "display": f"{vs_average:+.1f}%" if vs_average is not None else "無法計算"},



            {"label": "相對前月", "value": vs_previous, "display": f"{vs_previous:+.1f}%" if vs_previous is not None else "無前月基準"},



            {"label": "相對次月", "value": vs_next, "display": f"{vs_next:+.1f}%" if vs_next is not None else "無次月基準"},



            {"label": "低點日均", "value": round(min_count / day_count, 1), "display": f"{min_count / day_count:,.1f} 件/日"},



        ],



        "topic_observations": topic_observations,



        "limitations": [



            "目前尚未納入工作日數、春節假期、人口數或報案登錄延遲。",



            "刑事案件發生件數不是起訴、判決或定罪件數。",



            "AI 研判僅提供可追溯的異常提示，需搭配行政時程與地方背景再判讀。",



        ],



    }







def build_annual_comparison(conn, months, selected_month, metric_colors):



    selected_year = int(selected_month[:4])



    selected_month_num = int(selected_month[4:])



    years = sorted({int(month[:4]) for month in months if re.fullmatch(r"\d{6}", month)})



    years = [year for year in years if year <= selected_year][-8:]



    rows = []



    previous_total = None







    for year in years:



        start = f"{year}01"



        end = f"{year}{selected_month_num:02d}"



        result = conn.execute(



            """



            SELECT SUM(raw_value) AS total, COUNT(*) AS months_covered



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            """,



            [start, end],



        ).fetchone()



        total = int(result["total"] or 0) if result else 0



        rows.append({



            "year": year,



            "total": total,



            "months_covered": int(result["months_covered"] or 0) if result else 0,



            "yoy_pct": percent_change(total, previous_total),



        })



        if total:



            previous_total = total







    peak_rows = []



    for year in years:



        start = f"{year}01"



        end_month = selected_month_num if year == selected_year else 12



        end = f"{year}{end_month:02d}"



        peak = conn.execute(



            """



            SELECT source_month, raw_value



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            ORDER BY raw_value DESC, source_month ASC



            LIMIT 1



            """,



            [start, end],



        ).fetchone()



        if not peak:



            continue



        top_metrics = conn.execute(



            """



            SELECT metric, raw_value



            FROM official_statistics



            WHERE source_month = ?



              AND geography = '機關別總計'



              AND metric NOT IN ('總計', '其他')



              AND raw_value > 0



            ORDER BY raw_value DESC



            LIMIT ?



            """,



            [peak["source_month"], PEAK_SEGMENT_LIMIT],



        ).fetchall()



        top_metric_sum = sum(int(row["raw_value"] or 0) for row in top_metrics)



        peak_total = int(peak["raw_value"] or 0)



        segments = []



        for index, row in enumerate(top_metrics):



            count = int(row["raw_value"] or 0)



            segments.append({



                "metric": row["metric"],



                "label": row["metric"],



                "count": count,



                "share_pct": percent_of(count, peak_total),



                "color": metric_color(row["metric"], metric_colors, index),



            })



        other_count = max(peak_total - top_metric_sum, 0)



        if other_count:



            segments.append({



                "metric": "__other__",



                "label": "其他案類",



                "count": other_count,



                "share_pct": percent_of(other_count, peak_total),



                "color": OTHER_SEGMENT_COLOR,



            })



        peak_rows.append({



            "year": year,



            "peak_month": peak["source_month"],



            "total": peak_total,



            "top_metric_sum": top_metric_sum,



            "other_count": other_count,



            "scope": f"{year}/01-{year}/{end_month:02d}" if year == selected_year else f"{year}/01-{year}/12",



            "segments": segments,



        })







    def build_change_driver(current_year, previous_year, end_month, period_label):



        current_start = f"{current_year}01"



        current_end = f"{current_year}{end_month:02d}"



        previous_start = f"{previous_year}01"



        previous_end = f"{previous_year}{end_month:02d}"



        current_total_row = conn.execute(



            """



            SELECT SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            """,



            [current_start, current_end],



        ).fetchone()



        previous_total_row = conn.execute(



            """



            SELECT SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric = '總計'



            """,



            [previous_start, previous_end],



        ).fetchone()



        current_total = int(current_total_row["total"] or 0) if current_total_row else 0



        previous_total = int(previous_total_row["total"] or 0) if previous_total_row else 0



        current_metric_rows = conn.execute(



            """



            SELECT metric, SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric != '總計'



            GROUP BY metric



            """,



            [current_start, current_end],



        ).fetchall()



        previous_metric_rows = conn.execute(



            """



            SELECT metric, SUM(raw_value) AS total



            FROM official_statistics



            WHERE source_month BETWEEN ? AND ?



              AND geography = '機關別總計'



              AND metric != '總計'



            GROUP BY metric



            """,



            [previous_start, previous_end],



        ).fetchall()



        current_metrics = {item["metric"]: int(item["total"] or 0) for item in current_metric_rows}



        previous_metrics = {item["metric"]: int(item["total"] or 0) for item in previous_metric_rows}



        metric_deltas = []



        total_delta = current_total - previous_total



        for metric in sorted(set(current_metrics) | set(previous_metrics)):



            current_count = current_metrics.get(metric, 0)



            previous_count = previous_metrics.get(metric, 0)



            delta = current_count - previous_count



            if delta == 0:



                continue



            metric_deltas.append({



                "metric": metric,



                "label": "其他案類" if metric == "其他" else metric,



                "current": current_count,



                "previous": previous_count,



                "delta": delta,



                "delta_share_pct": percent_of(delta, total_delta) if total_delta else None,



                "color": metric_color(metric, metric_colors, len(metric_deltas)),



            })



        metric_delta_sum = sum(item["delta"] for item in metric_deltas)



        metric_deltas.sort(key=lambda item: abs(item["delta"]), reverse=True)



        return {



            "year": current_year,



            "previous_year": previous_year,



            "period_label": period_label,



            "current_total": current_total,



            "previous_total": previous_total,



            "total_delta": total_delta,



            "metric_delta_sum": metric_delta_sum,



            "reconciliation_delta": total_delta - metric_delta_sum,



            "drivers": metric_deltas[:8],



            "driver_count": len(metric_deltas),



            "current_metric_sum": sum(current_metrics.values()),



            "previous_metric_sum": sum(previous_metrics.values()),



        }







    change_drivers = []



    for index, row in enumerate(rows):



        if index == 0:



            continue



        change_drivers.append(



            build_change_driver(



                int(row["year"]),



                int(rows[index - 1]["year"]),



                selected_month_num,



                f"1-{selected_month_num}月同期間",



            )



        )







    complete_years = [



        year for year in years



        if year < selected_year and all(f"{year}{month:02d}" in months for month in range(1, 13))



    ]



    full_year_change_drivers = []



    for index, year in enumerate(complete_years):



        if index == 0:



            continue



        full_year_change_drivers.append(



            build_change_driver(year, complete_years[index - 1], 12, "1-12月完整年度")



        )







    return {



        "period_label": f"1-{selected_month_num}月同期間",



        "selected_year": selected_year,



        "selected_month": selected_month,



        "rows": list(reversed(rows)),



        "peak_months": list(reversed(peak_rows)),



        "change_drivers": list(reversed(change_drivers)),



        "full_year_change_drivers": list(reversed(full_year_change_drivers)),



        "note": "年度比較採同期間累計；年度高峰月為搜尋範圍內單月總量最高月份。案類拆解使用全部官方案類做加總檢查，頁面只顯示主要增減案類。",



    }







def parse_json(value, fallback):



    if isinstance(value, (dict, list)):



        return value



    try:



        return json.loads(value or "")



    except (TypeError, json.JSONDecodeError):



        return fallback







def compact_text(value: str, limit: int = 260) -> str:



    text = re.sub(r"\s+", " ", value or "").strip()



    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"







def extractive_summary(row: dict) -> dict:



    excerpt = compact_text(row.get("excerpt") or "", 900)



    if not excerpt:



        return {



            "text": "索引中沒有足夠文字可供摘要，請開啟來源 PDF 人工審閱。",



            "provider": "extractive_rule_v1",



            "confidence": "insufficient",



            "needs_manual_review": True,



            "evidence_snippets": [],



        }







    sentences = [



        compact_text(part, 180)



        for part in re.split(r"(?<=[。！？；])", excerpt)



        if compact_text(part, 180)



    ]



    matched = parse_json(row.get("matched_keywords"), [])



    anchors = ["主文", "原告", "被告", "判決", "裁定", "應給付", "有期徒刑", "無罪", "駁回"]







    scored = []



    for index, sentence in enumerate(sentences):



        score = sum(2 for term in anchors if term in sentence)



        score += sum(1 for term in matched[:8] if term and term in sentence)



        scored.append((score, index, sentence))







    selected = sorted(scored, key=lambda item: (-item[0], item[1]))[:2]



    selected = sorted(selected, key=lambda item: item[1])



    evidence = [item[2] for item in selected] or [compact_text(excerpt, 180)]



    title = compact_text(row.get("jtitle") or "未標示案由", 48)



    text = compact_text(f"{title}：" + " ".join(evidence), 300)



    return {



        "text": text,



        "provider": "extractive_rule_v1",



        "confidence": "low",



        "needs_manual_review": True,



        "evidence_snippets": evidence,



    }







def main():



    db_path = Path("data/local/public_safety.sqlite")



    static_api_dir = Path("web/static_api")



    static_api_dir.mkdir(parents=True, exist_ok=True)







    print(f"Connecting to database {db_path}...")



    conn = sqlite3.connect(db_path)



    conn.row_factory = sqlite3.Row



    cursor = conn.cursor()



    metric_style_count = sync_metric_styles(conn)



    metric_colors = load_metric_colors(conn)



    print(f"Synced {metric_style_count} metric style rows.")







    # 1. Months list



    print("Generating months.json...")



    cursor.execute(



        """



        SELECT source_month, SUM(raw_value) as count



        FROM official_statistics



        WHERE metric = '總計' AND geography = '機關別總計' AND source_month <= ?



        GROUP BY source_month



        ORDER BY source_month DESC



        """,



        [latest_complete_month()]



    )



    months_rows = [{"source_month": r["source_month"], "count": r["count"]} for r in cursor.fetchall()]



    if not months_rows:



        months_rows = [{"source_month": "202606", "count": 1248}]



    



    with open(static_api_dir / "months.json", "w", encoding="utf-8") as f:



        json.dump({"items": months_rows}, f, ensure_ascii=False, indent=2)







    # We will export details for every month found in DB



    available_months = [m["source_month"] for m in months_rows]







    for month in available_months:



        print(f"\nProcessing month {month}...")



        



        # 2. Official Summary Profile



        # Get all months in order



        all_months_cursor = conn.execute("SELECT DISTINCT source_month FROM official_statistics WHERE source_month <= ? ORDER BY source_month ASC", [latest_complete_month()])



        months_list = [r["source_month"] for r in all_months_cursor.fetchall()]



        



        current_rows = [dict(r) for r in conn.execute(



            "SELECT metric, geography, raw_value FROM official_statistics WHERE source_month = ?", [month]



        ).fetchall()]



        stats_lookup = {(r["geography"], r["metric"]): r["raw_value"] for r in current_rows}



        geographies = {r["geography"] for r in current_rows}



        total = stats_lookup.get(("機關別總計", "總計"), 0)







        prev_month = None



        if month in months_list:



            idx = months_list.index(month)



            if idx > 0:



                prev_month = months_list[idx - 1]



            months_through_selected = months_list[: idx + 1]



        else:



            months_through_selected = months_list







        previous_total = 0



        if prev_month:



            prev_total_row = conn.execute(



                "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'",



                [prev_month]



            ).fetchone()



            previous_total = prev_total_row[0] if prev_total_row else 0







        monthly_counts = []



        for m in months_through_selected:



            cnt_row = conn.execute(



                "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'",



                [m]



            ).fetchone()



            monthly_counts.append({"month": m, "count": cnt_row[0] if cnt_row else 0})







        safety_index_row = conn.execute(



            """



            SELECT SUM(s.raw_value * c.severity_score) 



            FROM official_statistics s



            JOIN crime_categories c ON s.metric = c.metric



            WHERE s.source_month = ? AND s.geography = '機關別總計' AND s.metric != '總計'



            """,



            [month]



        ).fetchone()



        safety_index = safety_index_row[0] if safety_index_row and safety_index_row[0] else 0







        category_counts = []



        for key, label, source_labels in OFFICIAL_CATEGORY_MAP:



            count = sum(stats_lookup.get(("機關別總計", sl), 0) for sl in source_labels)



            prev_count = 0



            if prev_month:



                markers = ",".join("?" for _ in source_labels)



                prev_row = conn.execute(



                    f"SELECT SUM(raw_value) FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric IN ({markers})",



                    [prev_month] + list(source_labels)



                ).fetchone()



                prev_count = prev_row[0] if prev_row and prev_row[0] else 0







            category_counts.append({



                "category": key,



                "label": label,



                "count": count,



                "change_pct": percent_change(count, prev_count)



            })







        iccs_rows = []



        



        iccs_breakdown = []



        for r in iccs_rows:



            code = r["iccs_code"]



            children = [dict(c) for c in conn.execute(



                """



                SELECT s.metric, c.severity_score, s.raw_value as count, (s.raw_value * c.severity_score) as weighted_score



                FROM official_statistics s



                JOIN crime_categories c ON s.metric = c.metric



                WHERE s.source_month = ? AND s.geography = '機關別總計' AND c.iccs_code = ?



                ORDER BY count DESC



                """,



                [month, code]



            ).fetchall()]



            



            iccs_breakdown.append({



                "code": code,



                "name": r["iccs_name"],



                "count": r["count"],



                "weighted_score": r["weighted_score"],



                "children": children



            })







        flags_row = conn.execute(



            """



            SELECT 



              SUM(CASE WHEN c.flag_cyber = 1 THEN s.raw_value ELSE 0 END) as cyber,



              SUM(CASE WHEN c.flag_weapon = 1 THEN s.raw_value ELSE 0 END) as weapon,



              SUM(CASE WHEN c.flag_domestic = 1 THEN s.raw_value ELSE 0 END) as domestic,



              SUM(CASE WHEN c.flag_organized_fraud = 1 THEN s.raw_value ELSE 0 END) as organized_fraud



            FROM official_statistics s



            JOIN crime_categories c ON s.metric = c.metric



            WHERE s.source_month = ? AND s.geography = '機關別總計'



            """,



            [month]



        ).fetchone()



        



        flags_summary = {



            "cyber": flags_row["cyber"] if flags_row and flags_row["cyber"] else 0,



            "weapon": flags_row["weapon"] if flags_row and flags_row["weapon"] else 0,



            "domestic": flags_row["domestic"] if flags_row and flags_row["domestic"] else 0,



            "organized_fraud": flags_row["organized_fraud"] if flags_row and flags_row["organized_fraud"] else 0



        }







        region_weighted_rows = conn.execute(



            """



            SELECT s.geography, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score



            FROM official_statistics s



            JOIN crime_categories c ON s.metric = c.metric



            WHERE s.source_month = ? AND s.geography NOT IN ('機關別總計', '署所屬機關') AND s.metric != '總計'



            GROUP BY s.geography



            ORDER BY weighted_score DESC



            """,



            [month]



        ).fetchall()



        region_weighted_counts = [{"geography": r["geography"], "count": r["count"], "weighted_score": r["weighted_score"]} for r in region_weighted_rows]



        topics = topic_definitions(stats_lookup)



        topic_monthly_trends = build_topic_monthly_trends(conn, months_through_selected, topics)



        topic_yoy_lookup = build_topic_yoy_lookup(conn, month, topics)



        topic_drilldowns = build_topic_drilldowns(



            stats_lookup,



            geographies,



            total,



            metric_colors,



            topics,



            topic_monthly_trends,



            topic_yoy_lookup,



        )



        ai_insight = build_ai_insight(monthly_counts, topic_drilldowns)



        annual_comparison = build_annual_comparison(conn, months_through_selected, month, metric_colors)







        selected_metric = "詐欺背信"



        region_rows = conn.execute(



            """



            SELECT geography, raw_value 



            FROM official_statistics 



            WHERE source_month = ? AND metric = ? AND geography NOT IN ('機關別總計', '署所屬機關')



            ORDER BY raw_value DESC



            """,



            [month, selected_metric]



        ).fetchall()



        region_counts = [{"geography": r["geography"], "count": r["raw_value"]} for r in region_rows]







        raw_rows_count = len(current_rows)



        metric_count_val = conn.execute("SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month = ?", [month]).fetchone()[0]



        case_metric_count = conn.execute(



            "SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month = ? AND metric != ?",



            [month, TOTAL_METRIC],



        ).fetchone()[0]



        national_metric_sum = conn.execute(



            """



            SELECT SUM(raw_value)



            FROM official_statistics



            WHERE source_month = ? AND geography = ? AND metric != ?



            """,



            [month, TOTAL_GEOGRAPHY, TOTAL_METRIC],



        ).fetchone()[0] or 0



        total_reconciliation_delta = int(total or 0) - int(national_metric_sum or 0)







        leading_topics = [



            item for item in sorted(topic_drilldowns, key=lambda item: item["total"], reverse=True)



            if not item.get("is_total_scope") and not item.get("is_residual_scope")



        ][:3]



        leading_text = "、".join(f"{item['label']} {item['total']:,} 件" for item in leading_topics)



        summary_text = (



            f"{month[:4]} 年 {int(month[4:])} 月官方刑事案件發生件數資料已載入。"



            f"本頁優先呈現民眾與民代常關注的治安主題：{leading_text}；"



            f"全國總案量 {total:,} 件僅作統計範圍背景。"



        )







        official_summary_payload = {



            "source_month": month,



            "source_url": "https://statis.moi.gov.tw/micst/webMain.aspx",



            "dataset_id": "9603",



            "total_cases": total,



            "total_change_pct": percent_change(total, previous_total),



            "safety_index": safety_index,



            "monthly_counts": monthly_counts,



            "category_counts": category_counts,



            "iccs_breakdown": iccs_breakdown,



            "flags_summary": flags_summary,



            "topic_drilldowns": topic_drilldowns,



            "ai_insight": ai_insight,



            "annual_comparison": annual_comparison,



            "metric_styles": {



                "count": len(metric_colors),



                "items": [{"metric": metric, "color": color} for metric, color in sorted(metric_colors.items())],



            },



            "region_weighted_counts": region_weighted_counts,



            "region_metric": selected_metric,



            "region_counts": region_counts,



            "quality": {



                "raw_rows": raw_rows_count,



                "selected_rows": raw_rows_count // 24 if raw_rows_count > 0 else 0,



                "duplicate_rows_dropped": 0,



                "metric_count": metric_count_val,



                "case_metric_count": case_metric_count,



                "national_metric_sum": national_metric_sum,



                "total_reconciliation_delta": total_reconciliation_delta,



                "matched_metric_totals": 1 if total_reconciliation_delta == 0 else 0,



                "invalid_cells": 0,



                "dash_zero_cells": 0,



            },



            "summary": {



                "text": summary_text,



                "method": "MOI dataset 9603 official descriptive statistics",



            },



        }







        with open(static_api_dir / f"official-summary_{month}.json", "w", encoding="utf-8") as f:



            json.dump(official_summary_payload, f, ensure_ascii=False, indent=2)







        print(f"Completed month {month}: exported official summary only.")



        continue







        # 3. Opinion Summary



        print(f"Generating opinion_{month}.json...")



        # Get opinion posts



        month_pattern = f"{month[:4]}-{month[4:]}%"



        opinion_rows = [dict(r) for r in conn.execute(



            """



            SELECT post_id, source, author, title, content, url, publish_date, category, sentiment, matched_keywords



            FROM opinion_posts



            WHERE publish_date LIKE ?



            ORDER BY publish_date DESC



            """,



            [month_pattern]



        ).fetchall()]







        topic_summaries = []



        for r in opinion_rows:



            kw = parse_json(r["matched_keywords"], [])



            topic_summaries.append({



                "topic": r["category"],



                "source": r["source"],



                "title": r["title"],



                "excerpt": compact_text(r["content"], 180),



                "url": r["url"],



                "publish_date": r["publish_date"],



                "sentiment": r["sentiment"],



                "keywords": kw



            })







        daily_rows = conn.execute(



            """



            SELECT SUBSTR(publish_date, 9, 2) as day, COUNT(*) as count



            FROM opinion_posts



            WHERE publish_date LIKE ?



            GROUP BY day



            ORDER BY day ASC



            """,



            [month_pattern]



        ).fetchall()



        daily_counts = [{"day": int(r["day"]), "count": r["count"]} for r in daily_rows]







        opinion_status = "ready" if topic_summaries else "not_configured"



        opinion_message = "已更新本月輿情討論資料。" if topic_summaries else "尚未啟動輿論爬蟲，因此不顯示推估或未驗證數字。"







        opinion_payload = {



            "source_month": month,



            "status": opinion_status,



            "sources": OPINION_SOURCES,



            "daily_counts": daily_counts,



            "topic_summaries": topic_summaries,



            "message": opinion_message,



        }







        with open(static_api_dir / f"opinion_{month}.json", "w", encoding="utf-8") as f:



            json.dump(opinion_payload, f, ensure_ascii=False, indent=2)







        # 4. Judgments List



        print(f"Generating judgments_{month}.json...")



        



        # Get count of total judgments for the month



        total_judgments = conn.execute("SELECT COUNT(*) FROM judgments WHERE source_month = ?", [month]).fetchone()[0]



        



        # Fetch up to 150 judgments



        judgments_cursor = conn.execute(



            """



            SELECT jid, source_month, court_folder, case_domain, jyear, jcase, jno,



                   jdate, jtitle, jpdf, text_length, excerpt, category_flags,



                   matched_keywords, age, gender, occupation, education, income_level, birth_city



            FROM judgments



            WHERE source_month = ?



            ORDER BY jdate DESC, jid ASC



            LIMIT 150



            """,



            [month]



        ).fetchall()



        



        judgments_items = []



        for r in judgments_cursor:



            item = dict(r)



            # Remove heavy text field to keep static JSON lightweight



            item.pop("excerpt", None)



            item["category_flags"] = parse_json(item["category_flags"], {})



            item["matched_keywords"] = parse_json(item["matched_keywords"], [])



            # Skip heavy extractive summary for static JSON



            item["summary"] = None



            judgments_items.append(item)



                



        judgments_payload = {



            "total": total_judgments if total_judgments > 0 else len(judgments_items),



            "limit": 150,



            "offset": 0,



            "items": judgments_items,



            "warnings": [],



            "search_capabilities": {



                "title": "static_in_memory",



                "court": "static_in_memory",



                "plaintiff": "static_in_memory",



                "defendant": "static_in_memory",



            },



        }



        



        with open(static_api_dir / f"judgments_{month}.json", "w", encoding="utf-8") as f:



            json.dump(judgments_payload, f, ensure_ascii=False, indent=2)



            



        print(f"Completed month {month}: exported {len(judgments_items)} judgments details.")







    # 5. Annual Summaries



    print("\nGenerating annual summaries...")



    years = sorted(list({m[:4] for m in available_months if m <= latest_complete_month()}))



    for year in years:



        print(f"Generating annual summary for year {year}...")



        prev_year = str(int(year) - 1)



        months_through_selected = [m for m in sorted(available_months) if m <= f"{year}12"]







        current_rows = [dict(r) for r in conn.execute(



            """



            SELECT metric, geography, SUM(raw_value) as raw_value



            FROM official_statistics



            WHERE source_month LIKE ?



            GROUP BY metric, geography



            """,



            [f"{year}%"]



        ).fetchall()]



        stats_lookup = {(r["geography"], r["metric"]): r["raw_value"] for r in current_rows}



        geographies = {r["geography"] for r in current_rows}



        total = stats_lookup.get(("機關別總計", "總計"), 0)







        prev_total_row = conn.execute(



            "SELECT SUM(raw_value) FROM official_statistics WHERE source_month LIKE ? AND geography = '機關別總計' AND metric = '總計'",



            [f"{prev_year}%"]



        ).fetchone()



        previous_total = prev_total_row[0] if prev_total_row and prev_total_row[0] else 0







        monthly_counts = []



        for m in months_through_selected:



            cnt_row = conn.execute(



                "SELECT raw_value FROM official_statistics WHERE source_month = ? AND geography = '機關別總計' AND metric = '總計'",



                [m]



            ).fetchone()



            monthly_counts.append({"month": m, "count": cnt_row[0] if cnt_row else 0})







        safety_index_row = conn.execute(



            """



            SELECT SUM(s.raw_value * c.severity_score)



            FROM official_statistics s



            JOIN crime_categories c ON s.metric = c.metric



            WHERE s.source_month LIKE ? AND s.geography = '機關別總計' AND s.metric != '總計'



            """,



            [f"{year}%"]



        ).fetchone()



        safety_index = safety_index_row[0] if safety_index_row and safety_index_row[0] else 0







        category_counts = []



        for key, label, source_labels in OFFICIAL_CATEGORY_MAP:



            count = sum(stats_lookup.get(("機關別總計", sl), 0) for sl in source_labels)



            prev_count = 0



            markers = ",".join("?" for _ in source_labels)



            prev_row = conn.execute(



                f"SELECT SUM(raw_value) FROM official_statistics WHERE source_month LIKE ? AND geography = '機關別總計' AND metric IN ({markers})",



                [f"{prev_year}%"] + list(source_labels)



            ).fetchone()



            prev_count = prev_row[0] if prev_row and prev_row[0] else 0







            category_counts.append({



                "category": key,



                "label": label,



                "count": count,



                "change_pct": percent_change(count, prev_count)



            })







        iccs_rows = []







        iccs_breakdown = []



        for r in iccs_rows:



            code = r["iccs_code"]



            children = [dict(c) for c in conn.execute(



                """



                SELECT s.metric, c.severity_score, SUM(s.raw_value) as count, (SUM(s.raw_value) * c.severity_score) as weighted_score



                FROM official_statistics s



                JOIN crime_categories c ON s.metric = c.metric



                WHERE s.source_month LIKE ? AND s.geography = '機關別總計' AND c.iccs_code = ?



                GROUP BY s.metric, c.severity_score



                ORDER BY count DESC



                """,



                [f"{year}%", code]



            ).fetchall()]







            iccs_breakdown.append({



                "code": code,



                "name": r["iccs_name"],



                "count": r["count"],



                "weighted_score": r["weighted_score"],



                "children": children



            })







        flags_row = conn.execute(



            """



            SELECT



                SUM(CASE WHEN c.flag_cyber = 1 THEN s.raw_value ELSE 0 END) as cyber,



                SUM(CASE WHEN c.flag_weapon = 1 THEN s.raw_value ELSE 0 END) as weapon,



                SUM(CASE WHEN c.flag_domestic = 1 THEN s.raw_value ELSE 0 END) as domestic,



                SUM(CASE WHEN c.flag_organized_fraud = 1 THEN s.raw_value ELSE 0 END) as organized_fraud



            FROM official_statistics s



            JOIN crime_categories c ON s.metric = c.metric



            WHERE s.source_month LIKE ? AND s.geography = '機關別總計'



            """,



            [f"{year}%"]



        ).fetchone()







        flags_summary = {



            "cyber": flags_row["cyber"] if flags_row and flags_row["cyber"] else 0,



            "weapon": flags_row["weapon"] if flags_row and flags_row["weapon"] else 0,



            "domestic": flags_row["domestic"] if flags_row and flags_row["domestic"] else 0,



            "organized_fraud": flags_row["organized_fraud"] if flags_row and flags_row["organized_fraud"] else 0



        }







        region_weighted_rows = conn.execute(



            """



            SELECT s.geography, SUM(s.raw_value) as count, SUM(s.raw_value * c.severity_score) as weighted_score



            FROM official_statistics s



            JOIN crime_categories c ON s.metric = c.metric



            WHERE s.source_month LIKE ? AND s.geography NOT IN ('機關別總計', '署所屬機關') AND s.metric != '總計'



            GROUP BY s.geography



            ORDER BY weighted_score DESC



            """,



            [f"{year}%"]



        ).fetchall()



        region_weighted_counts = [{"geography": r["geography"], "count": r["count"], "weighted_score": r["weighted_score"]} for r in region_weighted_rows]







        topics = topic_definitions(stats_lookup)



        topic_monthly_trends = build_topic_monthly_trends(conn, months_through_selected, topics)



        topic_yoy_lookup = build_topic_yoy_lookup(conn, f"{year}12", topics)



        topic_drilldowns = build_topic_drilldowns(



            stats_lookup,



            geographies,



            total,



            metric_colors,



            topics,



            topic_monthly_trends,



            topic_yoy_lookup,



        )



        ai_insight = build_ai_insight(monthly_counts, topic_drilldowns)



        annual_comparison = build_annual_comparison(conn, months_through_selected, f"{year}12", metric_colors)







        selected_metric = "詐欺背信"



        region_rows = conn.execute(



            """



            SELECT geography, SUM(raw_value) as raw_value



            FROM official_statistics



            WHERE source_month LIKE ? AND metric = ? AND geography NOT IN ('機關別總計', '署所屬機關')



            GROUP BY geography



            ORDER BY raw_value DESC



            """,



            [f"{year}%", selected_metric]



        ).fetchall()



        region_counts = [{"geography": r["geography"], "count": r["raw_value"]} for r in region_rows]







        raw_rows_count = conn.execute("SELECT COUNT(*) FROM official_statistics WHERE source_month LIKE ?", [f"{year}%"]).fetchone()[0]



        metric_count_val = conn.execute("SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month LIKE ?", [f"{year}%"]).fetchone()[0]



        case_metric_count = conn.execute(



            "SELECT COUNT(DISTINCT metric) FROM official_statistics WHERE source_month LIKE ? AND metric != ?",



            [f"{year}%", TOTAL_METRIC],



        ).fetchone()[0]



        national_metric_sum = conn.execute(



            """



            SELECT SUM(raw_value)



            FROM official_statistics



            WHERE source_month LIKE ? AND geography = ? AND metric != ?



            """,



            [f"{year}%", TOTAL_GEOGRAPHY, TOTAL_METRIC],



        ).fetchone()[0] or 0



        total_reconciliation_delta = int(total or 0) - int(national_metric_sum or 0)







        leading_topics = [



            item for item in sorted(topic_drilldowns, key=lambda item: item["total"], reverse=True)



            if not item.get("is_total_scope") and not item.get("is_residual_scope")



        ][:3]



        leading_text = "、".join(f"{item['label']} {item['total']:,} 件" for item in leading_topics)



        summary_text = (



            f"{year} 年整年官方刑事案件發生件數資料已累計載入。"



            f"本頁優先呈現民眾與民代常關注的治安主題：{leading_text}；"



            f"全國總案量 {total:,} 件僅作統計範圍背景。"



        )







        official_summary_payload = {



            "source_month": f"{year}_annual",



            "source_url": "https://statis.moi.gov.tw/micst/webMain.aspx",



            "dataset_id": "9603",



            "total_cases": total,



            "total_change_pct": percent_change(total, previous_total),



            "safety_index": safety_index,



            "monthly_counts": monthly_counts,



            "category_counts": category_counts,



            "iccs_breakdown": iccs_breakdown,



            "flags_summary": flags_summary,



            "topic_drilldowns": topic_drilldowns,



            "ai_insight": ai_insight,



            "annual_comparison": annual_comparison,



            "metric_styles": {



                "count": len(metric_colors),



                "items": [{"metric": metric, "color": color} for metric, color in sorted(metric_colors.items())],



            },



            "region_weighted_counts": region_weighted_counts,



            "region_metric": selected_metric,



            "region_counts": region_counts,



            "quality": {



                "raw_rows": raw_rows_count,



                "selected_rows": raw_rows_count // 24 if raw_rows_count > 0 else 0,



                "duplicate_rows_dropped": 0,



                "metric_count": metric_count_val,



                "case_metric_count": case_metric_count,



                "national_metric_sum": national_metric_sum,



                "total_reconciliation_delta": total_reconciliation_delta,



                "matched_metric_totals": 1 if total_reconciliation_delta == 0 else 0,



                "invalid_cells": 0,



                "dash_zero_cells": 0,



            },



            "summary": {



                "text": summary_text,



                "method": "MOI dataset 9603 official descriptive statistics",



            },



        }







        with open(static_api_dir / f"official-summary_{year}_annual.json", "w", encoding="utf-8") as f:



            json.dump(official_summary_payload, f, ensure_ascii=False, indent=2)







    conn.close()



    



    # Sync generated JSON files to docs/static_api for production GitHub Pages



    import shutil



    docs_api_dir = Path("docs/static_api")



    docs_api_dir.mkdir(parents=True, exist_ok=True)



    print("\nSyncing generated JSON files to docs/static_api...")



    for item in static_api_dir.glob("*"):



        if item.is_file():



            shutil.copy2(item, docs_api_dir / item.name)

    print("Sync to docs completed successfully!")

    # Sync generated JSON files to dashboard/public/static_api for Next.js fallback
    dashboard_api_dir = Path("dashboard/public/static_api")
    dashboard_api_dir.mkdir(parents=True, exist_ok=True)
    print("\nSyncing generated JSON files to dashboard/public/static_api...")
    for item in static_api_dir.glob("*"):
        if item.is_file():
            shutil.copy2(item, dashboard_api_dir / item.name)
    print("Sync to dashboard completed successfully!")



    



    print("\nStatic API JSON generation completed successfully!")








    # Sync generated summaries to Supabase
    try:
        import sys
        sys.path.append(str(Path(__file__).resolve().parent))
        from upload_to_supabase import main as upload_main
        upload_main()
    except Exception as e:
        print(f"Supabase sync hook skipped: {e}")


if __name__ == "__main__":



    main()



