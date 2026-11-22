-- PRE-AGGREGATED SUMMARY TABLES (query optimization). They are derived data: rebuilt in full
-- from the facts after every load, so they never drift. The facts keep all history.
CREATE OR REPLACE TABLE agg_sales_month_channel_medicine AS
SELECT d.year_month, d.first_day_of_month AS month_start, c.channel_group,
       m.medicine_id, m.generic_name, m.therapeutic_class, m.disease_category, m.cold_chain_flag,
       count(*) AS txn_count, sum(f.qty_sold) AS units_sold, sum(f.gross_sales) AS gross_sales,
       sum(f.discount_amount) AS discount_amount, sum(f.net_sales) AS net_sales, sum(f.cogs) AS cogs,
       sum(f.gross_margin) AS gross_margin, sum(f.returned_qty) AS returned_units
FROM fact_sales f
JOIN dim_date d ON d.date_key = f.sale_date_key
JOIN dim_channel c ON c.channel_key = f.channel_key
JOIN dim_medicine m ON m.medicine_key = f.medicine_key
GROUP BY ALL;

CREATE OR REPLACE TABLE agg_hospital_month_disease AS
SELECT d.year_month, d.first_day_of_month AS month_start, h.hospital_id, h.hospital_name, h.hospital_type,
       m.disease_category, count(*) AS record_count,
       sum(f.forecast_demand) AS forecast_demand, sum(f.requested_qty) AS requested_qty,
       sum(f.approved_qty) AS approved_qty, sum(f.received_qty) AS received_qty,
       sum(f.dispensed_qty) AS dispensed_qty, sum(f.consumed_qty) AS consumed_qty,
       sum(f.wastage_qty) AS wastage_qty, sum(f.unfulfilled_demand) AS unfulfilled_demand,
       sum(f.closing_stock) AS closing_stock, sum(f.stockout_days) AS stockout_days
FROM fact_hospital_demand f
JOIN dim_date d ON d.date_key = f.month_date_key
JOIN dim_hospital h ON h.hospital_key = f.hospital_key
JOIN dim_medicine m ON m.medicine_key = f.medicine_key
GROUP BY ALL;
