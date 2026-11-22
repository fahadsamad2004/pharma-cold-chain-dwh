SELECT channel_group, SUM(net_sales) AS net_revenue, SUM(units_sold) AS units
FROM agg_sales_month_channel_medicine
WHERE year_month >= '2025-01' AND year_month <= '2025-12'
GROUP BY channel_group ORDER BY channel_group;
