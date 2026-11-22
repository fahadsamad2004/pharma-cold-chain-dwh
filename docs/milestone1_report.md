# Phase 1 - Milestone 1 Report
**Sales & Demand Intelligence data mart: generator to query layer**

Course: Intelligent Data Architectures, Fall 2026 · Group Members: Fahad Samad & Rafay Zafar · Date: 22 Nov 2026

---

## 1. Scope

Phase 1 builds the *Sales & Demand Intelligence* (SDI) data mart from three of the seven source files:
`01_master_data` (63 medicines), `05_pharmacy_sales_data` (500,000 transactions, 2023-2025) and
`06_hospital_demand_data` (27,216 hospital-medicine-month rows, 12 hospitals). Milestone 1 covers every
layer up to and including the analytical query layer. Milestone 2 adds the BI dashboards and the
live-refresh demonstration.

| Spec item | Where it lives | Evidence |
|---|---|---|
| Data oversampling layer (2%) | `dags/p1_generate_data.py`, `include/generator/` | [Generation report (PDF)](reports/data_generation_report.pdf) |
| Batch ingestion dashboard (2%) | `include/ingestion/`, Grafana *1 - Batch Ingestion Monitor* | section 4 |
| Streaming ingestion dashboard (2%) | `include/streaming/`, `dags/p1_stream_ingest.py`, Grafana *4 - Streaming Ingestion Monitor* | section 5 |
| Storage dashboard (2%) | `include/metrics/storage.py`, Grafana *2 - Storage and Staging Monitor* | section 6 |
| Transformation and dimensional modelling (2.5%) | `include/dwh/`, `dags/p1_transform.py` | section 7 |
| Query layer and optimisation dashboard (2%) | `include/queries/`, Grafana *3 - Query Performance Monitor* | section 8 |
| Excel design file, Phase 1 (2.5%) | [`Milestone.1.SDI.DWH.Excel.xlsx`](../Milestone.1.SDI.DWH.Excel.xlsx) | section 9 |

## 2. End-to-end flow

1. **Oversampling.** The Airflow DAG `p1_generate_data` writes a new monthly batch for each source (as `.xlsx`) into `data/landing/`.
2. **Ingestion.** A Python file-watcher notices the file and calls the ingestion REST API, which validates it row by row and loads it into Postgres staging (`stg.*`). Every load is logged in `ops.batch_load_log`.
3. **Trigger.** `p1_ingest_monitor` runs every minute. When successfully loaded files are waiting and the landing folder has been quiet for 20 s, it triggers `p1_transform`.
4. **Transformation.** `p1_transform` builds/updates the DuckDB star schema (dimensions, then facts, then aggregates), runs data-quality checks, publishes the marts to Postgres (`mart.*`) and marks the loads as transformed. It then triggers `p1_query_layer` and `p1_storage_metrics`.
5. **Monitoring.** Each stage writes metrics to `ops.*` tables; four Grafana dashboards read them (5 s refresh).

New data is **appended** to the warehouse; nothing is ever emptied, so history accumulates across refreshes.

## 3. Data oversampling layer

*Goal:* simulate a live pipeline by producing realistic new records, enough to refresh the mart twice over different periods.

