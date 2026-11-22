"""DAG 3 - Transformation & dimensional modelling (staging -> DuckDB star schema -> mart).

Tasks run strictly one after another because DuckDB allows a single writer.
extract -> dim_date -> dim_medicine (SCD2) -> dim_pharmacy -> dim_hospital -> small dims + junk
-> fact_sales -> fact_hospital_demand -> aggregates -> data-quality checks -> publish to Postgres
-> mark loads as transformed -> trigger the query layer and the storage metrics DAGs."""
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.operators.trigger_dagrun import TriggerDagRunOperator

from common.db import log_failure

DAG_ID = "p1_transform"
DEFAULT_ARGS = {"owner": "phase1", "retries": 2, "retry_delay": timedelta(seconds=30),
                "on_failure_callback": log_failure}


def _run(step, fn, context):
    """Open DuckDB, run one step, close it. Logs the step in ops.etl_step_log."""
    from common.db import logged_step
    from dwh import duck
    with logged_step(context["run_id"], DAG_ID, step) as st:
        con = duck.connect()
        try:
            st.rows = fn(con)
        finally:
            con.close()
    return st.rows


@dag(dag_id=DAG_ID, schedule=None, start_date=pendulum.datetime(2026, 1, 1, tz="UTC"), catchup=False,
     max_active_runs=1, default_args=DEFAULT_ARGS, tags=["phase1", "transform", "dwh"], doc_md=__doc__)
def p1_transform():
    @task
    def extract_staging(**context):
        from common.db import logged_step
        from dwh import duck, extract
        loads = extract.pending_loads()
        with logged_step(context["run_id"], DAG_ID, "extract_staging") as st:
            con = duck.connect()
            try:
                st.rows = sum(extract.extract_staging(con, loads).values())
            finally:
                con.close()
        return [l[0] for l in loads]                       # load_ids -> XCom

    @task
    def dim_date(**context):
        from dwh import transform
        return _run("dim_date", transform.load_dim_date, context)

    @task
    def dim_medicine_scd2(**context):
        from dwh import transform
        return _run("dim_medicine_scd2", transform.load_dim_medicine_scd2, context)

    @task
    def dim_pharmacy(**context):
        from dwh import transform
        return _run("dim_pharmacy", transform.load_dim_pharmacy, context)

    @task
    def dim_hospital(**context):
        from dwh import transform
        return _run("dim_hospital", transform.load_dim_hospital, context)

    @task
    def small_dims_and_junk(**context):
        from dwh import transform
        return _run("small_dims_and_junk", transform.load_small_dims, context)

    @task
    def fact_sales(**context):
        from dwh import transform
        return _run("fact_sales", transform.load_fact_sales, context)

    @task
    def fact_hospital_demand(**context):
        from dwh import transform
        return _run("fact_hospital_demand", transform.load_fact_hospital_demand, context)

    @task
    def aggregates(**context):
        from dwh import transform
        return _run("aggregates", transform.build_aggregates, context)

    @task
    def data_quality_checks(**context):
        from dwh import quality
        return _run("data_quality_checks", lambda con: quality.run_checks(con, context["run_id"]), context)

    @task
    def publish_marts(**context):
        from dwh import publish
        return _run("publish_marts", publish.publish_marts, context)

    @task
    def mark_loads_transformed(load_ids):
        from common.db import pg_conn
        if not load_ids:
            return 0
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE ops.batch_load_log SET transformed = TRUE, transformed_at = now() "
                        "WHERE load_id = ANY(%s)", (load_ids,))
        conn.close()
        return len(load_ids)

    trigger_queries = TriggerDagRunOperator(task_id="trigger_query_layer", trigger_dag_id="p1_query_layer",
                                            wait_for_completion=False)
    trigger_storage = TriggerDagRunOperator(task_id="trigger_storage_metrics", trigger_dag_id="p1_storage_metrics",
                                            wait_for_completion=False)

    loads = extract_staging()
    chain = [dim_date(), dim_medicine_scd2(), dim_pharmacy(), dim_hospital(), small_dims_and_junk(),
             fact_sales(), fact_hospital_demand(), aggregates(), data_quality_checks(), publish_marts()]
    loads >> chain[0]
    for a, b in zip(chain, chain[1:]):
        a >> b
    marked = mark_loads_transformed(loads)
    chain[-1] >> marked
    marked >> [trigger_queries, trigger_storage]


p1_transform()
