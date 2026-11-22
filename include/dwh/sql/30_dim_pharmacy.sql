-- SCD Type 1: overwrite changed attributes, insert new pharmacies. Source = pharmacies seen in sales.
CREATE OR REPLACE TEMP TABLE src_pharmacy AS
SELECT pharmacyid AS pharmacy_id, arg_max(pharmacygln, salesdate) AS pharmacy_gln,
       arg_max(pharmacyname, salesdate) AS pharmacy_name, arg_max(pharmacytype, salesdate) AS pharmacy_type,
       arg_max(hospitalid, salesdate) AS hospital_id, arg_max(pharmacycity, salesdate) AS city,
       arg_max(pharmacystate, salesdate) AS state, arg_max(countrycode, salesdate) AS country_code
FROM stage.sales WHERE pharmacyid IS NOT NULL GROUP BY pharmacyid;

UPDATE dim_pharmacy d
SET pharmacy_gln = s.pharmacy_gln, pharmacy_name = s.pharmacy_name, pharmacy_type = s.pharmacy_type,
    hospital_id = s.hospital_id, city = s.city, state = s.state, country_code = s.country_code,
    updated_at = current_timestamp
FROM src_pharmacy s
WHERE d.pharmacy_id = s.pharmacy_id
  AND (d.pharmacy_name IS DISTINCT FROM s.pharmacy_name OR d.pharmacy_type IS DISTINCT FROM s.pharmacy_type
       OR d.city IS DISTINCT FROM s.city OR d.state IS DISTINCT FROM s.state
       OR d.hospital_id IS DISTINCT FROM s.hospital_id OR d.pharmacy_gln IS DISTINCT FROM s.pharmacy_gln);

INSERT INTO dim_pharmacy (pharmacy_key, pharmacy_id, pharmacy_gln, pharmacy_name, pharmacy_type,
                          hospital_id, city, state, country_code)
SELECT nextval('seq_pharmacy'), s.pharmacy_id, s.pharmacy_gln, s.pharmacy_name, s.pharmacy_type,
       s.hospital_id, s.city, s.state, s.country_code
FROM src_pharmacy s
WHERE NOT EXISTS (SELECT 1 FROM dim_pharmacy d WHERE d.pharmacy_id = s.pharmacy_id);
