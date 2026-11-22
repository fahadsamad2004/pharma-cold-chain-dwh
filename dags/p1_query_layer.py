"""DAG 4 - Analytical query layer.
Triggered after every transform (or manually). Writes a partitioned Parquet copy of fact_sales,
benchmarks raw vs optimized vs partitioned SQL, then runs every dashboard query once as a BI
refresh would. Every execution is timed and logged in ops.query_log."""
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task

from common.db import log_failure


@dag(dag_id="p1_query_layer", schedule=None, start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
     catchup=False, max_active_runs=1,
     default_args={"owner": "phase1", "retries": 1, "retry_delay": timedelta(seconds=30),
                   "on_failure_callback": log_failure},
     tags=["phase1", "query"], doc_md=__doc__)
def p1_query_layer():
    @task
    def export_partitioned_parquet(**context):
        from common.db import logged_step
        from dwh.duck import connect
        from queries import runner
        with logged_step(context["run_id"], "p1_query_layer", "export_partitioned_parquet") as st:
            con = connect(read_only=True)
            try:
                st.rows = runner.export_partitioned_parquet(con)   # number of parquet files
            finally:
                con.close()
        return st.rows

    @task
    def benchmark_queries(_prev, **context):
        from common.db import logged_step
        from queries import runner
        with logged_step(context["run_id"], "p1_query_layer", "benchmark_queries") as st:
            st.rows, failed = runner.run(context["run_id"], "benchmark", repeats=3)
        return {"queries_run": st.rows, "failed": failed}

    @task
    def dashboard_refresh_queries(_prev, **context):
        from common.db import logged_step
        from queries import runner
        with logged_step(context["run_id"], "p1_query_layer", "dashboard_refresh_queries") as st:
            st.rows, failed = runner.run(context["run_id"], "dashboard_refresh")
        return {"queries_run": st.rows, "failed": failed}

    dashboard_refresh_queries(benchmark_queries(export_partitioned_parquet()))


p1_query_layer()
