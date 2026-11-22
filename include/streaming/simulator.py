"""Streaming ingestion simulator (feeds the "Streaming Ingestion" dashboard).

A live stream is imitated with MICRO-BATCHES: every second the simulator creates a few dozen IoT
sensor readings (schema of source file 07), validates them row by row and inserts the good ones
into Postgres staging (stg.iot). One metrics row per second is written to ops.stream_metrics.

Metrics (computed exactly as the project spec describes):
  * Throughput (events/sec)  = records ingested / length of the tick window (one micro-batch per second)
  * End-to-end latency (sec) = timestamp of DB insert - timestamp the event was created at the source
  * Malformed / dropped      = counter of rows that failed validation (null key, bad timestamp, duplicate)
A small share of rows (MALFORMED_SHARE) is deliberately broken so the counter has something to show.
"""
import io
import json
import random
import time
import uuid
from datetime import datetime, timedelta, timezone

import pandas as pd

from common.db import pg_conn
from ingestion.loader import _ensure_table
from ingestion.schemas import EXPECTED_COLUMNS
from ingestion.validate import validate

MALFORMED_SHARE = 0.015
DEVICES = [f"DEV-{i:03d}" for i in range(1, 41)]
ZONES = ["ZONE-A", "ZONE-B", "ZONE-C", "ZONE-D"]
DDL = """
CREATE TABLE IF NOT EXISTS ops.stream_metrics (
    window_id TEXT, tick_no INTEGER, ts TIMESTAMPTZ DEFAULT now(), events_in INTEGER, events_ok INTEGER,
    events_bad INTEGER, tick_sec NUMERIC, throughput_eps NUMERIC, avg_latency_sec NUMERIC, max_latency_sec NUMERIC);
CREATE TABLE IF NOT EXISTS ops.stream_run_log (
    window_id TEXT PRIMARY KEY, started_at TIMESTAMPTZ, finished_at TIMESTAMPTZ, duration_sec NUMERIC,
    total_in INTEGER, total_ok INTEGER, total_bad INTEGER, avg_throughput_eps NUMERIC, status TEXT, error TEXT);
"""


def _make_events(window_id, tick_no, n, rng):
    now = datetime.now(timezone.utc)
    rows = []
    for i in range(n):
        lag = rng.uniform(0.05, 2.5)                      # simulated network/gateway delay
        ev = now - timedelta(seconds=lag)
        temp = rng.gauss(5.0, 1.1) + (rng.uniform(4, 8) if rng.random() < 0.03 else 0)
        hum = rng.gauss(45, 6)
        breach = "Y" if temp > 8 or temp < 2 else "N"
        r = {c: None for c in EXPECTED_COLUMNS["iot"]}
        r.update(sensorreadingid=f"STR-{window_id}-{tick_no:04d}-{i:04d}", deviceid=rng.choice(DEVICES),
                 devicetype="TempHumiditySensor", assettype="Warehouse", warehouseid="WH-01",
                 storagezoneid=rng.choice(ZONES), eventtimestamputc=ev.strftime("%Y-%m-%d %H:%M:%S.%f"),
                 ingestiontimestamputc=None, eventsequencenumber=str(tick_no * 1000 + i),
                 temperaturec=f"{temp:.2f}", relativehumiditypct=f"{hum:.1f}", storagemintempc="2",
                 storagemaxtempc="8", maxhumiditypct="60", temperaturebreachflag=breach,
                 thresholdbreachflag=breach, readingquality="Good", sourcestream="simulated_stream")
        rows.append(r)
    df = pd.DataFrame(rows)
    # inject malformed rows: null key / null device / impossible timestamp
    for idx in rng.sample(range(n), max(1, int(n * MALFORMED_SHARE))) if n else []:
        kind = rng.choice(["key", "device", "ts"])
        if kind == "key":
            df.loc[idx, "sensorreadingid"] = None
        elif kind == "device":
            df.loc[idx, "deviceid"] = None
        else:
            df.loc[idx, "eventtimestamputc"] = "not-a-timestamp"
    return df, now


def run(duration_sec=60, rate_eps=40, seed=None):
    """Run one stream window. Returns the summary dict."""
    rng = random.Random(seed)
    window_id = time.strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:4]
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute(DDL)
        _ensure_table(cur, "iot", EXPECTED_COLUMNS["iot"])
    t_start = time.time()
    tot_in = tot_ok = tot_bad = 0
    status, error, seen = "success", None, set()
    try:
        tick_no = 0
        while time.time() - t_start < duration_sec:
            tick_no += 1
            t_tick = time.time()
            n = max(1, int(rng.gauss(rate_eps, rate_eps * 0.2)))
            df, _ = _make_events(window_id, tick_no, n, rng)
            ok, reasons = validate("iot", df, seen)
            good, bad = df[ok], df[~ok]
            with conn, conn.cursor() as cur:
                if len(good):
                    t_insert = datetime.now(timezone.utc)
                    good = good.assign(ingestiontimestamputc=t_insert.strftime("%Y-%m-%d %H:%M:%S.%f"),
                                       _load_id=f"stream_{window_id}", _source_file="stream")
                    buf = io.StringIO()
                    good.to_csv(buf, index=False, header=False)
                    buf.seek(0)
                    cols = ", ".join(f'"{c}"' for c in good.columns)
                    cur.copy_expert(f"COPY stg.iot ({cols}) FROM STDIN WITH (FORMAT csv)", buf)
                    lat = (t_insert - pd.to_datetime(good["eventtimestamputc"]).dt.tz_localize("UTC")).dt.total_seconds()
                    avg_l, max_l = float(lat.mean()), float(lat.max())
                else:
                    avg_l = max_l = None
                for idx, row in bad.iterrows():
                    cur.execute("INSERT INTO stg.rejected_rows(load_id, source_domain, reason, row_data) VALUES (%s,%s,%s,%s)",
                                (f"stream_{window_id}", "iot", reasons[idx], json.dumps(row.dropna().to_dict())))
                tick_sec = max(time.time() - t_tick, 0.001)
                cur.execute("""INSERT INTO ops.stream_metrics (window_id, tick_no, events_in, events_ok, events_bad,
                               tick_sec, throughput_eps, avg_latency_sec, max_latency_sec)
                               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (window_id, tick_no, len(df), len(good), len(bad), round(tick_sec, 3),
                             round(len(good) / max(1.0, tick_sec), 1), avg_l, max_l))
            tot_in += len(df); tot_ok += len(good); tot_bad += len(bad)
            time.sleep(max(0.0, 1.0 - (time.time() - t_tick)))        # one micro-batch per second
    except Exception as exc:  # noqa: BLE001
        status, error = "failed", f"{type(exc).__name__}: {exc}"[:500]
    t_end = time.time()
    with conn, conn.cursor() as cur:
        cur.execute("""INSERT INTO ops.stream_run_log VALUES (%s,to_timestamp(%s),to_timestamp(%s),%s,%s,%s,%s,%s,%s,%s)""",
                    (window_id, t_start, t_end, round(t_end - t_start, 2), tot_in, tot_ok, tot_bad,
                     round(tot_ok / max(t_end - t_start, 0.001), 1), status, error))
    conn.close()
    return {"window_id": window_id, "events_in": tot_in, "ok": tot_ok, "malformed": tot_bad,
            "duration_sec": round(t_end - t_start, 1), "status": status, "error": error}
