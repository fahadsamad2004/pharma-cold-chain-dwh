"""Small database helpers shared by every module."""
import time
import traceback
from contextlib import contextmanager

import psycopg2

from common.config import PG


def pg_conn():
    return psycopg2.connect(**PG)


class _Step:
    def __init__(self):
        self.rows = None


@contextmanager
def logged_step(run_id, dag_id, step):
    """Wrap a pipeline step: records start/end/duration/rows/status in ops.etl_step_log.

        with logged_step(run_id, "p1_transform", "fact_sales") as st:
            st.rows = load_fact_sales(con)
    """
    st = _Step()
    t0 = time.time()
    status, err = "success", None
    try:
        yield st
    except Exception as exc:  # noqa: BLE001 - we log and re-raise
        status, err = "failed", f"{type(exc).__name__}: {exc}"[:1000]
        raise
    finally:
        t1 = time.time()
        try:
            conn = pg_conn()
            with conn, conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO ops.etl_step_log
                       (run_id, dag_id, step, started_at, finished_at, duration_sec, rows_affected, status, error)
                       VALUES (%s,%s,%s,to_timestamp(%s),to_timestamp(%s),%s,%s,%s,%s)""",
                    (run_id, dag_id, step, t0, t1, round(t1 - t0, 2), st.rows, status, err),
                )
            conn.close()
        except Exception:  # never let logging hide the real error
            traceback.print_exc()


def log_failure(context):
    """Airflow on_failure_callback: write a row for the failed task instance."""
    ti = context.get("task_instance")
    try:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO ops.etl_step_log (run_id, dag_id, step, started_at, finished_at,
                       duration_sec, rows_affected, status, error)
                   VALUES (%s,%s,%s,now(),now(),0,NULL,'dag_task_failed',%s)""",
                (context.get("run_id"), ti.dag_id if ti else None,
                 f"TASK {ti.task_id}" if ti else "unknown", str(context.get("exception"))[:1000]),
            )
        conn.close()
    except Exception:
        traceback.print_exc()
