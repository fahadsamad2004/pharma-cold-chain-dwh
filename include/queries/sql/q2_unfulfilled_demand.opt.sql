SELECT hospital_name, disease_category,
       SUM(requested_qty) AS requested_packs, SUM(unfulfilled_demand) AS unfulfilled_packs,
       1 - SUM(unfulfilled_demand) * 1.0 / NULLIF(SUM(requested_qty), 0) AS fill_rate,
       SUM(stockout_days) AS stockout_days
FROM agg_hospital_month_disease
GROUP BY hospital_name, disease_category
ORDER BY unfulfilled_packs DESC;
