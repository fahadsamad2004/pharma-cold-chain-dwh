-- Rows from this batch that are NOT in the fact table yet (append-only + idempotent).
-- If the same sale id arrived twice in staging, keep the most recently loaded copy.
CREATE OR REPLACE TABLE stage.new_sales AS
SELECT s.*,
       CASE WHEN s.saleschannel = 'Ecommerce' THEN 'E-commerce'
            WHEN s.pharmacytype = 'Hospital Pharmacy' THEN 'Hospital'
            ELSE 'Retail' END AS channel_group
FROM stage.sales s
WHERE NOT EXISTS (SELECT 1 FROM fact_sales f WHERE f.sales_transaction_id = s.salestransactionid)
QUALIFY row_number() OVER (PARTITION BY s.salestransactionid ORDER BY s._loaded_at DESC) = 1;
