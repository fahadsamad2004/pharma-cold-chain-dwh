"""Storage-layer metrics -> ops.storage_snapshot and ops.date_coverage (one batch per call,
all rows share the same captured_at so dashboards can show "the latest snapshot")."""
import os
import time

from psycopg2.extras import execute_values

from common.config import DUCKDB_PATH
from common.db import pg_conn
from dwh.duck import connect

DATE_CHECKS = [  # (domain, table, date_column, sql returning min_date, max_date, distinct_months)
    ("sales", "fact_sales", "sale_date",
     "SELECT min(d.full_date), max(d.full_date), count(DISTINCT d.year_month) FROM fact_sales f JOIN dim_date d ON d.date_key = f.sale_date_key"),
    ("hospital_demand", "fact_hospital_demand", "demand_month",
     "SELECT min(d.full_date), max(d.full_date), count(DISTINCT d.year_month) FROM fact_hospital_demand f JOIN dim_date d ON d.date_key = f.month_date_key"),
]


def new_timestamp():
    return time.strftime("%Y-%m-%d %H:%M:%S%z")


def collect_postgres(captured_at):
    """Row count + size of every staging table, and the whole database size."""
    conn = pg_conn()
    rows = []
    with conn, conn.cursor() as cur:
        cur.execute("SELECT tablename FROM pg_tables WHERE schemaname = 'stg' AND tablename <> 'rejected_rows' ORDER BY 1")
        for (t,) in cur.fetchall():
            cur.execute(f"SELECT count(*), pg_total_relation_size('stg.{t}') FROM stg.{t}")
            n, size = cur.fetchone()
            rows.append((captured_at, "staging", f"stg.{t}", t, n, round(size / 1048576, 2)))
        cur.execute("SELECT pg_database_size(current_database())")
        rows.append((captured_at, "postgres_db", "database:pharma", "all", None,
                     round(cur.fetchone()[0] / 1048576, 2)))
        execute_values(cur, "INSERT INTO ops.storage_snapshot VALUES %s", rows)
    conn.close()
    return len(rows)


def _domain_of(table):
    if table.startswith("dim_"):
        return "dimensions"
    if table.startswith("agg_"):
        return "aggregates"
    return table.replace("fact_", "")


def collect_duckdb(captured_at):
    """Row count of every warehouse table + physical size of the DuckDB file (os.path.getsize)."""
    con = connect(read_only=True)
    tables = [r[0] for r in con.execute("SELECT table_name FROM duckdb_tables() WHERE schema_name = 'main' ORDER BY 1").fetchall()]
    rows = [(captured_at, "dwh", t, _domain_of(t), con.execute(f"SELECT count(*) FROM {t}").fetchone()[0], None)
            for t in tables]
    con.close()
    size = sum(os.path.getsize(p) for p in (DUCKDB_PATH, DUCKDB_PATH + ".wal") if os.path.exists(p))
    rows.append((captured_at, "duckdb_file", os.path.basename(DUCKDB_PATH), "all", None, round(size / 1048576, 2)))
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        execute_values(cur, "INSERT INTO ops.storage_snapshot VALUES %s", rows)
    conn.close()
    return len(rows)


def collect_date_coverage(captured_at):
    """Is the 2023-2025 range fully represented? (min/max date + distinct year-months)."""
    con = connect(read_only=True)
    rows = []
    for domain, table, col, sql in DATE_CHECKS:
        mn, mx, months = con.execute(sql).fetchone()
        if mn is None:
            continue
        # expected: every month from 2023-01 to max(2025-12, last month seen)
        last = max((mx.year, mx.month), (2025, 12))
        expected = (last[0] - 2023) * 12 + last[1]
        rows.append((captured_at, domain, table, col, mn, mx, months, expected, round(100.0 * months / expected, 1)))
    con.close()
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        execute_values(cur, "INSERT INTO ops.date_coverage VALUES %s", rows)
    conn.close()
    return len(rows)
