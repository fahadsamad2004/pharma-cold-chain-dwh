"""Generates the four Grafana observability dashboards (JSON) from the SQL below.

    python grafana/build_dashboards.py

Every panel is a plain SQL query on the ops.* / stg.* tables (copy it to rebuild a panel by hand).
Design: dark theme, KPI tiles with sparklines, colour thresholds, section rows, a dynamic
"insights" table per dashboard, a navigation bar linking the four dashboards, and a time-range
picker (all log queries use $__timeFilter)."""
import json
from pathlib import Path

DS = {"type": "grafana-postgresql-datasource", "uid": "pharma-pg"}
OUT = Path(__file__).parent / "dashboards"
TAG = "pharma-phase1"
BLUE, GREEN, ORANGE, RED, PURPLE, TEAL, YELLOW = "#5794F2", "#73BF69", "#FF9830", "#F2495C", "#B877D9", "#4ECDC4", "#FADE2A"
_id = [0]


def _nid():
    _id[0] += 1
    return _id[0]


def _target(sql, fmt="table"):
    return [{"refId": "A", "datasource": DS, "format": fmt, "rawQuery": True, "editorMode": "code", "rawSql": sql}]


def _steps(*pairs):
    """_steps(('green', None), ('orange', 90), ...) -> threshold steps"""
    return {"mode": "absolute", "steps": [{"color": c, "value": v} for c, v in pairs]}


