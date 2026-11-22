"""Prints the reconciliation numbers (staging vs warehouse):
staging (Postgres) vs warehouse (DuckDB). Run:  make verify"""
import sys

sys.path.insert(0, "/opt/airflow/include")
from common.db import pg_conn  # noqa: E402
from dwh.duck import connect  # noqa: E402

pg = pg_conn().cursor()
duck = connect(read_only=True)


def pg1(sql):
    pg.execute(sql)
    return pg.fetchone()[0]


rows = [
    ("sales rows (distinct ids)", pg1("SELECT count(DISTINCT salestransactionid) FROM stg.sales"),
     duck.execute("SELECT count(*) FROM fact_sales").fetchone()[0]),
    ("sales net revenue USD", round(float(pg1("SELECT sum(netsalesamountusd::numeric) FROM (SELECT DISTINCT ON (salestransactionid) * FROM stg.sales ORDER BY salestransactionid, _loaded_at DESC) s")), 2),
     round(duck.execute("SELECT sum(net_sales) FROM fact_sales").fetchone()[0], 2)),
    ("hospital demand rows", pg1("SELECT count(DISTINCT hospitaldemandrecordid) FROM stg.hospital_demand"),
     duck.execute("SELECT count(*) FROM fact_hospital_demand").fetchone()[0]),
    ("medicines (distinct ids)", pg1("SELECT count(DISTINCT medicineid) FROM stg.master"),
     duck.execute("SELECT count(DISTINCT medicine_id) FROM dim_medicine WHERE medicine_key <> -1").fetchone()[0]),
]
print(f"{'check':32s}{'staging':>16s}{'warehouse':>16s}   match")
for name, a, b in rows:
    print(f"{name:32s}{a:>16,}{b:>16,}   {'OK' if a == b else 'DIFFERENT'}")
print("\nSCD2 - medicines with more than one version:")
for r in duck.execute("""SELECT medicine_id, generic_name, version_no, wholesale_price_usd, retail_price_usd, valid_from, valid_to, is_current
                         FROM dim_medicine WHERE medicine_id IN (SELECT medicine_id FROM dim_medicine GROUP BY 1 HAVING count(*) > 1)
                         ORDER BY medicine_id, version_no""").fetchall():
    print("  ", r)
print("\nRevenue by channel:")
for r in duck.execute("""SELECT c.channel_group, count(*), round(sum(net_sales)) FROM fact_sales f
                         JOIN dim_channel c USING (channel_key) GROUP BY 1 ORDER BY 1""").fetchall():
    print("  ", r)
