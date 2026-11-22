SELECT c.channel_group, SUM(f.net_sales) AS net_revenue, SUM(f.qty_sold) AS units
FROM read_parquet('{parquet_dir}/fact_sales/*/*/*.parquet', hive_partitioning = true) f
JOIN dim_channel c ON c.channel_key = f.channel_key
WHERE f.year = 2025
GROUP BY c.channel_group ORDER BY c.channel_group;
