"""DAG 2 - Ingestion monitor (every minute).
The file-watcher + API load files into Postgres staging (that part is NOT inside Airflow because it
must react instantly). This DAG watches the ops.batch_load_log table: when there are successfully
loaded files that have not been transformed yet, and the landing folder has been quiet for a few
seconds, it triggers the p1_transform DAG."""

import pendulum
from airflow.decorators import dag
from airflow.operators.python import ShortCircuitOperator
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from common.db import log_failure

QUIET_SECONDS = 20


def _should_transform():
    from airflow.models import DagRun
    from airflow.utils.state import DagRunState

    from common.config import LANDING, PHASE1_DOMAINS
    from common.db import pg_conn

    if DagRun.find(dag_id="p1_transform", state=DagRunState.RUNNING) or \
            DagRun.find(dag_id="p1_transform", state=DagRunState.QUEUED):
        print("a transform is already running/queued -> skip")
        return False
    if any(p.suffix.lower() in (".csv", ".xlsx") for p in LANDING.glob("*")):
        print("files still waiting in landing -> wait")
        return False
    conn = pg_conn()
    with conn, conn.cursor() as cur:
        cur.execute("""SELECT count(*), coalesce(extract(epoch FROM now() - max(finished_at)), 9999)
                       FROM ops.batch_load_log
                       WHERE status = 'success' AND NOT transformed AND source_domain = ANY(%s)""",
                    (list(PHASE1_DOMAINS),))
        pending, idle = cur.fetchone()
        cur.execute("SELECT to_regclass('stg.master') IS NOT NULL")
        has_master = cur.fetchone()[0]
    conn.close()
    print(f"pending loads={pending}, seconds since last load={idle:.0f}, master staged={has_master}")
    return bool(pending) and idle >= QUIET_SECONDS and has_master


@dag(dag_id="p1_ingest_monitor", schedule="* * * * *", start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
     catchup=False, max_active_runs=1, default_args={"owner": "phase1", "retries": 0, "on_failure_callback": log_failure},
     tags=["phase1", "ingestion"], doc_md=__doc__)
def p1_ingest_monitor():
    check = ShortCircuitOperator(task_id="check_new_loads", python_callable=_should_transform)
    trigger = TriggerDagRunOperator(task_id="trigger_transform", trigger_dag_id="p1_transform",
                                    conf={"source": "p1_ingest_monitor"}, wait_for_completion=False)
    check >> trigger


p1_ingest_monitor()
