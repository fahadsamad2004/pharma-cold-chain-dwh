-- Small dimensions + junk dimensions: insert any NEW value combinations found in this batch.
INSERT INTO dim_customer_segment (segment_key, segment_name)
SELECT nextval('seq_segment'), s.customersegment
FROM (SELECT DISTINCT customersegment FROM stage.sales WHERE customersegment IS NOT NULL) s
WHERE NOT EXISTS (SELECT 1 FROM dim_customer_segment d WHERE d.segment_name = s.customersegment);

INSERT INTO dim_promotion (promotion_key, promotion_code, discount_pct)
SELECT nextval('seq_promotion'), p.code, p.pct
FROM (SELECT COALESCE(promotioncode, 'NONE') AS code,
             round(avg(TRY_CAST(discountamountusd AS DOUBLE) / NULLIF(TRY_CAST(grosssalesamountusd AS DOUBLE), 0)), 2) AS pct
      FROM stage.sales GROUP BY 1) p
WHERE NOT EXISTS (SELECT 1 FROM dim_promotion d WHERE d.promotion_code = p.code);

INSERT INTO dim_sales_junk (sales_junk_key, payment_method, payer_type, prescription_required,
                            return_flag, sale_status, ecommerce_delivery_status)
SELECT nextval('seq_sales_junk'), j.paymentmethod, j.payertype, j.prescriptionrequiredflag,
       j.returnflag, j.salestatus, j.ecommercedeliverystatus
FROM (SELECT DISTINCT paymentmethod, payertype, prescriptionrequiredflag, returnflag, salestatus,
             ecommercedeliverystatus FROM stage.sales) j
WHERE NOT EXISTS (SELECT 1 FROM dim_sales_junk d
                  WHERE d.payment_method IS NOT DISTINCT FROM j.paymentmethod
                    AND d.payer_type IS NOT DISTINCT FROM j.payertype
                    AND d.prescription_required IS NOT DISTINCT FROM j.prescriptionrequiredflag
                    AND d.return_flag IS NOT DISTINCT FROM j.returnflag
                    AND d.sale_status IS NOT DISTINCT FROM j.salestatus
                    AND d.ecommerce_delivery_status IS NOT DISTINCT FROM j.ecommercedeliverystatus);

INSERT INTO dim_demand_status (demand_status_key, medication_request_status, formulary_status)
SELECT nextval('seq_demand_status'), j.medicationrequeststatus, j.formularystatus
FROM (SELECT DISTINCT medicationrequeststatus, formularystatus FROM stage.hospital_demand) j
WHERE NOT EXISTS (SELECT 1 FROM dim_demand_status d
                  WHERE d.medication_request_status IS NOT DISTINCT FROM j.medicationrequeststatus
                    AND d.formulary_status IS NOT DISTINCT FROM j.formularystatus);
