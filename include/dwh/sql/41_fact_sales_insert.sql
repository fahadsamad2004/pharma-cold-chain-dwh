INSERT INTO fact_sales
SELECT (SELECT COALESCE(max(sales_key), 0) FROM fact_sales)
         + row_number() OVER (ORDER BY TRY_CAST(s.salesdate AS DATE), s.salestransactionid) AS sales_key,
       s.salestransactionid,
       CAST(strftime(TRY_CAST(s.salesdate AS DATE), '%Y%m%d') AS INTEGER),
       COALESCE(CAST(strftime(TRY_CAST(s.pharmacydeliverydate AS DATE), '%Y%m%d') AS INTEGER), -1),
       COALESCE(CAST(strftime(TRY_CAST(s.batchexpirydate AS DATE), '%Y%m%d') AS INTEGER), -1),
       m.medicine_key,                      -- point-in-time version: the price valid ON the sale date
       COALESCE(p.pharmacy_key, -1), COALESCE(h.hospital_key, -1), ch.channel_key,
       COALESCE(seg.segment_key, -1), COALESCE(promo.promotion_key, -1), COALESCE(j.sales_junk_key, -1),
       s.warehouselotid, s.productionbatchid, s.sourcewarehouseid, s.pharmacyorderid, s.pharmacydeliveryid,
       TRY_CAST(s.salestimestamputc AS TIMESTAMP),
       CAST(TRY_CAST(s.quantitysoldpacks AS DOUBLE) AS INTEGER), TRY_CAST(s.unitretailpriceusd AS DOUBLE),
       TRY_CAST(s.grosssalesamountusd AS DOUBLE), TRY_CAST(s.discountamountusd AS DOUBLE),
       TRY_CAST(s.netsalesamountusd AS DOUBLE), TRY_CAST(s.salestaxusd AS DOUBLE),
       TRY_CAST(s.costofgoodssoldusd AS DOUBLE), TRY_CAST(s.grossmarginusd AS DOUBLE),
       CAST(COALESCE(TRY_CAST(s.returnedquantitypacks AS DOUBLE), 0) AS INTEGER),
       CAST(TRY_CAST(s.daystoexpiryatsale AS DOUBLE) AS INTEGER),
       s._load_id, current_timestamp
FROM stage.new_sales s
JOIN dim_medicine m ON m.medicine_id = s.medicineid
                   AND TRY_CAST(s.salesdate AS DATE) BETWEEN m.valid_from AND m.valid_to
JOIN dim_channel ch ON ch.channel_group = s.channel_group
LEFT JOIN dim_pharmacy p ON p.pharmacy_id = s.pharmacyid
LEFT JOIN dim_hospital h ON h.hospital_id = s.hospitalid
LEFT JOIN dim_customer_segment seg ON seg.segment_name = s.customersegment
LEFT JOIN dim_promotion promo ON promo.promotion_code = COALESCE(s.promotioncode, 'NONE')
LEFT JOIN dim_sales_junk j
       ON j.payment_method IS NOT DISTINCT FROM s.paymentmethod AND j.payer_type IS NOT DISTINCT FROM s.payertype
      AND j.prescription_required IS NOT DISTINCT FROM s.prescriptionrequiredflag
      AND j.return_flag IS NOT DISTINCT FROM s.returnflag AND j.sale_status IS NOT DISTINCT FROM s.salestatus
      AND j.ecommerce_delivery_status IS NOT DISTINCT FROM s.ecommercedeliverystatus
ORDER BY 1;
