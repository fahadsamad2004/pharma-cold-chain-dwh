"""DAG 1 - Data oversampling layer.
Trigger manually with the parameter refresh_no = 1 (Jan 2026) or 2 (Feb 2026).
Generates new batches for source files 01 (master), 05 (sales), 06 (hospital demand) and drops
them as .xlsx into data/landing/, where the file-watcher picks them up."""
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.models.param import Param

from common.db import log_failure

DEFAULT_ARGS = {"owner": "phase1", "retries": 1, "retry_delay": timedelta(seconds=20),
                "on_failure_callback": log_failure}


@dag(dag_id="p1_generate_data", schedule=None, start_date=pendulum.datetime(2026, 1, 1, tz="UTC"),
     catchup=False, default_args=DEFAULT_ARGS, tags=["phase1", "generator"],
     params={"refresh_no": Param(1, type="integer", minimum=1, maximum=12,
                                 description="1 = Jan 2026 refresh, 2 = Feb 2026 refresh")},
     doc_md=__doc__)
def p1_generate_data():
    @task
    def plan(**context):
        from generator import generate
        return generate.plan(int(context["params"]["refresh_no"]))

    @task
    def generate_master(p):
        from generator import generate
        return generate.generate_master(p["refresh_no"])

    @task
    def generate_sales(p, _master_done):          # needs the new prices from the master delta
        from generator import generate
        return generate.generate_sales(p["refresh_no"])

    @task
    def generate_hospital_demand(p):
        from generator import generate
        return generate.generate_hospital(p["refresh_no"])

    @task
    def log_generation_stats(p, master, sales, hospital, **context):
        from generator import generate
        return generate.log_generation(context["run_id"], p["refresh_no"], [master, sales, hospital])

    p = plan()
    m = generate_master(p)
    s = generate_sales(p, m)
    h = generate_hospital_demand(p)
    log_generation_stats(p, m, s, h)


p1_generate_data()
