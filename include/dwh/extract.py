"""Step 1 of the transform: copy the NEW staging rows from Postgres into DuckDB's `stage`
schema, so every later step is plain SQL inside DuckDB.

'New' = rows belonging to successful loads that are not yet marked transformed."""
import os
import tempfile

from common.config import PHASE1_DOMAINS
from common.db import pg_conn
from dwh.duck import run_sql
from ingestion.schemas import EXPECTED_COLUMNS

AUDIT = ["_load_id", "_loaded_at", "_source_file"]


def pending_loads():
    """[(load_id, domain), ...] successful, not-yet-transformed Phase 1 loads."""
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute("""SELECT load_id, source_domain FROM ops.batch_load_log
                       WHERE status = 'success' AND NOT transformed AND source_domain = ANY(%s)
                       ORDER BY finished_at""", (list(PHASE1_DOMAINS),))
        rows = cur.fetchall()
    conn.close()
    return rows


def extract_staging(con, loads):
    """Rebuild stage.* from the given loads. Returns {domain: rows_extracted}."""
    run_sql(con, "00_ddl.sql")
    con.execute("DROP SCHEMA IF EXISTS stage CASCADE")
    con.execute("CREATE SCHEMA stage")
    pg = pg_conn()
    counts = {}
    for domain in PHASE1_DOMAINS:
        cols = EXPECTED_COLUMNS[domain] + AUDIT
        ddl = ", ".join(f'"{c}" VARCHAR' for c in cols)
        con.execute(f"CREATE TABLE stage.{domain} ({ddl})")          # always exists, may be empty
        ids = [lid for lid, dom in loads if dom == domain]
        counts[domain] = 0
        if not ids:
            continue
        select_cols = ", ".join(f'"{c}"' for c in cols)
        fd, path = tempfile.mkstemp(suffix=".csv")
        os.close(fd)
        try:
            with open(path, "w", newline="") as fh, pg.cursor() as cur:
                cur.copy_expert(
                    "COPY (SELECT " + select_cols + " FROM stg." + domain +
                    " WHERE _load_id = ANY(ARRAY[" + ",".join("'" + i + "'" for i in ids) + "])) "
                    "TO STDOUT WITH (FORMAT csv, HEADER true)", fh)
            con.execute(f"INSERT INTO stage.{domain} SELECT * FROM read_csv('{path}', header=true, "
                        f"all_varchar=true, quote='\"')")
            counts[domain] = con.execute(f"SELECT count(*) FROM stage.{domain}").fetchone()[0]
        finally:
            os.remove(path)
    pg.close()
    return counts
