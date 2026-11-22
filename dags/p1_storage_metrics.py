"""DAG 5 - Storage layer metrics.
Triggered after every transform (or manually): table row counts, storage footprint (MB) and
date-coverage into ops.storage_snapshot / ops.date_coverage."""
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task

from common.db import log_failure


@dag(dag_id="p1_storage_metrics", schedule=None, start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
     catchup=False, max_active_runs=1,
     default_args={"owner": "phase1", "retries": 1, "retry_delay": timedelta(seconds=30),
                   "on_failure_callback": log_failure},
     tags=["phase1", "storage"], doc_md=__doc__)
def p1_storage_metrics():
    @task
    def start():
        from metrics import storage
        return storage.new_timestamp()

    @task
    def postgres_metrics(captured_at):
        from metrics import storage
        return storage.collect_postgres(captured_at)

    @task
    def duckdb_metrics(captured_at):
        from metrics import storage
        return storage.collect_duckdb(captured_at)

    @task
    def date_coverage(captured_at):
        from metrics import storage
        return storage.collect_date_coverage(captured_at)

    ts = start()
    postgres_metrics(ts)
    duckdb_metrics(ts)
    date_coverage(ts)


p1_storage_metrics()
