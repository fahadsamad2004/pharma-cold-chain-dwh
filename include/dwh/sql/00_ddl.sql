-- =====================================================================================
-- STAR SCHEMA / FACT CONSTELLATION DDL for Phase 1 (DuckDB).  Safe to re-run:
-- everything is CREATE ... IF NOT EXISTS, so history is never dropped.
-- Conventions:  *_key = surrogate key (integer),  -1 = "Unknown / Not applicable" member.
-- =====================================================================================
CREATE SCHEMA IF NOT EXISTS stage;   -- scratch copy of the staging rows being transformed

-- ------------------------------------------------------------------ DATE (role-playing)
CREATE TABLE IF NOT EXISTS dim_date (
    date_key INTEGER, full_date DATE, calendar_year INTEGER, calendar_quarter INTEGER,
    calendar_month INTEGER, month_name VARCHAR, year_month VARCHAR, first_day_of_month DATE,
    day_of_month INTEGER, day_of_week INTEGER, day_name VARCHAR, week_of_year INTEGER,
    is_weekend BOOLEAN);

-- ------------------------------------------------------------------ MEDICINE (SCD Type 2)
CREATE SEQUENCE IF NOT EXISTS seq_medicine START 1;
CREATE TABLE IF NOT EXISTS dim_medicine (
    medicine_key BIGINT, medicine_id VARCHAR, internal_sku VARCHAR, gtin14 VARCHAR,
    generic_name VARCHAR, brand_name VARCHAR, disease_category VARCHAR, icd10_category VARCHAR,
    atc_code VARCHAR, therapeutic_class VARCHAR, dosage_form VARCHAR, strength VARCHAR,
    route_of_administration VARCHAR, pack_size VARCHAR, prescription_class VARCHAR,
    controlled_flag VARCHAR, cold_chain_flag VARCHAR, storage_min_temp_c DOUBLE,
    storage_max_temp_c DOUBLE, max_humidity_pct DOUBLE, shelf_life_months INTEGER,
    min_remaining_shelf_life_days INTEGER, primary_supplier_id VARCHAR, primary_plant_id VARCHAR,
    mfg_lead_time_days INTEGER, standard_batch_size_packs INTEGER, safety_stock_days INTEGER,
    reorder_review_cycle_days INTEGER,
    unit_mfg_cost_usd DOUBLE, wholesale_price_usd DOUBLE, retail_price_usd DOUBLE,   -- tracked
    product_status VARCHAR,                                                           -- tracked
    valid_from DATE, valid_to DATE, is_current BOOLEAN, version_no INTEGER,
    row_hash VARCHAR, loaded_at TIMESTAMP DEFAULT current_timestamp);

-- ------------------------------------------------------------------ PHARMACY / HOSPITAL (SCD Type 1)
CREATE SEQUENCE IF NOT EXISTS seq_pharmacy START 1;
CREATE TABLE IF NOT EXISTS dim_pharmacy (
    pharmacy_key BIGINT, pharmacy_id VARCHAR, pharmacy_gln VARCHAR, pharmacy_name VARCHAR,
    pharmacy_type VARCHAR, hospital_id VARCHAR, city VARCHAR, state VARCHAR, country_code VARCHAR,
    updated_at TIMESTAMP DEFAULT current_timestamp);

CREATE SEQUENCE IF NOT EXISTS seq_hospital START 1;
CREATE TABLE IF NOT EXISTS dim_hospital (
    hospital_key BIGINT, hospital_id VARCHAR, hospital_gln VARCHAR, hospital_name VARCHAR,
    hospital_type VARCHAR, hospital_pharmacy_id VARCHAR, city VARCHAR, state VARCHAR,
    country_code VARCHAR, trauma_level VARCHAR, licensed_beds INTEGER, icu_beds INTEGER,
    avg_occupancy_rate_pct DOUBLE, catchment_population BIGINT,
    updated_at TIMESTAMP DEFAULT current_timestamp);

