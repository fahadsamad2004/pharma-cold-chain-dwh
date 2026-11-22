"""Central configuration. Every value can be overridden with an environment variable
(docker-compose.yml sets them), so the same code runs in Docker and on your laptop."""
import os
from pathlib import Path

PG = dict(
    host=os.getenv("PG_HOST", "postgres"),
    port=int(os.getenv("PG_PORT", "5432")),
    dbname=os.getenv("PG_DB", "pharma"),
    user=os.getenv("PG_USER", "airflow"),
    password=os.getenv("PG_PASSWORD", "airflow"),
)

DATA_DIR = Path(os.getenv("DATA_DIR", "/opt/airflow/data"))
LANDING = DATA_DIR / "landing"      # drop files here -> watcher ingests them
ARCHIVE = DATA_DIR / "archive"      # successfully ingested files
REJECTED = DATA_DIR / "rejected"    # files whose load failed
RAW = DATA_DIR / "raw"              # the original 7 CSVs (history)
TMP = DATA_DIR / "tmp"              # generator writes here first, then renames into landing
GENERATED = DATA_DIR / "generated"  # CSV copies + stats of everything the generator produced

DUCKDB_PATH = os.getenv("DUCKDB_PATH", "/opt/airflow/warehouse/pharma_dwh.duckdb")
PARQUET_DIR = Path(os.getenv("PARQUET_DIR", "/opt/airflow/warehouse/parquet"))
INGEST_API_URL = os.getenv("INGEST_API_URL", "http://ingest-api:8000")

# Phase 1 only transforms these staging domains (others are loaded to staging but
# stay untouched until Phases 2 and 3).
PHASE1_DOMAINS = ("master", "sales", "hospital_demand")
