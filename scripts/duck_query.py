"""Run any SQL against the DuckDB warehouse (read-only) and print the result:
    docker compose exec airflow-scheduler python /opt/airflow/scripts/duck_query.py "SELECT count(*) FROM fact_sales"
Note: DuckDB only lets ONE process write at a time; this opens the file read-only, so don't run it
while the p1_transform DAG is running."""
import sys

sys.path.insert(0, "/opt/airflow/include")
from dwh.duck import connect  # noqa: E402

if len(sys.argv) < 2:
    sys.exit('usage: duck_query.py "SQL"')
con = connect(read_only=True)
cur = con.execute(sys.argv[1])
cols = [d[0] for d in cur.description]
rows = cur.fetchall()
print(" | ".join(cols))
for r in rows[:200]:
    print(" | ".join("" if v is None else str(v) for v in r))
print(f"({len(rows)} rows)")
