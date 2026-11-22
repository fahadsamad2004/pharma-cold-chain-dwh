SELECT medicine_id, generic_name, therapeutic_class, disease_category, cold_chain_flag,
       SUM(units_sold) AS units_sold, SUM(net_sales) AS net_revenue
FROM agg_sales_month_channel_medicine
GROUP BY medicine_id, generic_name, therapeutic_class, disease_category, cold_chain_flag
ORDER BY units_sold DESC LIMIT 10;
