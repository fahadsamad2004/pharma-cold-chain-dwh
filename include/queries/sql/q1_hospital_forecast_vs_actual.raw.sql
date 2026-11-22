-- Dashboard widget: Hospital forecast vs actual consumption (ratio of sums, per hospital per month)
SELECT d.year_month, h.hospital_name,
       SUM(f.forecast_demand) AS forecast_packs, SUM(f.consumed_qty) AS consumed_packs,
       SUM(f.consumed_qty) * 1.0 / NULLIF(SUM(f.forecast_demand), 0) AS consumption_to_forecast_ratio
FROM fact_hospital_demand f
JOIN dim_date d ON d.date_key = f.month_date_key
JOIN dim_hospital h ON h.hospital_key = f.hospital_key
GROUP BY d.year_month, h.hospital_name
ORDER BY d.year_month, h.hospital_name;
