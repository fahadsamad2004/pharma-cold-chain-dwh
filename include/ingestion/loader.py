"""Batch loader: reads one CSV/XLSX file, validates it, loads it into Postgres staging and
logs the metrics the "Batch Ingestion" dashboard needs (duration, rows, success).

Design notes:
  * Staging tables are RAW copies: every column is TEXT, plus audit columns
    _load_id, _loaded_at, _source_file. Type casting happens later, in the transform.
  * CSV files are read in chunks of 100k rows so the 218 MB sales file never has to
    fit in memory. The whole file is ONE transaction: it either loads fully or not at all.
  * Rows that fail validation go to stg.rejected_rows with the reason.
"""
import io
import json
import re
import time
import uuid
from pathlib import Path

import pandas as pd

from common.db import pg_conn
from ingestion.schemas import EXPECTED_COLUMNS, PREFIX_TO_DOMAIN
from ingestion.validate import check_schema, validate

CHUNK_ROWS = 100_000


def infer_domain(file_name):
    m = re.match(r"^(\d{2})_", file_name)
    return PREFIX_TO_DOMAIN.get(m.group(1)) if m else None


def _read_chunks(path: Path):
    """Yield DataFrames of strings with lower-case column names."""
    na = dict(keep_default_na=False, na_values=[""])
    if path.suffix.lower() in (".xlsx", ".xls"):
        frames = [pd.read_excel(path, dtype=str, **na)]
    elif path.suffix.lower() == ".csv":
        frames = pd.read_csv(path, dtype=str, chunksize=CHUNK_ROWS, low_memory=False, **na)
    else:
        raise ValueError(f"unsupported file type: {path.suffix}")
    for df in frames:
        df.columns = [str(c).strip().lower() for c in df.columns]
        yield df


def _ensure_table(cur, domain, cols):
    col_ddl = ", ".join(f'"{c}" TEXT' for c in cols)
    cur.execute(f"""CREATE TABLE IF NOT EXISTS stg.{domain} ({col_ddl},
                    _load_id TEXT, _loaded_at TIMESTAMPTZ DEFAULT now(), _source_file TEXT)""")
    cur.execute(f"CREATE INDEX IF NOT EXISTS ix_stg_{domain}_load ON stg.{domain} (_load_id)")


def _already_loaded(file_name):
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute("SELECT 1 FROM ops.batch_load_log WHERE file_name=%s AND status='success' LIMIT 1",
                    (file_name,))
        hit = cur.fetchone() is not None
    conn.close()
    return hit


def load_file(path_str, triggered_by="api"):
    path = Path(path_str)
    domain = infer_domain(path.name)
    if domain and _already_loaded(path.name):
        return {"status": "skipped", "file_name": path.name,
                "message": "this file name was already loaded successfully (idempotent skip)"}

    load_id = f"{domain or 'unknown'}_{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    t0 = time.time()
    status, error = "success", None
    rows_read = rows_loaded = rows_rejected = 0
    size_mb = round(path.stat().st_size / 1_048_576, 3) if path.exists() else None
    conn = None
    try:
        if domain is None:
            raise ValueError("unrecognised file name: expected 'NN_name.csv|xlsx' with NN between 01 and 07")
        expected = EXPECTED_COLUMNS[domain]
        conn = pg_conn()
        cur = conn.cursor()
        seen = set()
        first = True
        for df in _read_chunks(path):
            if first:
                check_schema(domain, list(df.columns), expected)
                _ensure_table(cur, domain, expected)
                first = False
            df = df[expected]                       # fixed column order
            rows_read += len(df)                    # len(df): the "rows processed" metric
            ok, reasons = validate(domain, df, seen)
            bad_df, good_df = df[~ok], df[ok]
            rows_rejected += len(bad_df)
            rows_loaded += len(good_df)
            if len(good_df):
                good_df = good_df.assign(_load_id=load_id, _source_file=path.name)
                buf = io.StringIO()
                good_df.to_csv(buf, index=False, header=False)
                buf.seek(0)
                cols = ", ".join(f'"{c}"' for c in good_df.columns)
                cur.copy_expert(f"COPY stg.{domain} ({cols}) FROM STDIN WITH (FORMAT csv)", buf)
            for idx, row in bad_df.iterrows():
                cur.execute("INSERT INTO stg.rejected_rows(load_id, source_domain, reason, row_data) "
                            "VALUES (%s,%s,%s,%s)",
                            (load_id, domain, reasons[idx], json.dumps(row.dropna().to_dict())))
        if first:  # file had a header but no rows
            raise ValueError("file contains no data rows")
        conn.commit()
    except Exception as exc:  # noqa: BLE001 - any unhandled error = failed batch
        if conn:
            conn.rollback()
        status = "failed"
        error = f"{type(exc).__name__}: {exc}"[:500]
        rows_loaded = 0
    finally:
        if conn:
            conn.close()

    t1 = time.time()
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO ops.batch_load_log
               (load_id, file_name, source_domain, file_size_mb, started_at, finished_at, duration_sec,
                rows_read, rows_loaded, rows_rejected, status, error, triggered_by)
               VALUES (%s,%s,%s,%s,to_timestamp(%s),to_timestamp(%s),%s,%s,%s,%s,%s,%s,%s)""",
            (load_id, path.name, domain or "unknown", size_mb, t0, t1, round(t1 - t0, 2),
             rows_read, rows_loaded, rows_rejected, status, error, triggered_by))
    conn.close()
    return {"status": status, "load_id": load_id, "file_name": path.name, "domain": domain,
            "rows_read": rows_read, "rows_loaded": rows_loaded, "rows_rejected": rows_rejected,
            "duration_sec": round(t1 - t0, 2), "error": error}
