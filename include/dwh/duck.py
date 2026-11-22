"""DuckDB connection + helpers. DuckDB allows ONE writer process at a time, so every
Airflow task opens the file, does its work and closes it again."""
from pathlib import Path

import duckdb

from common.config import DUCKDB_PATH

SQL_DIR = Path(__file__).parent / "sql"


def connect(read_only=False):
    Path(DUCKDB_PATH).parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(DUCKDB_PATH, read_only=read_only)


def run_sql(con, filename, params=None):
    """Run a .sql file from include/dwh/sql (may hold several statements)."""
    sql = (SQL_DIR / filename).read_text()
    return con.execute(sql, params) if params is not None else con.execute(sql)


def count(con, table):
    return con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
