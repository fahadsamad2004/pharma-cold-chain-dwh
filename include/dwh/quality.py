"""Data-quality / reconciliation checks run after loading. Every check is written to
ops.dq_check_log; the task FAILS if any check fails (so bad data never goes unnoticed)."""
from common.db import pg_conn


def _check(results, name, expected, actual, passed, details=""):
    results.append((name, str(expected), str(actual), bool(passed), details))


def run_checks(con, run_id):
    r = []
    # 1. every NEW staged sale became a fact row (nothing silently dropped by a join)
    new_sales = con.execute("SELECT count(*) FROM stage.new_sales").fetchone()[0] if _exists(con, "new_sales") else 0
    orphan_sales = con.execute("""SELECT count(*) FROM stage.new_sales s WHERE NOT EXISTS
        (SELECT 1 FROM fact_sales f WHERE f.sales_transaction_id = s.salestransactionid)""").fetchone()[0] \
        if _exists(con, "new_sales") else 0
    _check(r, "sales: staged rows without a fact row (orphans)", 0, orphan_sales, orphan_sales == 0,
           f"{new_sales} new staged sales rows examined")
    new_dem = con.execute("SELECT count(*) FROM stage.new_demand").fetchone()[0] if _exists(con, "new_demand") else 0
    orphan_dem = con.execute("""SELECT count(*) FROM stage.new_demand s WHERE NOT EXISTS
        (SELECT 1 FROM fact_hospital_demand f WHERE f.hospital_demand_record_id = s.hospitaldemandrecordid)""").fetchone()[0] \
        if _exists(con, "new_demand") else 0
    _check(r, "hospital demand: staged rows without a fact row (orphans)", 0, orphan_dem, orphan_dem == 0,
           f"{new_dem} new staged demand rows examined")
    # 2. money reconciliation for this batch: staging net sales == fact net sales
    if new_sales:
        stg = con.execute("SELECT round(sum(TRY_CAST(netsalesamountusd AS DOUBLE)), 2) FROM stage.new_sales").fetchone()[0]
        fct = con.execute("""SELECT round(sum(f.net_sales), 2) FROM fact_sales f
            WHERE f.sales_transaction_id IN (SELECT salestransactionid FROM stage.new_sales)""").fetchone()[0]
        _check(r, "sales: net sales staging vs fact (this batch)", stg, fct, abs((stg or 0) - (fct or 0)) < 0.5)
    # 3. no sale may point at the Unknown medicine or Unknown pharmacy
    bad = con.execute("SELECT count(*) FROM fact_sales WHERE medicine_key = -1 OR pharmacy_key = -1").fetchone()[0]
    _check(r, "sales: facts pointing at Unknown medicine/pharmacy", 0, bad, bad == 0)
    # 4. SCD2 integrity: exactly one current version per medicine, no overlapping ranges
    cur_bad = con.execute("""SELECT count(*) FROM (SELECT medicine_id FROM dim_medicine WHERE medicine_key <> -1
        AND is_current GROUP BY 1 HAVING count(*) <> 1)""").fetchone()[0]
    overlap = con.execute("""SELECT count(*) FROM dim_medicine a JOIN dim_medicine b
        ON a.medicine_id = b.medicine_id AND a.medicine_key < b.medicine_key
        AND a.valid_from <= b.valid_to AND b.valid_from <= a.valid_to WHERE a.medicine_key <> -1""").fetchone()[0]
    _check(r, "dim_medicine: medicines without exactly 1 current version", 0, cur_bad, cur_bad == 0)
    _check(r, "dim_medicine: overlapping validity ranges", 0, overlap, overlap == 0)
    # 5. whole-history reconciliation: distinct ids in Postgres staging == rows in the facts
    pg = pg_conn()
    with pg.cursor() as cur:
        cur.execute("SELECT count(DISTINCT salestransactionid) FROM stg.sales")
        stg_sales = cur.fetchone()[0]
        cur.execute("SELECT count(DISTINCT hospitaldemandrecordid) FROM stg.hospital_demand")
        stg_dem = cur.fetchone()[0]
    fact_sales = con.execute("SELECT count(*) FROM fact_sales").fetchone()[0]
    fact_dem = con.execute("SELECT count(*) FROM fact_hospital_demand").fetchone()[0]
    _check(r, "TOTAL sales: distinct ids in staging vs rows in fact_sales", stg_sales, fact_sales,
           stg_sales == fact_sales, "only equal once every staged load has been transformed")
    _check(r, "TOTAL hospital demand: distinct ids in staging vs rows in fact", stg_dem, fact_dem,
           stg_dem == fact_dem)
    with pg, pg.cursor() as cur:
        for row in r:
            cur.execute("""INSERT INTO ops.dq_check_log (run_id, check_name, expected, actual, passed, details)
                           VALUES (%s,%s,%s,%s,%s,%s)""", (run_id, *row))
    pg.close()
    failed = [x for x in r if not x[3]]
    if failed:
        raise AssertionError("Data-quality checks failed: " + "; ".join(f"{x[0]} (expected {x[1]}, got {x[2]})" for x in failed))
    return len(r)


def _exists(con, table):
    return con.execute("SELECT count(*) FROM duckdb_tables() WHERE schema_name = 'stage' AND table_name = ?",
                       [table]).fetchone()[0] > 0
