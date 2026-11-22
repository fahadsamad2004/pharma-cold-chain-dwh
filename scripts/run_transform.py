"""Run the whole Phase 1 transform WITHOUT Airflow (handy for debugging):
    docker compose exec airflow-scheduler python /opt/airflow/scripts/run_transform.py
It does exactly what the p1_transform DAG does, step by step, in one process."""
import sys
import time

sys.path.insert(0, "/opt/airflow/include")
from common.db import logged_step, pg_conn  # noqa: E402
from dwh import duck, extract, publish, quality, transform  # noqa: E402


def main():
    run_id = "manual__" + time.strftime("%Y%m%dT%H%M%S")
    loads = extract.pending_loads()
    print("pending loads:", loads)
    con = duck.connect()
    steps = [("extract_staging", lambda: sum(extract.extract_staging(con, loads).values())),
             ("dim_date", lambda: transform.load_dim_date(con)),
             ("dim_medicine_scd2", lambda: transform.load_dim_medicine_scd2(con)),
             ("dim_pharmacy", lambda: transform.load_dim_pharmacy(con)),
             ("dim_hospital", lambda: transform.load_dim_hospital(con)),
             ("small_dims_and_junk", lambda: transform.load_small_dims(con)),
             ("fact_sales", lambda: transform.load_fact_sales(con)),
             ("fact_hospital_demand", lambda: transform.load_fact_hospital_demand(con)),
             ("aggregates", lambda: transform.build_aggregates(con)),
             ("data_quality_checks", lambda: quality.run_checks(con, run_id)),
             ("publish_marts", lambda: publish.publish_marts(con))]
    for name, fn in steps:
        with logged_step(run_id, "p1_transform", name) as st:
            st.rows = fn()
        print(f"{name:24s} rows={st.rows}")
    con.close()
    if loads:
        conn = pg_conn()
        with conn, conn.cursor() as cur:
            cur.execute("UPDATE ops.batch_load_log SET transformed=TRUE, transformed_at=now() WHERE load_id = ANY(%s)",
                        ([l[0] for l in loads],))
        conn.close()
    print("done")


if __name__ == "__main__":
    main()
