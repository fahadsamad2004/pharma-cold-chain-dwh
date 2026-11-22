-- Dashboard widget: Unfulfilled demand and fill rate by hospital and disease category
SELECT h.hospital_name, m.disease_category,
       SUM(f.requested_qty) AS requested_packs, SUM(f.unfulfilled_demand) AS unfulfilled_packs,
       1 - SUM(f.unfulfilled_demand) * 1.0 / NULLIF(SUM(f.requested_qty), 0) AS fill_rate,
       SUM(f.stockout_days) AS stockout_days
FROM fact_hospital_demand f
JOIN dim_hospital h ON h.hospital_key = f.hospital_key
JOIN dim_medicine m ON m.medicine_key = f.medicine_key
GROUP BY h.hospital_name, m.disease_category
ORDER BY unfulfilled_packs DESC;
