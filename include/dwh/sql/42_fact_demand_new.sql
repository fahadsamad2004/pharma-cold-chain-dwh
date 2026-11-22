CREATE OR REPLACE TABLE stage.new_demand AS
SELECT s.* FROM stage.hospital_demand s
WHERE NOT EXISTS (SELECT 1 FROM fact_hospital_demand f WHERE f.hospital_demand_record_id = s.hospitaldemandrecordid)
QUALIFY row_number() OVER (PARTITION BY s.hospitaldemandrecordid ORDER BY s._loaded_at DESC) = 1;
