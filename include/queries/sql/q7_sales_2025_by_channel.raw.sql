-- Date-filtered widget: 2025 sales by channel. Shows the effect of table partitioning:
--   raw         = scans the whole fact table
--   optimized   = reads the small summary table
--   partitioned = reads only the year=2025 folders of the partitioned Parquet copy
SELECT c.channel_group, SUM(f.net_sales) AS net_revenue, SUM(f.qty_sold) AS units
FROM fact_sales f JOIN dim_channel c ON c.channel_key = f.channel_key
WHERE f.sale_date_key BETWEEN 20250101 AND 20251231
GROUP BY c.channel_group ORDER BY c.channel_group;
