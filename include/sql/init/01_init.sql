-- Runs ONCE, the first time the Postgres container starts with an empty volume.
-- Creates the "pharma" database and the three schemas used by the pipeline:
--   stg  = staging / ODS (raw copies of the source files, all columns TEXT)
--   ops  = operational metrics (feeds the Grafana observability dashboards)
--   mart = published copy of the DuckDB star schema (feeds BI tools in Milestone 2)
CREATE DATABASE pharma;
\connect pharma

CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS ops;
CREATE SCHEMA IF NOT EXISTS mart;

-- ---------------------------------------------------------------- batch ingestion
CREATE TABLE IF NOT EXISTS ops.batch_load_log (
    load_id         TEXT PRIMARY KEY,
    file_name       TEXT,
    source_domain   TEXT,
    file_size_mb    NUMERIC,
    started_at      TIMESTAMPTZ,
    finished_at     TIMESTAMPTZ,
    duration_sec    NUMERIC,          -- Timestamp_end - Timestamp_start of the load
    rows_read       INTEGER,          -- len(df) summed over chunks
    rows_loaded     INTEGER,          -- rows that passed validation and were inserted
    rows_rejected   INTEGER,          -- rows that failed a validation rule
    status          TEXT,             -- 'success' | 'failed'
    error           TEXT,
    triggered_by    TEXT,
    transformed     BOOLEAN DEFAULT FALSE,
    transformed_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS stg.rejected_rows (
    load_id         TEXT,
    source_domain   TEXT,
    reason          TEXT,
    row_data        JSONB,
    rejected_at     TIMESTAMPTZ DEFAULT now()
);

-- ---------------------------------------------------------------- transformation / ETL
CREATE TABLE IF NOT EXISTS ops.etl_step_log (
    id            SERIAL PRIMARY KEY,
    run_id        TEXT,
    dag_id        TEXT,
    step          TEXT,
    started_at    TIMESTAMPTZ,
    finished_at   TIMESTAMPTZ,
    duration_sec  NUMERIC,
    rows_affected BIGINT,
    status        TEXT,
    error         TEXT
);

CREATE TABLE IF NOT EXISTS ops.dq_check_log (
    id          SERIAL PRIMARY KEY,
    run_id      TEXT,
    checked_at  TIMESTAMPTZ DEFAULT now(),
    check_name  TEXT,
    expected    TEXT,
    actual      TEXT,
    passed      BOOLEAN,
    details     TEXT
);

-- ---------------------------------------------------------------- query layer
CREATE TABLE IF NOT EXISTS ops.query_log (
    id             SERIAL PRIMARY KEY,
    run_id         TEXT,
    query_name     TEXT,
    variant        TEXT,              -- 'raw' | 'optimized' | 'partitioned'
    trigger_source TEXT,              -- 'dashboard_refresh' | 'benchmark'
    executed_at    TIMESTAMPTZ DEFAULT now(),
    duration_ms    NUMERIC,
    rows_returned  INTEGER,
    status         TEXT,              -- 'success' | 'failed'
    error          TEXT
);

-- ---------------------------------------------------------------- storage layer
CREATE TABLE IF NOT EXISTS ops.storage_snapshot (
    captured_at   TIMESTAMPTZ,
    layer         TEXT,               -- 'staging' | 'dwh' | 'postgres_db' | 'duckdb_file'
    table_name    TEXT,
    source_domain TEXT,
    row_count     BIGINT,
    size_mb       NUMERIC
);

CREATE TABLE IF NOT EXISTS ops.date_coverage (
    captured_at     TIMESTAMPTZ,
    domain          TEXT,
    table_name      TEXT,
    date_column     TEXT,
    min_date        DATE,
    max_date        DATE,
    distinct_months INTEGER,
    expected_months INTEGER,
    coverage_pct    NUMERIC
);

-- ---------------------------------------------------------------- generator
CREATE TABLE IF NOT EXISTS ops.generation_log (
    id             SERIAL PRIMARY KEY,
    run_id         TEXT,
    refresh_no     INTEGER,
    file_name      TEXT,
    source_domain  TEXT,
    rows_generated INTEGER,
    period_start   DATE,
    period_end     DATE,
    file_size_mb   NUMERIC,
    details        JSONB,
    generated_at   TIMESTAMPTZ DEFAULT now()
);

-- Convenience view: raw vs optimized timings per query (used by the query dashboard)
CREATE OR REPLACE VIEW ops.v_query_benchmark AS
SELECT query_name,
       ROUND(AVG(duration_ms) FILTER (WHERE variant = 'raw'), 2)         AS raw_ms,
       ROUND(AVG(duration_ms) FILTER (WHERE variant = 'optimized'), 2)   AS optimized_ms,
       ROUND(AVG(duration_ms) FILTER (WHERE variant = 'partitioned'), 2) AS partitioned_ms
FROM ops.query_log
WHERE status = 'success' AND trigger_source = 'benchmark'
GROUP BY query_name;

-- Read-only role for Grafana / BI tools (good practice: dashboards never need write access)
CREATE ROLE grafana_ro LOGIN PASSWORD 'grafana';
GRANT CONNECT ON DATABASE pharma TO grafana_ro;
GRANT USAGE ON SCHEMA ops, mart, stg TO grafana_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA ops, mart, stg TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA ops  GRANT SELECT ON TABLES TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA mart GRANT SELECT ON TABLES TO grafana_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA stg  GRANT SELECT ON TABLES TO grafana_ro;

-- ---------------------------------------------------------------- streaming ingestion
CREATE TABLE IF NOT EXISTS ops.stream_metrics (
    window_id TEXT, tick_no INTEGER, ts TIMESTAMPTZ DEFAULT now(), events_in INTEGER, events_ok INTEGER,
    events_bad INTEGER, tick_sec NUMERIC, throughput_eps NUMERIC, avg_latency_sec NUMERIC, max_latency_sec NUMERIC);
CREATE TABLE IF NOT EXISTS ops.stream_run_log (
    window_id TEXT PRIMARY KEY, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, duration_sec NUMERIC,
    total_in INTEGER, total_ok INTEGER, total_bad INTEGER, avg_throughput_eps NUMERIC, status TEXT, error TEXT);
