"""Prints a markdown table of everything the generator produced (paste it into your 1-2 page report):
    docker compose exec airflow-scheduler python /opt/airflow/scripts/generation_summary.py"""
import sys

sys.path.insert(0, "/opt/airflow/include")
from common.db import pg_conn  # noqa: E402

cur = pg_conn().cursor()
cur.execute("""SELECT refresh_no, file_name, source_domain, rows_generated, period_start, period_end, file_size_mb
               FROM ops.generation_log ORDER BY refresh_no, file_name""")
print("| Refresh | File | Domain | Rows | Period | Size (MB) |\n|---|---|---|---|---|---|")
total = 0
for r in cur.fetchall():
    total += r[3]
    print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:,} | {r[4]} to {r[5]} | {r[6]} |")
print(f"\nTotal rows generated: {total:,}")
