-- Dashboard widget: fast vs slow movers ranked inside each disease category
WITH v AS (
  SELECT m.disease_category, m.therapeutic_class, m.generic_name, SUM(f.qty_sold) AS units_sold
  FROM fact_sales f JOIN dim_medicine m ON m.medicine_key = f.medicine_key
  GROUP BY m.disease_category, m.therapeutic_class, m.generic_name)
SELECT *, RANK() OVER (PARTITION BY disease_category ORDER BY units_sold DESC) AS fast_rank,
          RANK() OVER (PARTITION BY disease_category ORDER BY units_sold ASC)  AS slow_rank
FROM v ORDER BY disease_category, fast_rank;
