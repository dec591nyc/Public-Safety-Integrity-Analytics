# -*- coding: utf-8 -*-
"""ETL Package for Public Safety Integrity Analytics."""

from .config import (
    DATASET_ID, BASE_URL, BASE_PARAMS, CATEGORIES, CATEGORY_LABELS,
    DOMAIN_LABELS, OPINION_SOURCES, OFFICIAL_CATEGORY_MAP, TOTAL_GEOGRAPHY,
    TOTAL_METRIC, EXCLUDED_GEOGRAPHIES, TOPIC_COLORS, OFFICIAL_TOPIC_GROUPS
)
from .db import (
    get_connection, db_execute, db_executemany, db_fetch_all, init_db,
    sync_metric_styles, load_metric_colors, metric_color
)
from .extract import (
    parse_month, get_months_range, download_and_ingest_moi
)
from .transform import (
    percent_change, percent_of, row_to_dict, get_row_dict_list,
    topic_definitions, build_topic_yoy_lookup, build_topic_monthly_trends,
    build_topic_drilldowns, build_ai_insight, build_annual_comparison
)
from .load import (
    save_summary_report
)
