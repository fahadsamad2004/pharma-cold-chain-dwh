-- Dashboard widget: Channel revenue split and gross margin % by month
SELECT d.year_month, c.channel_group, SUM(f.net_sales) AS net_revenue, SUM(f.gross_margin) AS gross_margin,
       SUM(f.gross_margin) / NULLIF(SUM(f.net_sales), 0) AS margin_pct, COUNT(*) AS transactions
FROM fact_sales f
JOIN dim_date d ON d.date_key = f.sale_date_key
JOIN dim_channel c ON c.channel_key = f.channel_key
GROUP BY d.year_month, c.channel_group
ORDER BY d.year_month, c.channel_group;
