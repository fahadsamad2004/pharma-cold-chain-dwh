INSERT INTO fact_hospital_demand
SELECT (SELECT COALESCE(max(demand_key), 0) FROM fact_hospital_demand)
         + row_number() OVER (ORDER BY TRY_CAST(s.demandmonth AS DATE), s.hospitalid, s.medicineid),
       s.hospitaldemandrecordid,
       CAST(strftime(TRY_CAST(s.demandmonth AS DATE), '%Y%m%d') AS INTEGER),
       COALESCE(h.hospital_key, -1), m.medicine_key, COALESCE(ds.demand_status_key, -1),
       CAST(TRY_CAST(s.estimateddiseasecases AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.diseaserelatedadmissions AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.outpatientencounters AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.forecastdemandpacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.requestedquantitypacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.approvedquantitypacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.receivedquantitypacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.emergencyrequestquantitypacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.openingstockpacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.dispensedquantitypacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.consumedquantitypacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.wastagequantitypacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.closingstockpacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.unfulfilleddemandpacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(s.stockoutdays AS DOUBLE) AS INTEGER), TRY_CAST(s.servicelevelpct AS DOUBLE),
       CAST(TRY_CAST(s.averageleadtimedays AS DOUBLE) AS INTEGER), TRY_CAST(s.demandtrendindex AS DOUBLE),
       s._load_id, current_timestamp
FROM stage.new_demand s
JOIN dim_medicine m ON m.medicine_id = s.medicineid
                   AND TRY_CAST(s.demandmonth AS DATE) BETWEEN m.valid_from AND m.valid_to
LEFT JOIN dim_hospital h ON h.hospital_id = s.hospitalid
LEFT JOIN dim_demand_status ds ON ds.medication_request_status IS NOT DISTINCT FROM s.medicationrequeststatus
                              AND ds.formulary_status IS NOT DISTINCT FROM s.formularystatus
ORDER BY 1;
