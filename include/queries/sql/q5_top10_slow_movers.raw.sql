-- Dashboard widget: Top 10 slow-moving medicines (fewest units sold)
SELECT m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category, m.cold_chain_flag,
       SUM(f.qty_sold) AS units_sold, SUM(f.net_sales) AS net_revenue
FROM fact_sales f JOIN dim_medicine m ON m.medicine_key = f.medicine_key
GROUP BY m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category, m.cold_chain_flag
ORDER BY units_sold ASC LIMIT 10;
