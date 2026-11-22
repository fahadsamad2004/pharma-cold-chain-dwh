-- SCD2 step 1: if the staged version differs from the current one and is newer, CLOSE the
-- current row (valid_to = day before the change, is_current = false).
UPDATE dim_medicine d
SET valid_to = v.eff - INTERVAL 1 DAY, is_current = FALSE
FROM stage.master_versions v
WHERE v.seq = ? AND d.medicine_id = v.medicineid AND d.is_current
  AND d.row_hash <> v.h AND v.eff > d.valid_from;
