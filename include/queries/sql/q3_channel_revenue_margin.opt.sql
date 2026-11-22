SELECT year_month, channel_group, SUM(net_sales) AS net_revenue, SUM(gross_margin) AS gross_margin,
       SUM(gross_margin) / NULLIF(SUM(net_sales), 0) AS margin_pct, SUM(txn_count) AS transactions
FROM agg_sales_month_channel_medicine
GROUP BY year_month, channel_group
ORDER BY year_month, channel_group;
