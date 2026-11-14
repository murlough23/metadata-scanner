#!/usr/bin/env python3
"""Small metadata scanner for a MySQL database.

What it does:
  1. Connects to MySQL (retrying with backoff if the database isn't ready yet).
  2. Reads table and column metadata from information_schema.
  3. Profiles each table: exact row count and NULL count per column.
  4. Applies a few simple quality rules and records any issues found.
  5. Writes everything to a JSON report and logs a summary.

Settings come from environment variables (defaults match the practice container):
  DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME, OUTPUT_FILE

Usage:
  pip install mysql-connector-python
  python scan_metadata.py
"""
import argparse, json, logging, os, sys, time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

exclude_tables = {t.strip() for t in os.getenv("EXCLUDE_TABLES", "").split(",") if t.strip()}

import mysql.connector
from mysql.connector import Error

log = logging.getLogger("scanner")

CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", "changeme"),
}


def _s(value):
    """information_schema sometimes returns bytes; always work with text."""
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    return value


def quote(name):
    """Quote an identifier for use in SQL (names come from information_schema)."""
    return "`" + name.replace("`", "``") + "`"


def connect_with_retry(schema, max_attempts=5, base_delay=1):
    """Connect to MySQL, waiting longer after each failed attempt."""
    for attempt in range(1, max_attempts + 1):
        try:
            conn = mysql.connector.connect(**CONFIG)
            log.info("Connected to %s:%s/%s", CONFIG["host"], CONFIG["port"], schema)
            return conn
        except Error as exc:
            if attempt == max_attempts:
                log.error("Giving up after %d attempts: %s", attempt, exc)
                raise
            delay = base_delay * 2 ** (attempt - 1)
            log.warning("Connection attempt %d failed (%s); retrying in %ds", attempt, exc, delay)
            time.sleep(delay)


def fetch_schema(conn, schema):
    """Return {table_name: {"type": ..., "columns": [...]}} from information_schema."""
    sql = """
        SELECT c.table_name, t.table_type, c.column_name,
               c.data_type, c.is_nullable, c.column_key
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema AND t.table_name = c.table_name
        WHERE c.table_schema = %s
        ORDER BY c.table_name, c.ordinal_position
    """
    cur = conn.cursor()
    cur.execute(sql, (schema,))
    tables = {}
    for table, ttype, col, dtype, nullable, key in cur.fetchall():
        entry = tables.setdefault(_s(table), {"type": _s(ttype), "columns": []})
        entry["columns"].append({
            "name": _s(col),
            "data_type": _s(dtype),
            "nullable": _s(nullable) == "YES",
            "key": _s(key) or None,
        })
    cur.close()
    return tables


def profile_table(conn, schema, table, columns):
    """One query per table: total rows plus the NULL count of every column."""
    parts = ["COUNT(*)"] + [f"SUM({quote(c['name'])} IS NULL)" for c in columns] + [f"COUNT(DISTINCT {quote(c['name'])})" for c in columns]
    sql = f"SELECT {', '.join(parts)} FROM {quote(schema)}.{quote(table)}"
    cur = conn.cursor()
    cur.execute(sql)
    row = cur.fetchone()
    cur.close()
    row_count = int(row[0])
    n = len(columns)
    null_counts = row[1:1 + n]
    distinct_counts = row[1 + n:]
    for col, nulls, distincts in zip(columns, null_counts, distinct_counts):
        col["null_count"] = int(nulls or 0)  # SUM() is NULL when the table is empty
        col["null_pct"] = round(100 * col["null_count"] / row_count, 2) if row_count else None
        col["distinct_count"] = int(distincts or 0)
    return row_count


def estimate_row_count(conn, schema, table):
    """Alternative to profile_table() when 'fast' flag is True."""
    cur = conn.cursor()
    cur.execute(
        "SELECT table_rows FROM information_schema.tables "
        "WHERE table_schema = %s AND table_name = %s",
        (schema, table),
    )
    row = cur.fetchone()
    cur.close()
    return int(row[0] or 0)


