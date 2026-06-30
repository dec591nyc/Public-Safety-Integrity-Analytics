#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Synchronize stable colors for official MOI crime metric labels."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add current scripts directory to sys.path to allow importing etl
sys.path.append(str(Path(__file__).resolve().parent))
from etl import get_connection, sync_metric_styles

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=Path("data/local/public_safety.sqlite"))
    args = parser.parse_args()
    
    conn, db_type = get_connection(args.db)
    try:
        count = sync_metric_styles(conn, db_type)
        print(f"Synced {count} official metric styles into {args.db} ({db_type})")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