-- ------------------------------------------------------------------ SMALL DIMENSIONS
CREATE TABLE IF NOT EXISTS dim_channel (
    channel_key INTEGER, channel_group VARCHAR, channel_description VARCHAR, is_physical BOOLEAN);

CREATE SEQUENCE IF NOT EXISTS seq_segment START 1;
CREATE TABLE IF NOT EXISTS dim_customer_segment (segment_key BIGINT, segment_name VARCHAR);

CREATE SEQUENCE IF NOT EXISTS seq_promotion START 1;
CREATE TABLE IF NOT EXISTS dim_promotion (promotion_key BIGINT, promotion_code VARCHAR, discount_pct DOUBLE);

-- JUNK DIMENSION: low-cardinality flags/statuses of a sale folded into one table so the
-- fact table carries ONE key instead of six little columns.
CREATE SEQUENCE IF NOT EXISTS seq_sales_junk START 1;
CREATE TABLE IF NOT EXISTS dim_sales_junk (
    sales_junk_key BIGINT, payment_method VARCHAR, payer_type VARCHAR,
    prescription_required VARCHAR, return_flag VARCHAR, sale_status VARCHAR,
    ecommerce_delivery_status VARCHAR);

-- Junk dimension for the hospital demand fact
CREATE SEQUENCE IF NOT EXISTS seq_demand_status START 1;
CREATE TABLE IF NOT EXISTS dim_demand_status (
    demand_status_key BIGINT, medication_request_status VARCHAR, formulary_status VARCHAR);

-- ------------------------------------------------------------------ FACTS
-- Transaction fact: grain = one sales transaction (append-only)
CREATE TABLE IF NOT EXISTS fact_sales (
    sales_key BIGINT, sales_transaction_id VARCHAR,                 -- degenerate dimension
    sale_date_key INTEGER, delivery_date_key INTEGER, expiry_date_key INTEGER,  -- 3 roles of dim_date
    medicine_key BIGINT, pharmacy_key BIGINT, hospital_key BIGINT, channel_key INTEGER,
    segment_key BIGINT, promotion_key BIGINT, sales_junk_key BIGINT,
    warehouse_lot_id VARCHAR, production_batch_id VARCHAR,          -- traceability keys (Phase 3)
    source_warehouse_id VARCHAR, pharmacy_order_id VARCHAR, pharmacy_delivery_id VARCHAR,
    sale_timestamp_utc TIMESTAMP,
    qty_sold INTEGER, unit_retail_price DOUBLE, gross_sales DOUBLE, discount_amount DOUBLE,
    net_sales DOUBLE, sales_tax DOUBLE, cogs DOUBLE, gross_margin DOUBLE,
    returned_qty INTEGER, days_to_expiry_at_sale INTEGER,
    load_id VARCHAR, loaded_at TIMESTAMP DEFAULT current_timestamp);

-- Periodic snapshot fact: grain = hospital x medicine x month
CREATE TABLE IF NOT EXISTS fact_hospital_demand (
    demand_key BIGINT, hospital_demand_record_id VARCHAR,
    month_date_key INTEGER, hospital_key BIGINT, medicine_key BIGINT, demand_status_key BIGINT,
    estimated_disease_cases INTEGER, disease_related_admissions INTEGER, outpatient_encounters INTEGER,
    forecast_demand INTEGER, requested_qty INTEGER, approved_qty INTEGER, received_qty INTEGER,
    emergency_request_qty INTEGER, opening_stock INTEGER, dispensed_qty INTEGER,
    consumed_qty INTEGER, wastage_qty INTEGER, closing_stock INTEGER, unfulfilled_demand INTEGER,
    stockout_days INTEGER, service_level_pct DOUBLE, avg_lead_time_days INTEGER,
    demand_trend_index DOUBLE, load_id VARCHAR, loaded_at TIMESTAMP DEFAULT current_timestamp);

