"""DAG - Streaming ingestion simulation (micro-batches, one per second) into Postgres staging.
Trigger manually; parameters: duration_sec (default 60) and rate_eps (default 40 events/sec).
Metrics land in ops.stream_metrics / ops.stream_run_log and feed the 'Streaming Ingestion Monitor' dashboard."""
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.models.param import Param

from common.db import log_failure


@dag(dag_id="p1_stream_ingest", schedule=None, start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
     catchup=False, tags=["phase1", "streaming"], doc_md=__doc__,
     default_args={"owner": "phase1", "retries": 0, "on_failure_callback": log_failure,
                   "execution_timeout": timedelta(minutes=15)},
     params={"duration_sec": Param(60, type="integer", minimum=10, maximum=600),
             "rate_eps": Param(40, type="integer", minimum=1, maximum=500)})
def p1_stream_ingest():
    @task
    def run_stream(**context):
        from streaming import simulator
        res = simulator.run(int(context["params"]["duration_sec"]), int(context["params"]["rate_eps"]))
        if res["status"] != "success":
            raise RuntimeError(res["error"])
        return res

    run_stream()


p1_stream_ingest()