def fixed(colors):
    """Overrides that pin a colour to named series/fields."""
    return [{"matcher": {"id": "byName", "options": n},
             "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]} for n, c in colors.items()]


def _panel(ptype, title, sql, g, options=None, defaults=None, fmt="table", overrides=None, desc=""):
    return {"id": _nid(), "type": ptype, "title": title, "description": desc, "datasource": DS,
            "gridPos": {"x": g[0], "y": g[1], "w": g[2], "h": g[3]}, "targets": _target(sql, fmt),
            "options": options or {}, "fieldConfig": {"defaults": defaults or {}, "overrides": overrides or []}}


def row(title, y):
    return {"id": _nid(), "type": "row", "title": title, "collapsed": False, "panels": [], "gridPos": {"x": 0, "y": y, "w": 24, "h": 1}}


def text(md, g):
    return {"id": _nid(), "type": "text", "title": "", "gridPos": {"x": g[0], "y": g[1], "w": g[2], "h": g[3]},
            "options": {"mode": "markdown", "content": md}, "transparent": True}


def kpi(title, sql, g, unit=None, steps=None, decimals=None, desc="", color_mode="value"):
    """KPI tile with a sparkline. SQL must return a `time` column and ONE numeric column."""
    d = {"color": {"mode": "thresholds"}, "thresholds": steps or _steps((BLUE, None))}
    if unit:
        d["unit"] = unit
    if decimals is not None:
        d["decimals"] = decimals
    return _panel("stat", title, sql, g, desc=desc, defaults=d, fmt="time_series", options={
        "reduceOptions": {"calcs": ["lastNotNull"], "fields": "", "values": False}, "colorMode": color_mode,
        "graphMode": "area", "textMode": "value", "justifyMode": "auto", "orientation": "auto"})


def meter(title, sql, g, unit=None, steps=None, vmax=None, desc=""):
    """Horizontal gradient bars, one per row (name column + value column)."""
    d = {"color": {"mode": "thresholds"}, "thresholds": steps or _steps((BLUE, None)), "min": 0}
    if unit:
        d["unit"] = unit
    if vmax:
        d["max"] = vmax
    return _panel("bargauge", title, sql, g, desc=desc, defaults=d, options={
        "reduceOptions": {"values": True, "calcs": [], "fields": ""}, "orientation": "horizontal",
        "displayMode": "gradient", "valueMode": "color", "showUnfilled": True, "minVizHeight": 12, "minVizWidth": 8,
        "namePlacement": "top", "sizing": "auto", "text": {"titleSize": 12, "valueSize": 16}})


def bars(title, sql, g, xfield, horizontal=False, stacking="none", unit=None, colors=None, desc=""):
    d = {"color": {"mode": "palette-classic"}, "custom": {"fillOpacity": 85, "gradientMode": "hue", "lineWidth": 0}}
    if unit:
        d["unit"] = unit
    return _panel("barchart", title, sql, g, desc=desc, defaults=d, overrides=fixed(colors or {}), options={
        "orientation": "horizontal" if horizontal else "vertical", "xField": xfield, "xTickLabelRotation": 0,
        "showValue": "auto", "stacking": stacking, "groupWidth": 0.7, "barWidth": 0.9,
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True},
        "tooltip": {"mode": "multi", "sort": "none"}})


def donut(title, sql, g, unit=None, desc=""):
    d = {"color": {"mode": "palette-classic"}}
    if unit:
        d["unit"] = unit
    return _panel("piechart", title, sql, g, desc=desc, defaults=d, options={
        "pieType": "donut", "displayLabels": ["percent"], "reduceOptions": {"values": True, "calcs": [], "fields": ""},
        "legend": {"displayMode": "table", "placement": "right", "showLegend": True, "values": ["value", "percent"]},
        "tooltip": {"mode": "single"}})


def timeseries(title, sql, g, unit=None, colors=None, style="line", stacking="none", desc=""):
    custom = {"drawStyle": style, "lineWidth": 2, "fillOpacity": 30 if style == "line" else 80, "gradientMode": "opacity",
              "lineInterpolation": "smooth" if style == "line" else "linear", "showPoints": "auto", "spanNulls": True,
              "stacking": {"mode": stacking, "group": "A"}}
    d = {"color": {"mode": "palette-classic"}, "custom": custom}
    if unit:
        d["unit"] = unit
    return _panel("timeseries", title, sql, g, desc=desc, defaults=d, fmt="time_series", overrides=fixed(colors or {}), options={
        "legend": {"displayMode": "list", "placement": "bottom", "showLegend": True}, "tooltip": {"mode": "multi", "sort": "desc"}})


def table(title, sql, g, cell_colors=None, status_col=None, desc=""):
    """cell_colors: {column: thresholds} -> coloured cells; status_col: column with success/failed/true/false text."""
    ov = []
    for col, steps in (cell_colors or {}).items():
        ov.append({"matcher": {"id": "byName", "options": col}, "properties": [
            {"id": "custom.cellOptions", "value": {"type": "color-background", "mode": "gradient"}},
            {"id": "thresholds", "value": steps}, {"id": "color", "value": {"mode": "thresholds"}}]})
    if status_col:
        mp = {k: {"color": c, "text": k} for k, c in (("success", GREEN), ("failed", RED), ("true", GREEN), ("false", RED),
                                                       ("dag_task_failed", RED), ("Pass", GREEN), ("FAIL", RED))}
        ov.append({"matcher": {"id": "byName", "options": status_col}, "properties": [
            {"id": "custom.cellOptions", "value": {"type": "color-text"}},
            {"id": "mappings", "value": [{"type": "value", "options": mp}]}]})
    return _panel("table", title, sql, g, desc=desc, overrides=ov,
                  defaults={"custom": {"align": "auto", "cellOptions": {"type": "auto"}}},
                  options={"showHeader": True, "cellHeight": "sm"})


def dashboard(uid, title, panels, desc, variables=None, tags=None):
    return {"uid": uid, "title": title, "description": desc, "tags": [TAG] + (tags or []), "timezone": "browser",
            "schemaVersion": 39, "version": 2, "refresh": "5s", "time": {"from": "now-7d", "to": "now"},
            "style": "dark", "editable": True, "graphTooltip": 1, "panels": panels,
            "templating": {"list": variables or []}, "annotations": {"list": []},
            "links": [{"type": "dashboards", "tags": [TAG], "asDropdown": False, "includeVars": False, "keepTime": True,
                       "title": "Observability dashboards", "icon": "dashboard", "targetBlank": False}]}


GREEN_RED = _steps((RED, None), (ORANGE, 90), (GREEN, 99))
GOOD_BAD = _steps((GREEN, None), (ORANGE, 1), (RED, 5))
ZERO_OK = _steps((GREEN, None), (RED, 1))
INFO = "**How to read:** tiles show the latest value with its trend; colours follow thresholds (green = healthy, orange = watch, red = act). Hover the (i) icon on a tile for its definition. "


# =============================================================== 1. BATCH INGESTION
_id[0] = 0
DOM = "('$domain' = 'All' OR source_domain = '$domain')"
T = "$__timeFilter(started_at)"
batch_var = [{"name": "domain", "label": "Source domain", "type": "query", "datasource": DS, "refresh": 1, "sort": 1,
              "query": "SELECT 'All' AS domain UNION ALL SELECT DISTINCT source_domain FROM ops.batch_load_log WHERE source_domain IS NOT NULL",
              "definition": "SELECT 'All' AS domain UNION ALL SELECT DISTINCT source_domain FROM ops.batch_load_log",
              "current": {"text": "All", "value": "All"}, "options": [{"text": "All", "value": "All", "selected": True}],
              "includeAll": False, "multi": False}]
batch = dashboard("p1-batch", "1 - Batch Ingestion Monitor", [
    text(INFO + "Spec metrics: **Batch Load Duration** (end - start), **Rows Processed** (`len(df)`), **Batch Success Rate** (successful / attempted x 100). Use the *Source domain* filter and the time picker above.", (0, 0, 24, 2)),
    kpi("Success rate", f"SELECT started_at AS time, ROUND(100.0 * AVG((status = 'success')::int) OVER (ORDER BY started_at), 1) AS \"success %\" FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1",
        (0, 2, 4, 5), unit="percent", steps=GREEN_RED, desc="(successful runs / total attempted runs) x 100"),
    kpi("Batches", f"SELECT started_at AS time, COUNT(*) OVER (ORDER BY started_at) AS batches FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1", (4, 2, 4, 5)),
    kpi("Rows loaded", f"SELECT started_at AS time, SUM(rows_loaded) OVER (ORDER BY started_at) AS rows FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1",
        (8, 2, 4, 5), steps=_steps((GREEN, None)), unit="short"),
    kpi("Rows rejected", f"SELECT started_at AS time, SUM(rows_rejected) OVER (ORDER BY started_at) AS rejected FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1",
        (12, 2, 4, 5), steps=GOOD_BAD),
    kpi("Failed batches", f"SELECT started_at AS time, SUM((status = 'failed')::int) OVER (ORDER BY started_at) AS failed FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1",
        (16, 2, 4, 5), steps=ZERO_OK),
    kpi("Avg load time", f"SELECT started_at AS time, ROUND(AVG(duration_sec) OVER (ORDER BY started_at), 2) AS seconds FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1",
        (20, 2, 4, 5), unit="s", steps=_steps((GREEN, None), (ORANGE, 30), (RED, 120))),

    row("Load performance", 7),
    meter("Batch load duration per file (seconds)",
          f"SELECT regexp_replace(file_name, '\\.(csv|xlsx)$', '') AS file, duration_sec FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY started_at DESC LIMIT 12",
          (0, 8, 12, 9), unit="s", steps=_steps((GREEN, None), (ORANGE, 30), (RED, 120)),
          desc="Which file takes longest to read, parse and insert."),
    bars("Rows processed per batch: loaded vs rejected",
         f"SELECT regexp_replace(file_name, '\\.(csv|xlsx)$', '') AS file, rows_loaded, rows_rejected FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY started_at DESC LIMIT 12",
         (12, 8, 12, 9), "file", horizontal=True, stacking="normal", colors={"rows_loaded": GREEN, "rows_rejected": RED}),

    row("Reliability and data quality", 17),
    bars("Successful vs failed batches by domain (%)",
         f"SELECT source_domain, COUNT(*) FILTER (WHERE status = 'success') AS successful, COUNT(*) FILTER (WHERE status = 'failed') AS failed FROM ops.batch_load_log WHERE {T} GROUP BY 1 ORDER BY 1",
         (0, 18, 8, 9), "source_domain", stacking="percent", colors={"successful": GREEN, "failed": RED}),
    meter("Top validation reject reasons (rows)",
          "SELECT left(reason, 60) AS reason, COUNT(*) AS rows FROM stg.rejected_rows GROUP BY 1 ORDER BY 2 DESC LIMIT 8",
          (8, 18, 8, 9), steps=_steps((ORANGE, None), (RED, 100))),
    table("Domain scorecard",
          f"SELECT source_domain AS domain, COUNT(*) AS batches, ROUND(100.0 * AVG((status = 'success')::int), 1) AS success_pct, ROUND(AVG(duration_sec), 1) AS avg_sec, SUM(rows_loaded) AS rows FROM ops.batch_load_log WHERE {T} GROUP BY 1 ORDER BY 1",
          (16, 18, 8, 9), cell_colors={"success_pct": GREEN_RED, "avg_sec": _steps((GREEN, None), (ORANGE, 30), (RED, 120))}),

    row("Trends", 27),
    timeseries("Rows loaded per batch over time", f"SELECT started_at AS time, rows_loaded AS \"rows loaded\", rows_rejected AS \"rows rejected\" FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1",
               (0, 28, 12, 8), style="bars", colors={"rows loaded": GREEN, "rows rejected": RED}),
    timeseries("Load duration over time (s)", f"SELECT started_at AS time, duration_sec AS \"duration (s)\" FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY 1",
               (12, 28, 12, 8), unit="s", colors={"duration (s)": BLUE}),

    row("Details and insights", 36),
    table("Recent batches",
          f"SELECT started_at, file_name, source_domain AS domain, status, rows_read, rows_loaded, rows_rejected, duration_sec, left(error, 80) AS error FROM ops.batch_load_log WHERE {T} AND {DOM} ORDER BY started_at DESC LIMIT 15",
          (0, 37, 16, 9), status_col="status"),
    table("Insights",
          f"""SELECT 'Slowest load' AS insight, file_name || ' - ' || duration_sec || ' s' AS detail FROM (SELECT * FROM ops.batch_load_log WHERE {T} ORDER BY duration_sec DESC NULLS LAST LIMIT 1) a
              UNION ALL SELECT 'Largest load', file_name || ' - ' || rows_loaded || ' rows' FROM (SELECT * FROM ops.batch_load_log WHERE {T} ORDER BY rows_loaded DESC NULLS LAST LIMIT 1) b
              UNION ALL SELECT 'Most frequent reject', left(reason, 50) || ' (' || n || ')' FROM (SELECT reason, COUNT(*) n FROM stg.rejected_rows GROUP BY 1 ORDER BY 2 DESC LIMIT 1) c
              UNION ALL SELECT 'Failed batches', COUNT(*) FILTER (WHERE status = 'failed') || ' of ' || COUNT(*) FROM ops.batch_load_log WHERE {T}""",
          (16, 37, 8, 9)),
    bars("ETL step duration: latest transform run (s)",
         "SELECT step, duration_sec FROM ops.etl_step_log WHERE dag_id = 'p1_transform' AND run_id = (SELECT run_id FROM ops.etl_step_log WHERE dag_id = 'p1_transform' ORDER BY started_at DESC LIMIT 1) ORDER BY started_at",
         (0, 46, 12, 9), "step", horizontal=True, unit="s", colors={"duration_sec": TEAL}),
    table("Data-quality checks: latest run",
          "SELECT check_name, expected, actual, CASE WHEN passed THEN 'Pass' ELSE 'FAIL' END AS result FROM ops.dq_check_log WHERE run_id = (SELECT run_id FROM ops.dq_check_log ORDER BY id DESC LIMIT 1)",
          (12, 46, 12, 9), status_col="result"),
], "Batch ingestion: load duration, rows processed, success rate.", variables=batch_var, tags=["ingestion"])

# =============================================================== 2. STORAGE
_id[0] = 0
SNAP = "layer = 'staging'"
storage = dashboard("p1-storage", "2 - Storage and Staging Monitor", [
    text(INFO + "Spec metrics: **Table Row Count** (`SELECT COUNT(*)`), **Storage Footprint MB** (`pg_total_relation_size` / `os.path.getsize`), **Date Coverage Span** (distinct year-months vs expected). Snapshots are taken after every transform.", (0, 0, 24, 2)),
    kpi("Staging rows", "SELECT captured_at AS time, SUM(row_count) AS rows FROM ops.storage_snapshot WHERE layer = 'staging' AND $__timeFilter(captured_at) GROUP BY 1 ORDER BY 1", (0, 2, 4, 5), unit="short"),
    kpi("Warehouse rows", "SELECT captured_at AS time, SUM(row_count) AS rows FROM ops.storage_snapshot WHERE layer = 'dwh' AND table_name NOT LIKE 'agg_%' AND $__timeFilter(captured_at) GROUP BY 1 ORDER BY 1",
        (4, 2, 4, 5), unit="short", steps=_steps((GREEN, None))),
    kpi("Postgres size", "SELECT captured_at AS time, SUM(size_mb) AS mb FROM ops.storage_snapshot WHERE layer = 'postgres_db' AND $__timeFilter(captured_at) GROUP BY 1 ORDER BY 1",
        (8, 2, 4, 5), unit="decmbytes", decimals=1, steps=_steps((PURPLE, None))),
    kpi("DuckDB size", "SELECT captured_at AS time, SUM(size_mb) AS mb FROM ops.storage_snapshot WHERE layer = 'duckdb_file' AND $__timeFilter(captured_at) GROUP BY 1 ORDER BY 1",
        (12, 2, 4, 5), unit="decmbytes", decimals=1, steps=_steps((TEAL, None)), desc="os.path.getsize() of the DuckDB file"),
    kpi("Date coverage", "SELECT captured_at AS time, MIN(coverage_pct) AS pct FROM ops.date_coverage WHERE $__timeFilter(captured_at) GROUP BY 1 ORDER BY 1",
        (16, 2, 4, 5), unit="percent", steps=GREEN_RED, desc="distinct year-months present / months expected from 2023-01"),
    kpi("Domains staged", "SELECT captured_at AS time, COUNT(DISTINCT source_domain) AS domains FROM ops.storage_snapshot WHERE layer = 'staging' AND row_count > 0 AND $__timeFilter(captured_at) GROUP BY 1 ORDER BY 1",
        (20, 2, 4, 5), steps=_steps((BLUE, None))),

    row("Footprint by source domain", 7),
    donut("Storage breakdown: rows", "SELECT source_domain, row_count FROM ops.storage_snapshot WHERE layer = 'staging' AND captured_at = (SELECT MAX(captured_at) FROM ops.storage_snapshot)", (0, 8, 8, 9)),
    donut("Storage breakdown: MB", "SELECT source_domain, size_mb FROM ops.storage_snapshot WHERE layer = 'staging' AND captured_at = (SELECT MAX(captured_at) FROM ops.storage_snapshot)", (8, 8, 8, 9), unit="decmbytes"),
    meter("Warehouse table row counts (DuckDB)", "SELECT table_name, row_count FROM ops.storage_snapshot WHERE layer = 'dwh' AND captured_at = (SELECT MAX(captured_at) FROM ops.storage_snapshot) ORDER BY row_count DESC",
          (16, 8, 8, 9), steps=_steps((BLUE, None))),

    row("Growth after each refresh", 17),
    timeseries("Cumulative rows by layer", "SELECT captured_at AS time, layer AS metric, SUM(row_count) AS rows FROM ops.storage_snapshot WHERE layer IN ('staging', 'dwh') AND table_name NOT LIKE 'agg_%' AND $__timeFilter(captured_at) GROUP BY 1, 2 ORDER BY 1",
               (0, 18, 12, 8), colors={"staging": BLUE, "dwh": GREEN}),
    timeseries("Staging rows by source domain (stacked)", "SELECT captured_at AS time, source_domain AS metric, SUM(row_count) AS rows FROM ops.storage_snapshot WHERE layer = 'staging' AND $__timeFilter(captured_at) GROUP BY 1, 2 ORDER BY 1",
               (12, 18, 12, 8), stacking="normal"),

    row("Date coverage and insights", 26),
    table("Date coverage span", "SELECT domain, table_name, to_char(min_date, 'YYYY-MM-DD') AS min_date, to_char(max_date, 'YYYY-MM-DD') AS max_date, distinct_months, expected_months, coverage_pct FROM ops.date_coverage WHERE captured_at = (SELECT MAX(captured_at) FROM ops.date_coverage)",
          (0, 27, 16, 8), cell_colors={"coverage_pct": GREEN_RED}),
    table("Insights",
          """SELECT 'Largest staging domain' AS insight, source_domain || ' - ' || row_count || ' rows' AS detail FROM (SELECT * FROM ops.storage_snapshot WHERE layer = 'staging' AND captured_at = (SELECT MAX(captured_at) FROM ops.storage_snapshot) ORDER BY row_count DESC LIMIT 1) a
             UNION ALL SELECT 'Largest warehouse table', table_name || ' - ' || row_count || ' rows' FROM (SELECT * FROM ops.storage_snapshot WHERE layer = 'dwh' AND captured_at = (SELECT MAX(captured_at) FROM ops.storage_snapshot) ORDER BY row_count DESC LIMIT 1) b
             UNION ALL SELECT 'Latest snapshot', to_char(MAX(captured_at), 'YYYY-MM-DD HH24:MI') FROM ops.storage_snapshot
             UNION ALL SELECT 'Snapshots taken', COUNT(DISTINCT captured_at)::text FROM ops.storage_snapshot""",
          (16, 27, 8, 8)),
], "Storage layer: row counts, footprint, date coverage.", tags=["storage"])

# =============================================================== 3. QUERY PERFORMANCE
_id[0] = 0
QT = "$__timeFilter(executed_at)"
query = dashboard("p1-query", "3 - Query Performance Monitor", [
    text(INFO + "Spec metrics: **Query Execution Time** (`time.perf_counter()` wrapper), **Daily Active Query Count** (counter per executed query), **Query Error Rate** (failed / total x 100).", (0, 0, 24, 2)),
    kpi("Queries today", f"SELECT executed_at AS time, COUNT(*) OVER (PARTITION BY date_trunc('day', executed_at) ORDER BY executed_at) AS queries FROM ops.query_log WHERE {QT} ORDER BY 1", (0, 2, 4, 5),
        desc="queries executed so far today (counter incremented for every executed query)"),
    kpi("Error rate", f"SELECT executed_at AS time, ROUND(100.0 * AVG((status = 'failed')::int) OVER (ORDER BY executed_at), 2) AS \"error %\" FROM ops.query_log WHERE {QT} ORDER BY 1",
        (4, 2, 4, 5), unit="percent", steps=GOOD_BAD, desc="(failed queries / total executed queries) x 100"),
    kpi("Avg query time", f"SELECT executed_at AS time, ROUND(AVG(duration_ms) OVER (ORDER BY executed_at), 1) AS ms FROM ops.query_log WHERE status = 'success' AND trigger_source = 'dashboard_refresh' AND {QT} ORDER BY 1",
        (8, 2, 4, 5), unit="ms", steps=_steps((GREEN, None), (ORANGE, 500), (RED, 1000))),
    kpi("Slowest query", f"SELECT executed_at AS time, MAX(duration_ms) OVER (ORDER BY executed_at) AS ms FROM ops.query_log WHERE status = 'success' AND trigger_source = 'dashboard_refresh' AND {QT} ORDER BY 1",
        (12, 2, 4, 5), unit="ms", decimals=1, steps=_steps((GREEN, None), (ORANGE, 500), (RED, 1000))),
    kpi("Total queries", f"SELECT executed_at AS time, COUNT(*) OVER (ORDER BY executed_at) AS total FROM ops.query_log WHERE {QT} ORDER BY 1", (16, 2, 4, 5), steps=_steps((BLUE, None))),
    kpi("Best speed-up", "SELECT now() AS time, MAX(ROUND(raw_ms / NULLIF(optimized_ms, 0), 1)) AS speedup FROM ops.v_query_benchmark", (20, 2, 4, 5),
        unit="x", steps=_steps((ORANGE, None), (GREEN, 2)), desc="largest benefit of the summary tables"),

    row("Execution time per widget", 7),
    meter("Average execution time per dashboard widget (ms)",
          f"SELECT query_name AS widget, ROUND(AVG(duration_ms), 1) AS avg_ms FROM ops.query_log WHERE status = 'success' AND trigger_source = 'dashboard_refresh' AND {QT} GROUP BY 1 ORDER BY 2 DESC",
          (0, 8, 12, 9), unit="ms", steps=_steps((GREEN, None), (ORANGE, 500), (RED, 1000)), desc="Spot unoptimised joins or missing summary tables."),
    bars("Optimization proof: raw vs optimized vs partitioned (ms)", "SELECT split_part(query_name, '_', 1) AS query, raw_ms, optimized_ms, partitioned_ms FROM ops.v_query_benchmark ORDER BY 1",
         (12, 8, 12, 9), "query", unit="ms", colors={"raw_ms": RED, "optimized_ms": GREEN, "partitioned_ms": BLUE}),

    row("Usage and errors", 17),
    timeseries("Queries executed per hour", f"SELECT date_trunc('hour', executed_at) AS time, trigger_source AS metric, COUNT(*) AS queries FROM ops.query_log WHERE {QT} GROUP BY 1, 2 ORDER BY 1",
               (0, 18, 8, 8), style="bars", stacking="normal"),
    timeseries("Execution time trend per widget (ms)", f"SELECT executed_at AS time, split_part(query_name, '_', 1) AS metric, duration_ms FROM ops.query_log WHERE status = 'success' AND trigger_source = 'dashboard_refresh' AND {QT} ORDER BY 1",
               (8, 18, 8, 8), unit="ms"),
    donut("Executions by variant", f"SELECT variant, COUNT(*) AS runs FROM ops.query_log WHERE {QT} GROUP BY 1", (16, 18, 8, 8)),

    row("Benchmark detail and failures", 26),
    table("Speed-up per query", "SELECT query_name, raw_ms, optimized_ms, partitioned_ms, ROUND(raw_ms / NULLIF(optimized_ms, 0), 1) AS speedup_x FROM ops.v_query_benchmark ORDER BY 1",
          (0, 27, 12, 8), cell_colors={"speedup_x": _steps((ORANGE, None), (GREEN, 2))}),
    table("Latest failed queries", f"SELECT executed_at, query_name, variant, left(error, 120) AS error FROM ops.query_log WHERE status = 'failed' AND {QT} ORDER BY executed_at DESC LIMIT 10",
          (12, 27, 12, 8)),
], "Analytical query layer: execution time, query count, error rate.", tags=["query"])

# =============================================================== 4. STREAMING INGESTION
_id[0] = 0
ST = "$__timeFilter(ts)"
stream = dashboard("p1-stream", "4 - Streaming Ingestion Monitor", [
    text(INFO + "Spec metrics: **Stream Throughput** (events/sec), **End-to-End Latency** (DB insert time - event time), **Malformed / Dropped Records** (validation failures). Run a window with `make stream`.", (0, 0, 24, 2)),
    kpi("Throughput", f"SELECT ts AS time, throughput_eps AS \"events/s\" FROM ops.stream_metrics WHERE {ST} ORDER BY 1", (0, 2, 4, 5), unit="short", decimals=1,
        steps=_steps((ORANGE, None), (GREEN, 10)), desc="records ingested per second (latest tick)"),
    kpi("Events ingested", f"SELECT ts AS time, SUM(events_ok) OVER (ORDER BY ts) AS events FROM ops.stream_metrics WHERE {ST} ORDER BY 1", (4, 2, 4, 5), steps=_steps((GREEN, None))),
    kpi("Avg latency", f"SELECT ts AS time, ROUND(avg_latency_sec, 2) AS seconds FROM ops.stream_metrics WHERE avg_latency_sec IS NOT NULL AND {ST} ORDER BY 1",
        (8, 2, 4, 5), unit="s", steps=_steps((GREEN, None), (ORANGE, 3), (RED, 10)), desc="DB insert timestamp - source event timestamp"),
    kpi("Max latency", f"SELECT ts AS time, ROUND(max_latency_sec, 2) AS seconds FROM ops.stream_metrics WHERE max_latency_sec IS NOT NULL AND {ST} ORDER BY 1",
        (12, 2, 4, 5), unit="s", steps=_steps((GREEN, None), (ORANGE, 5), (RED, 15))),
    kpi("Dropped records", f"SELECT ts AS time, SUM(events_bad) OVER (ORDER BY ts) AS dropped FROM ops.stream_metrics WHERE {ST} ORDER BY 1",
        (16, 2, 4, 5), steps=_steps((GREEN, None), (ORANGE, 1), (RED, 500))),
    kpi("Malformed rate", f"SELECT ts AS time, ROUND(100.0 * SUM(events_bad) OVER (ORDER BY ts) / NULLIF(SUM(events_in) OVER (ORDER BY ts), 0), 2) AS \"malformed %\" FROM ops.stream_metrics WHERE {ST} ORDER BY 1",
        (20, 2, 4, 5), unit="percent", steps=GOOD_BAD),

    row("Throughput and latency", 7),
    timeseries("Stream throughput (events per second)", f"SELECT ts AS time, throughput_eps AS \"events/sec\" FROM ops.stream_metrics WHERE {ST} ORDER BY 1",
               (0, 8, 12, 9), colors={"events/sec": TEAL}, desc="Line chart over the simulation run: pipeline stability."),
    timeseries("End-to-end latency: average and maximum (s)", f"SELECT ts AS time, avg_latency_sec AS \"avg latency\", max_latency_sec AS \"max latency\" FROM ops.stream_metrics WHERE {ST} ORDER BY 1",
               (12, 8, 12, 9), unit="s", colors={"avg latency": BLUE, "max latency": ORANGE}),

    row("Data quality of the stream", 17),
    timeseries("Accepted vs malformed events per tick", f"SELECT ts AS time, events_ok AS accepted, events_bad AS malformed FROM ops.stream_metrics WHERE {ST} ORDER BY 1",
               (0, 18, 10, 8), style="bars", stacking="normal", colors={"accepted": GREEN, "malformed": RED}),
    meter("Malformed record reasons", "SELECT left(reason, 55) AS reason, COUNT(*) AS rows FROM stg.rejected_rows WHERE load_id LIKE 'stream_%' GROUP BY 1 ORDER BY 2 DESC LIMIT 8",
          (10, 18, 8, 8), steps=_steps((ORANGE, None), (RED, 50))),
    donut("Accepted vs dropped (all windows)", "SELECT 'accepted' AS outcome, COALESCE(SUM(total_ok), 0) AS events FROM ops.stream_run_log UNION ALL SELECT 'dropped', COALESCE(SUM(total_bad), 0) FROM ops.stream_run_log",
          (18, 18, 6, 8)),

    row("Stream windows and insights", 26),
    table("Stream windows", "SELECT started_at, window_id, duration_sec, total_in, total_ok, total_bad, avg_throughput_eps, status FROM ops.stream_run_log ORDER BY started_at DESC LIMIT 10",
          (0, 27, 16, 8), status_col="status"),
    table("Insights",
          """SELECT 'Windows run' AS insight, COUNT(*)::text AS detail FROM ops.stream_run_log
             UNION ALL SELECT 'Peak throughput', ROUND(MAX(throughput_eps), 1) || ' events/s' FROM ops.stream_metrics
             UNION ALL SELECT 'Worst latency', ROUND(MAX(max_latency_sec), 2) || ' s' FROM ops.stream_metrics
             UNION ALL SELECT 'Overall malformed rate', ROUND(100.0 * SUM(total_bad) / NULLIF(SUM(total_in), 0), 2) || ' %' FROM ops.stream_run_log""",
          (16, 27, 8, 8)),
], "Streaming ingestion: throughput, end-to-end latency, malformed records.", tags=["streaming"])

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for fname, dash in [("1_batch_ingestion.json", batch), ("2_storage.json", storage), ("3_query_performance.json", query), ("4_streaming_ingestion.json", stream)]:
        (OUT / fname).write_text(json.dumps(dash, indent=1))
        print("wrote", fname, len(dash["panels"]), "panels")
