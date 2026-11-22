"""Analytical query layer: runs the dashboard SQL, times every execution and logs it.

Naming convention in include/queries/sql/:
    <query_name>.raw.sql          straight over the star schema (facts + dimensions)
    <query_name>.opt.sql          over the pre-aggregated summary tables  ("optimized")
    <query_name>.partitioned.sql  over the Hive-partitioned Parquet copy (optional)

Two modes:
    dashboard_refresh : runs the OPTIMIZED version of every widget once - this is what a BI
                        dashboard does on refresh, so it feeds "daily active query count" and
                        "average execution time per widget".
    benchmark         : runs raw / optimized / partitioned several times to prove (with
                        numbers) that the optimizations work.
"""
import shutil
import time
from pathlib import Path

from psycopg2.extras import execute_values

from common.config import PARQUET_DIR
from common.db import pg_conn
from dwh.duck import connect

QUERY_DIR = Path(__file__).parent / "sql"
SUFFIX_TO_VARIANT = {"raw": "raw", "opt": "optimized", "partitioned": "partitioned"}


def discover():
    """{query_name: {variant: sql_text}}"""
    found = {}
    for f in sorted(QUERY_DIR.glob("*.sql")):
        name, suffix = f.name[:-4].rsplit(".", 1)
        found.setdefault(name, {})[SUFFIX_TO_VARIANT[suffix]] = f.read_text()
    return found


def export_partitioned_parquet(con):
    """Table partitioning: write fact_sales as Parquet files split into year=/month= folders."""
    target = PARQUET_DIR / "fact_sales"
    shutil.rmtree(target, ignore_errors=True)
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    con.execute(f"""COPY (SELECT f.*, d.calendar_year AS year, d.calendar_month AS month
                          FROM fact_sales f JOIN dim_date d ON d.date_key = f.sale_date_key)
                    TO '{target}' (FORMAT parquet, PARTITION_BY (year, month))""")
    return sum(1 for _ in target.rglob("*.parquet"))


def _timed(con, sql):
    """time.perf_counter() wrapper around the query execution -> (ms, rows, status, error)."""
    t = time.perf_counter()
    try:
        rows = len(con.execute(sql.replace("{parquet_dir}", str(PARQUET_DIR))).fetchall())
        return (time.perf_counter() - t) * 1000, rows, "success", None
    except Exception as exc:  # noqa: BLE001 - failures are data for the error-rate KPI
        return (time.perf_counter() - t) * 1000, 0, "failed", f"{type(exc).__name__}: {exc}"[:400]


def _log(records):
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        execute_values(cur, """INSERT INTO ops.query_log
            (run_id, query_name, variant, trigger_source, duration_ms, rows_returned, status, error)
            VALUES %s""", records)
    conn.close()


def run(run_id, mode="dashboard_refresh", repeats=1):
    variants = ["optimized"] if mode == "dashboard_refresh" else ["raw", "optimized", "partitioned"]
    con = connect(read_only=True)
    records = []
    for name, vmap in discover().items():
        for variant in variants:
            if variant not in vmap:
                continue
            for _ in range(repeats):
                ms, rows, status, err = _timed(con, vmap[variant])
                records.append((run_id, name, variant, mode, round(ms, 2), rows, status, err))
    con.close()
    _log(records)
    return len(records), sum(1 for r in records if r[6] == "failed")
