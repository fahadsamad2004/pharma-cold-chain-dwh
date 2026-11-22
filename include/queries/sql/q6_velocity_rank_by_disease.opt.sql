WITH v AS (
  SELECT disease_category, therapeutic_class, generic_name, SUM(units_sold) AS units_sold
  FROM agg_sales_month_channel_medicine
  GROUP BY disease_category, therapeutic_class, generic_name)
SELECT *, RANK() OVER (PARTITION BY disease_category ORDER BY units_sold DESC) AS fast_rank,
          RANK() OVER (PARTITION BY disease_category ORDER BY units_sold ASC)  AS slow_rank
FROM v ORDER BY disease_category, fast_rank;
