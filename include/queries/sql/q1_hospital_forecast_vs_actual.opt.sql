SELECT year_month, hospital_name,
       SUM(forecast_demand) AS forecast_packs, SUM(consumed_qty) AS consumed_packs,
       SUM(consumed_qty) * 1.0 / NULLIF(SUM(forecast_demand), 0) AS consumption_to_forecast_ratio
FROM agg_hospital_month_disease
GROUP BY year_month, hospital_name
ORDER BY year_month, hospital_name;
