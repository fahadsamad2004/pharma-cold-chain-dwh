"""Ingestion REST API (Flask). The file watcher calls it; you can also call it by hand:

    curl -X POST localhost:8000/ingest -H 'Content-Type: application/json' \
         -d '{"file_path": "/opt/airflow/data/landing/01_master_data.csv"}'
"""
from pathlib import Path

from flask import Flask, jsonify, request

from common.config import DATA_DIR
from common.db import pg_conn
from ingestion.loader import load_file

app = Flask(__name__)


@app.get("/health")
def health():
    try:
        conn = pg_conn()
        conn.close()
        return jsonify(status="ok", database="reachable")
    except Exception as exc:  # noqa: BLE001
        return jsonify(status="degraded", database=str(exc)), 503


@app.post("/ingest")
def ingest():
    body = request.get_json(force=True, silent=True) or {}
    file_path = body.get("file_path")
    if not file_path:
        return jsonify(status="error", message="file_path is required"), 400
    p = Path(file_path).resolve()
    if DATA_DIR.resolve() not in p.parents:          # safety: only files under the data folder
        return jsonify(status="error", message="file must be inside the data directory"), 400
    if not p.is_file():
        return jsonify(status="error", message=f"file not found: {p.name}"), 404
    result = load_file(str(p), triggered_by=body.get("triggered_by", "api"))
    return jsonify(result), (200 if result["status"] in ("success", "skipped") else 422)


@app.get("/loads")
def loads():
    limit = min(int(request.args.get("limit", 20)), 200)
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute("""SELECT load_id, file_name, source_domain, status, rows_loaded, rows_rejected,
                              duration_sec, started_at FROM ops.batch_load_log
                       ORDER BY started_at DESC LIMIT %s""", (limit,))
        cols = [d[0] for d in cur.description]
        data = [dict(zip(cols, [str(v) if k == "started_at" else (float(v) if k == "duration_sec" and v is not None else v)
                                for k, v in zip(cols, r)])) for r in cur.fetchall()]
    conn.close()
    return jsonify(data)
