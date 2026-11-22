"""Dimension and fact loading steps. Each function takes an open DuckDB connection and
returns the number of rows it inserted, so Airflow can log it per step."""
from dwh.duck import count, run_sql


def load_dim_date(con):
    before = count(con, "dim_date")
    run_sql(con, "10_dim_date.sql")
    return count(con, "dim_date") - before


def load_dim_medicine_scd2(con):
    """Type 2 slowly changing dimension. Replays staged master rows in date order."""
    before = count(con, "dim_medicine")
    run_sql(con, "20_dim_medicine_stage.sql")
    n = con.execute("SELECT count(*) FROM stage.master_versions").fetchone()[0]
    for seq in range(1, n + 1):
        run_sql(con, "21_dim_medicine_close.sql", [seq])
        run_sql(con, "22_dim_medicine_insert.sql", [seq])
    return count(con, "dim_medicine") - before          # new versions created


def load_dim_pharmacy(con):
    before = count(con, "dim_pharmacy")
    run_sql(con, "30_dim_pharmacy.sql")
    return count(con, "dim_pharmacy") - before


def load_dim_hospital(con):
    before = count(con, "dim_hospital")
    run_sql(con, "31_dim_hospital.sql")
    return count(con, "dim_hospital") - before


def load_small_dims(con):
    tables = ["dim_customer_segment", "dim_promotion", "dim_sales_junk", "dim_demand_status"]
    before = sum(count(con, t) for t in tables)
    run_sql(con, "32_dim_small.sql")
    return sum(count(con, t) for t in tables) - before


def load_fact_sales(con):
    before = count(con, "fact_sales")
    run_sql(con, "40_fact_sales_new.sql")
    run_sql(con, "41_fact_sales_insert.sql")
    return count(con, "fact_sales") - before


def load_fact_hospital_demand(con):
    before = count(con, "fact_hospital_demand")
    run_sql(con, "42_fact_demand_new.sql")
    run_sql(con, "43_fact_demand_insert.sql")
    return count(con, "fact_hospital_demand") - before


def build_aggregates(con):
    run_sql(con, "50_aggregates.sql")
    return count(con, "agg_sales_month_channel_medicine") + count(con, "agg_hospital_month_disease")
