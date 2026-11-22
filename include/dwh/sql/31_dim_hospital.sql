-- SCD Type 1 from the hospital demand file (latest month wins).
CREATE OR REPLACE TEMP TABLE src_hospital AS
SELECT hospitalid AS hospital_id, arg_max(hospitalgln, demandmonth) AS hospital_gln,
       arg_max(hospitalname, demandmonth) AS hospital_name, arg_max(hospitaltype, demandmonth) AS hospital_type,
       arg_max(hospitalpharmacyid, demandmonth) AS hospital_pharmacy_id, arg_max(city, demandmonth) AS city,
       arg_max(state, demandmonth) AS state, arg_max(countrycode, demandmonth) AS country_code,
       arg_max(traumalevel, demandmonth) AS trauma_level,
       CAST(TRY_CAST(arg_max(licensedbeds, demandmonth) AS DOUBLE) AS INTEGER) AS licensed_beds,
       CAST(TRY_CAST(arg_max(icubeds, demandmonth) AS DOUBLE) AS INTEGER) AS icu_beds,
       TRY_CAST(arg_max(averageoccupancyratepct, demandmonth) AS DOUBLE) AS avg_occupancy_rate_pct,
       CAST(TRY_CAST(arg_max(catchmentpopulation, demandmonth) AS DOUBLE) AS BIGINT) AS catchment_population
FROM stage.hospital_demand
WHERE hospitalid IS NOT NULL GROUP BY hospitalid;

UPDATE dim_hospital d
SET hospital_gln = s.hospital_gln, hospital_name = s.hospital_name, hospital_type = s.hospital_type,
    hospital_pharmacy_id = s.hospital_pharmacy_id, city = s.city, state = s.state,
    country_code = s.country_code, trauma_level = s.trauma_level, licensed_beds = s.licensed_beds,
    icu_beds = s.icu_beds, avg_occupancy_rate_pct = s.avg_occupancy_rate_pct,
    catchment_population = s.catchment_population, updated_at = current_timestamp
FROM src_hospital s
WHERE d.hospital_id = s.hospital_id
  AND (d.hospital_name IS DISTINCT FROM s.hospital_name OR d.licensed_beds IS DISTINCT FROM s.licensed_beds
       OR d.icu_beds IS DISTINCT FROM s.icu_beds
       OR d.avg_occupancy_rate_pct IS DISTINCT FROM s.avg_occupancy_rate_pct
       OR d.catchment_population IS DISTINCT FROM s.catchment_population
       OR d.trauma_level IS DISTINCT FROM s.trauma_level);

INSERT INTO dim_hospital (hospital_key, hospital_id, hospital_gln, hospital_name, hospital_type,
       hospital_pharmacy_id, city, state, country_code, trauma_level, licensed_beds, icu_beds,
       avg_occupancy_rate_pct, catchment_population)
SELECT nextval('seq_hospital'), s.hospital_id, s.hospital_gln, s.hospital_name, s.hospital_type,
       s.hospital_pharmacy_id, s.city, s.state, s.country_code, s.trauma_level, s.licensed_beds,
       s.icu_beds, s.avg_occupancy_rate_pct, s.catchment_population
FROM src_hospital s
WHERE NOT EXISTS (SELECT 1 FROM dim_hospital d WHERE d.hospital_id = s.hospital_id);
