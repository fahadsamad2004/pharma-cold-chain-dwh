"""Publish the DuckDB marts to Postgres schema `mart`, so BI tools (Power BI, Superset,
Grafana, Metabase) can read them without fighting over DuckDB's single-writer file lock.
Full refresh of each table; DuckDB stays the build + analytical engine."""
import os
import tempfile

from common.db import pg_conn

TABLES = ["dim_date", "dim_medicine", "dim_pharmacy", "dim_hospital", "dim_channel",
          "dim_customer_segment", "dim_promotion", "dim_sales_junk", "dim_demand_status",
          "fact_sales", "fact_hospital_demand",
          "agg_sales_month_channel_medicine", "agg_hospital_month_disease"]

TYPE_MAP = {"BIGINT": "BIGINT", "INTEGER": "INTEGER", "DOUBLE": "DOUBLE PRECISION", "VARCHAR": "TEXT",
            "DATE": "DATE", "BOOLEAN": "BOOLEAN", "TIMESTAMP": "TIMESTAMP", "HUGEINT": "NUMERIC",
            "SMALLINT": "SMALLINT", "TINYINT": "SMALLINT", "FLOAT": "REAL"}


def _pg_type(duck_type):
    if duck_type.startswith("DECIMAL"):
        return "NUMERIC"
    return TYPE_MAP.get(duck_type, "TEXT")


def publish_marts(con):
    pg = pg_conn()
    total = 0
    for t in TABLES:
        cols = con.execute(f"DESCRIBE {t}").fetchall()
        ddl = ", ".join(f'"{c[0]}" {_pg_type(c[1])}' for c in cols)
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            con.execute(f"COPY {t} TO '{path}' (FORMAT csv, HEADER false)")
            with pg, pg.cursor() as cur:                       # one transaction per table
                cur.execute(f"DROP TABLE IF EXISTS mart.{t}")
                cur.execute(f"CREATE TABLE mart.{t} ({ddl})")
                with open(path) as fh:
                    cur.copy_expert(f"COPY mart.{t} FROM STDIN WITH (FORMAT csv)", fh)
                cur.execute(f"SELECT count(*) FROM mart.{t}")
                total += cur.fetchone()[0]
        finally:
            os.remove(path)
    pg.close()
    return total