-- ------------------------------------------------------------------ UNKNOWN MEMBERS + STATIC DIMS
INSERT INTO dim_medicine (medicine_key, medicine_id, generic_name, product_status, valid_from, valid_to,
                          is_current, version_no, row_hash)
SELECT -1, 'UNKNOWN', 'Unknown', 'Unknown', DATE '1900-01-01', DATE '9999-12-31', TRUE, 1, 'n/a'
WHERE NOT EXISTS (SELECT 1 FROM dim_medicine WHERE medicine_key = -1);

INSERT INTO dim_pharmacy (pharmacy_key, pharmacy_id, pharmacy_name, pharmacy_type)
SELECT -1, 'UNKNOWN', 'Unknown pharmacy', 'Unknown'
WHERE NOT EXISTS (SELECT 1 FROM dim_pharmacy WHERE pharmacy_key = -1);

INSERT INTO dim_hospital (hospital_key, hospital_id, hospital_name, hospital_type)
SELECT -1, 'N/A', 'Not a hospital sale', 'Not applicable'
WHERE NOT EXISTS (SELECT 1 FROM dim_hospital WHERE hospital_key = -1);

INSERT INTO dim_date (date_key, full_date, year_month)
SELECT -1, NULL, 'Unknown' WHERE NOT EXISTS (SELECT 1 FROM dim_date WHERE date_key = -1);

INSERT INTO dim_channel
SELECT * FROM (VALUES
  (1, 'Retail',      'Chain and independent physical pharmacies', TRUE),
  (2, 'Hospital',    'Hospital pharmacies',                       TRUE),
  (3, 'E-commerce',  'Online orders (ecommerce platform)',        FALSE),
  (-1,'Unknown',     'Unclassified',                              NULL)) v(channel_key, channel_group, channel_description, is_physical)
WHERE NOT EXISTS (SELECT 1 FROM dim_channel);

INSERT INTO dim_customer_segment (segment_key, segment_name)
SELECT -1, 'Unknown' WHERE NOT EXISTS (SELECT 1 FROM dim_customer_segment WHERE segment_key = -1);

INSERT INTO dim_promotion (promotion_key, promotion_code, discount_pct)
SELECT -1, 'UNKNOWN', NULL WHERE NOT EXISTS (SELECT 1 FROM dim_promotion WHERE promotion_key = -1);

INSERT INTO dim_sales_junk (sales_junk_key, payment_method, payer_type, prescription_required,
                            return_flag, sale_status, ecommerce_delivery_status)
SELECT -1, 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'Unknown', 'Unknown'
WHERE NOT EXISTS (SELECT 1 FROM dim_sales_junk WHERE sales_junk_key = -1);

INSERT INTO dim_demand_status (demand_status_key, medication_request_status, formulary_status)
SELECT -1, 'Unknown', 'Unknown' WHERE NOT EXISTS (SELECT 1 FROM dim_demand_status WHERE demand_status_key = -1);

-- ------------------------------------------------------------------ ROLE-PLAYING VIEWS of dim_date
-- One physical date table, three business roles. BI tools can use these like separate dimensions.
CREATE OR REPLACE VIEW dim_sale_date AS
  SELECT date_key AS sale_date_key, full_date AS sale_date, calendar_year AS sale_year,
         calendar_month AS sale_month, year_month AS sale_year_month, day_name AS sale_day_name FROM dim_date;
CREATE OR REPLACE VIEW dim_delivery_date AS
  SELECT date_key AS delivery_date_key, full_date AS delivery_date, calendar_year AS delivery_year,
         calendar_month AS delivery_month, year_month AS delivery_year_month FROM dim_date;
CREATE OR REPLACE VIEW dim_expiry_date AS
  SELECT date_key AS expiry_date_key, full_date AS expiry_date, calendar_year AS expiry_year,
         calendar_month AS expiry_month, year_month AS expiry_year_month FROM dim_date;
