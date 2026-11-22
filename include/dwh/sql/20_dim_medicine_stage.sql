-- Prepare every staged master row as a candidate "version" of a medicine, numbered in
-- chronological order. row_hash covers ONLY the attributes we want history for (Type 2):
-- prices, manufacturing cost, status, supplier, plant.
CREATE OR REPLACE TABLE stage.master_versions AS
SELECT row_number() OVER (ORDER BY TRY_CAST(effectivefromdate AS DATE), _loaded_at, medicineid) AS seq,
       TRY_CAST(effectivefromdate AS DATE) AS eff,
       md5(concat_ws('|', CAST(TRY_CAST(wholesalepriceusd AS DOUBLE) AS VARCHAR),
                          CAST(TRY_CAST(recommendedretailpriceusd AS DOUBLE) AS VARCHAR),
                          CAST(TRY_CAST(unitmanufacturingcostusd AS DOUBLE) AS VARCHAR),
                          productstatus, primarysupplierid, primaryplantid)) AS h,
       *
FROM stage.master;
