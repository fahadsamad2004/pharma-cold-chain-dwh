-- SCD2 step 2: insert a new current version when the medicine has no current row
-- (brand-new medicine, or the previous version was just closed in step 1).
-- A medicine's FIRST version is valid from 1900-01-01 so every historical sale finds a row.
INSERT INTO dim_medicine
SELECT nextval('seq_medicine'), v.medicineid, v.internalsku, v.gtin14, v.genericname, v.fictionalbrandname,
       v.diseasecategory, v.icd10category, v.atccode, v.therapeuticclass, v.dosageform, v.strength,
       v.routeofadministration, v.packsize, v.prescriptionclass, v.controlledmedicineflag, v.coldchainflag,
       TRY_CAST(v.storagemintempc AS DOUBLE), TRY_CAST(v.storagemaxtempc AS DOUBLE),
       TRY_CAST(v.maxhumiditypct AS DOUBLE), CAST(TRY_CAST(v.shelflifemonths AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(v.minimumremainingshelflifedays AS DOUBLE) AS INTEGER),
       v.primarysupplierid, v.primaryplantid,
       CAST(TRY_CAST(v.manufacturingleadtimedays AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(v.standardbatchsizepacks AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(v.safetystockdays AS DOUBLE) AS INTEGER),
       CAST(TRY_CAST(v.reorderreviewcycledays AS DOUBLE) AS INTEGER),
       TRY_CAST(v.unitmanufacturingcostusd AS DOUBLE), TRY_CAST(v.wholesalepriceusd AS DOUBLE),
       TRY_CAST(v.recommendedretailpriceusd AS DOUBLE), v.productstatus,
       CASE WHEN p.max_ver IS NULL THEN DATE '1900-01-01' ELSE v.eff END,
       DATE '9999-12-31', TRUE, COALESCE(p.max_ver, 0) + 1, v.h, current_timestamp
FROM stage.master_versions v
LEFT JOIN (SELECT medicine_id, max(version_no) AS max_ver FROM dim_medicine GROUP BY medicine_id) p
       ON p.medicine_id = v.medicineid
WHERE v.seq = ?
  AND NOT EXISTS (SELECT 1 FROM dim_medicine d WHERE d.medicine_id = v.medicineid AND d.is_current);