def check_quality(info):
    """Simple rules; each returns a short issue code and detail."""
    issues = []
    if info["type"] == "BASE TABLE":
        if not any(c["key"] == "PRI" for c in info["columns"]):
            issues.append({"rule": "no_primary_key", "detail": "table has no primary key"})
        if info.get("row_count") == 0 and info.get("row_count_exact"):
            # table is only considered empty if we know the exact row count
            issues.append({"rule": "empty_table", "detail": "table has zero rows"})
        elif info.get("row_count"):
            for c in info["columns"]:
                # Only check these counts when not in fast mode
                if "null_count" in c:
                    if c["null_pct"] is not None and c["null_pct"] >= 50:
                        issues.append({"rule": "mostly_null_column",
                                    "detail": f"column {c['name']} is {c['null_pct']}% NULL"})
                    if c["distinct_count"] == info.get("row_count"):
                        issues.append({"rule": "cols_rows_equal",
                                    "detail": f"column {c['name']} count is equal to row count: {c['distinct_count']}"})
    return issues


def scan(conn, schema, fast=False):
    tables = fetch_schema(conn, schema)
    log.info("Found %d tables/views", len(tables))
    errors = 0
    for name, info in tables.items():
        if info["type"] != "BASE TABLE":
            log.info("Skipping profiling for %s (%s)", name, info["type"])
            info["issues"] = []
            continue
        elif name in exclude_tables:
            log.info("Excluding table %s (%s)", name, info["type"])
            info["issues"] = []
            continue
        try:
            if fast:
                info["row_count"] = estimate_row_count(conn, schema, name)
                info["row_count_exact"] = False
            else:
                info["row_count"] = profile_table(conn, schema, name, info["columns"])
                info["row_count_exact"] = True
            log.info("Profiled %s: %d rows (%s), %d columns", name, info["row_count"], 'Approximate' if fast else 'Exact', len(info["columns"]))
        except Error as exc:
            errors += 1
            info["error"] = str(exc)
            log.error("Could not profile %s: %s", name, exc)
        info["issues"] = check_quality(info)
    return tables, errors


def build_report(schema, tables, errors):
    """Summarize, and reconcile: every table found must be accounted for."""
    profiled = [t for t in tables.values() if "row_count" in t]
    base_tables = [t for t in tables.values() if t["type"] == "BASE TABLE"]
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "source": {"host": CONFIG["host"], "port": CONFIG["port"], "database": schema},
        "summary": {
            "tables_found": len(tables),
            "base_tables": len(base_tables),
            "profiled": len(profiled),
            "profiling_errors": errors,
            "reconciled": len(profiled) + errors == len(base_tables),
            "issues_found": sum(len(t["issues"]) for t in tables.values()),
        },
        "tables": tables,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Sample metadata scanner."
    )

    parser.add_argument(
        "--output", 
        type=str, 
        default="metadata_report.json",
        help="The name of the JSON file to write output to"
    )

    parser.add_argument(
        "-db", "--database", 
        type=str, 
        default="sakila", 
        help="The name of the database to connect to"
    )

    parser.add_argument(
        "--fast", 
        action='store_true',
        help="Fast table scanning instead of using COUNT(*)"
    )

    # 5. Parse the command line inputs
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    schema = args.database
    fast = args.fast
    try:
        conn = connect_with_retry(schema)
    except Error:
        return 1
    try:
        tables, errors = scan(conn, schema, fast)
    finally:
        conn.close()
    
    report = build_report(schema, tables, errors)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    s = report["summary"]
    log.info("Wrote %s: %d tables, %d issues, %d errors, reconciled=%s",
             args.output, s["tables_found"], s["issues_found"], s["profiling_errors"], s["reconciled"])
    return 1 if errors or not s["reconciled"] else 0


if __name__ == "__main__":
    sys.exit(main())