- **Refresh 1 = January 2026, Refresh 2 = February 2026** (history ends December 2025).
- **Sales (05):** 2025 had 180,000 rows, +9.09% on 2024. Projected 2026 = 196,364 rows, spread by calendar days: **16,677** rows (Jan) and **15,064** rows (Feb). Each new sale re-uses a real (pharmacy, warehouse lot, batch, medicine) combination from the last 180 days whose batch still has at least 30 days of shelf life; prices come from the current master data; discount, tax and COGS follow the formulas observed in the history; return and promotion rates are inherited from the sampled rows.
- **Hospital demand (06):** 12 hospitals × 63 medicines = **756** rows per month (the file's own grain). Values scale from the same month last year; opening stock equals the previous month's closing stock.
- **Master data (01):** 4 medicines per refresh receive a price rise (wholesale +4-10%, cost +2-5%) effective on the 1st of the month, which produces genuine SCD Type 2 history.
- Fixed random seed per refresh, so runs are reproducible. IDs continue the existing sequences.

Totals: **17,437 rows** (refresh 1) and **15,824 rows** (refresh 2). Full methodology and statistics: [data_generation_report.pdf](reports/data_generation_report.pdf).

## 4. Batch ingestion (file-watcher, API, staging, dashboard 1)

**Components** (`include/ingestion/`)
- `watcher.py` - polling file-watcher on `data/landing/`. It waits until a file stops growing, calls the API, then moves the file to `data/archive/` (success) or `data/rejected/` (failure).
- `api.py` - Flask REST API (`POST /ingest`, `GET /health`) running under gunicorn.
- `loader.py` - reads CSV (in 100k-row chunks) or XLSX, checks the schema, validates rows, bulk-loads good rows with `COPY`, writes rejected rows with their reason to `stg.rejected_rows`. Each file is **one transaction**: it loads fully or not at all. A file name that already loaded successfully is skipped (idempotent).
- `validate.py` - rules: non-null keys, price > 0, quantity > 0, valid date (2020-2030), non-negative demand quantities, no duplicate key inside a file. A schema mismatch or unknown file name fails the whole batch.

**Staging design:** raw copy, every column `TEXT` plus `_load_id`, `_loaded_at`, `_source_file`. Casting happens in the transform, so a malformed value can never block a load.

**Dashboard 1 - Batch Ingestion Monitor** (spec metrics in bold). All four dashboards share one design: dark theme, KPI tiles with trend sparklines and colour thresholds (green/orange/red), section rows, a time-range picker, a navigation bar linking the dashboards, and a dynamic *Insights* table that states the slowest/largest/most frequent items in words. This dashboard also has a *Source domain* filter.

| Panel | Metric / computation |
|---|---|
| Batch success rate % | **successful runs / attempted runs × 100** |
| Batches attempted, rows loaded, rows rejected, failed batches | counters from `ops.batch_load_log` |
| Load duration per file (horizontal bars) | **end timestamp - start timestamp** of each file load |
| Rows processed per batch (loaded vs rejected) | **`len(df)`** per chunk, summed |
| Recent batches, validation rejects by reason | audit tables |
| ETL step durations, data-quality checks | latest `p1_transform` run |

*Story the dashboard tells:* the 208 MB historical sales file dominates load time while the generated monthly files load in seconds; the rejected-rows tables show which rule fires and how often; a failed batch (e.g. wrong schema) is visible immediately and the file is quarantined in `data/rejected/`.

_[Insert screenshot of dashboard 1 here]_

## 5. Streaming ingestion (dashboard 4)

Streaming is simulated with **micro-batches, one per second** (`include/streaming/simulator.py`, DAG `p1_stream_ingest`, parameters `duration_sec`=60, `rate_eps`=40). Events follow the IoT schema of source file 07 and are validated and inserted into `stg.iot`. A small share (about 1.5%) of events is deliberately malformed so the dropped-record counter is exercised.

| Panel | Metric / computation |
|---|---|
| Stream throughput - line chart per tick | **records ingested / tick length (s)** |
| Avg and max end-to-end latency | **DB insert timestamp - event timestamp** |
| Malformed / dropped records (total, rate, per tick, by reason) | **counter incremented when row validation fails** |
| Stream windows table | one row per run: duration, records in/ok/bad, average throughput |

*Story:* throughput stays flat at the configured rate (pipeline stable), latency stays in the 1-2 s range driven by the simulated gateway delay, and the malformed counter shows the validation layer rejecting about 1-2% of the events without stopping the stream.

_[Insert screenshot of dashboard 4 here]_

## 6. Storage and staging (dashboard 2)

`p1_storage_metrics` snapshots, after every transform: row counts of every staging and warehouse table (`SELECT COUNT(*)`), Postgres size (`pg_total_relation_size`, `pg_database_size`), DuckDB file size (`os.path.getsize`) and date coverage (distinct year-months present vs expected from 2023-01).

| Panel | Metric |
|---|---|
| Staging rows, warehouse rows, Postgres MB, DuckDB MB | cumulative footprint |
| Storage breakdown by source domain (donuts: rows and MB) | share of each domain in staging |
| Warehouse table row counts | dimensions and facts |
| Cumulative rows over time | step growth after each refresh |
| Date coverage span and % | MIN/MAX date, distinct months |

*Story:* sales dominates storage; after refresh 1 and 2 the cumulative-rows line steps up (data is appended, not replaced); coverage shows the 2023-2025 range fully represented, with January 2026 and February 2026 added by the refreshes (January 2023 holds only a few rows in the source data).

_[Insert screenshot of dashboard 2 here]_

## 7. Transformation and dimensional modelling

Implemented in DuckDB (`include/dwh/`), orchestrated by `p1_transform` as a strictly sequential chain (DuckDB allows one writer):
`extract_staging -> dim_date -> dim_medicine_scd2 -> dim_pharmacy -> dim_hospital -> small_dims_and_junk -> fact_sales -> fact_hospital_demand -> aggregates -> data_quality_checks -> publish_marts -> mark_loads_transformed`.

**Star schema (fact constellation with conformed dimensions)**

| Table | Type | Notes |
|---|---|---|
| `fact_sales` | Transaction fact | grain: one sales transaction; degenerate key `sales_transaction_id`; append-only, idempotent (`NOT EXISTS` anti-join) |
| `fact_hospital_demand` | Periodic snapshot fact | grain: hospital × medicine × month |
| `dim_medicine` | **SCD Type 2** | tracks wholesale/retail price, unit cost, status, supplier, plant; `valid_from`, `valid_to`, `is_current`, `version_no`, `row_hash`; facts join the version valid on the sale date |
| `dim_pharmacy`, `dim_hospital` | SCD Type 1 | derived and de-duplicated from the sales and demand files |
| `dim_date` | **Role-playing** | views `dim_sale_date`, `dim_delivery_date`, `dim_expiry_date` |
| `dim_sales_junk`, `dim_demand_status` | **Junk dimensions** | low-cardinality flags folded into one key |
| `dim_channel`, `dim_customer_segment`, `dim_promotion` | Small dimensions | channel derived: E-commerce / Hospital / Retail |
| `agg_sales_month_channel_medicine`, `agg_hospital_month_disease` | Pre-aggregated summaries | rebuilt after each load |

Every dimension has an **unknown member (key -1)** so a fact row is never lost. Sales and hospital demand are never joined row-to-row; they are compared only after aggregating both to medicine × month.

**Data-quality gate (`quality.py`)** - the transform fails if any check fails: no orphan staged rows, staging vs fact net-sales reconciliation, no fact rows pointing to the unknown medicine/pharmacy, exactly one current version per medicine, no overlapping validity ranges, and total distinct-ID counts staging vs warehouse.

**Publish:** the marts are copied to Postgres `mart.*` so BI tools can read them without touching DuckDB.

## 8. Analytical query layer and optimisation (dashboard 3)

Seven business queries (`include/queries/sql/`), each written in up to three variants:

| Query | Business question |
|---|---|
| q1 | Hospital forecast vs actual consumption ratio |
| q2 | Unfulfilled demand analysis |
| q3 | Channel revenue split and gross margin (Retail vs Hospital vs E-commerce) |
| q4 / q5 | Top-10 fast-moving / slow-moving medicines |
| q6 | Velocity rank within each disease category |
| q7 | 2025 sales by channel (also partitioned variant) |

Variants: **raw** (over the star schema), **optimized** (over the pre-aggregated summary tables), **partitioned** (over Hive-partitioned Parquet `year=/month=`). `p1_query_layer` runs the optimised version of each widget (dashboard-refresh mode) and a benchmark of all variants, timing each with `time.perf_counter()` and logging success/failure.

**Measured result:** summary tables gave **3-7x** speed-ups on the large scans over `fact_sales`; the small hospital queries gained nothing (already milliseconds); Parquet partitioning was *not* faster at this data size. These numbers are reported as measured (see assumption 23). DuckDB is columnar, so zone maps and sorted inserts replace B-tree indexes.

**Dashboard 3 - Query Performance Monitor**

| Panel | Metric / computation |
|---|---|
| Daily active query count | counter incremented for every executed query |
| Query error rate % | **failed queries / total executed × 100** |
| Avg and slowest dashboard query (ms) | `time.perf_counter()` wrapper |
| Avg execution time per widget (columns) | find unoptimised widgets |
| Raw vs optimised vs partitioned | optimisation proof |
| Queries per hour, latest failed queries | usage and error log |

_[Insert screenshot of dashboard 3 here]_

## 9. Design workbook (Excel, Phase 1)

[`Milestone.1.SDI.DWH.Excel.xlsx`](../Milestone.1.SDI.DWH.Excel.xlsx) documents the design before implementation: business requirements X-ray, OLTP X-ray (13 source entities), transformation rules for every dimension attribute and fact measure, full dimension specifications (SCD strategy, hierarchies), both fact tables (grain, type, additivity, degenerate keys), the star schema diagram and three solvable dimensional queries. It matches the implemented schema in section 7, with one documented design choice: geography is a hierarchy (country > state > city) inside `dim_pharmacy` and `dim_hospital` rather than a separate `dim_geography` table.

## 10. Orchestration design (Airflow)

Six DAGs, each with one concern; DAG files only declare tasks and call functions in `include/` (modular, clean task separation). Failures write to `ops.etl_step_log` via an `on_failure_callback`; every pipeline step is wrapped by `logged_step`, which records start, end, duration, rows and status.

| DAG | Trigger | Purpose |
|---|---|---|
| `p1_generate_data` | manual (`refresh_no`) | oversampling |
| `p1_ingest_monitor` | every minute | detect new loads, trigger transform |
| `p1_transform` | by monitor | staging to star schema, quality gate, publish |
| `p1_query_layer` | by transform | timed queries, benchmark |
| `p1_storage_metrics` | by transform | storage snapshot |
| `p1_stream_ingest` | manual (`duration_sec`, `rate_eps`) | streaming simulation |

## 11. How to reproduce

See the [README](../README.md). Sequence: `make up`, `make seed`, trigger `p1_generate_data` with `refresh_no` 1 then 2, `make stream`, open the four Grafana dashboards, `make verify`.

## 12. Limitations and next steps

- Oversampling currently covers sources 01, 05 and 06; generators for 02, 03, 04 and 07 are added in Phases 2 and 3.
- The stream simulator produces synthetic IoT events; Phase 3 replays the real IoT file and applies temperature-range validation per medicine.
- Milestone 2: three BI dashboards (hospital forecast vs actual and unfulfilled demand; channel revenue and margin; fast vs slow movers) on `mart.*`, with the dashboard and mart refreshed at least twice in the demo.
