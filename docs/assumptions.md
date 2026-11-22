# Project assumptions

**Data and files**
1. The 7 historical files are loaded as CSV (a 208 MB sales file is impractical as .xlsx). Every *generated* refresh file is written as `.xlsx`, so the "Excel file" requirement is met and the loader proves it reads both formats.
2. Staging is a raw copy: all columns TEXT + audit columns (`_load_id`, `_loaded_at`, `_source_file`). Typing/casting happens in the transform so a bad value can never block a load.
3. Empty cells are NULL. Columns that are legitimately empty (e.g. `HospitalID` on 78% of sales, `PromotionCode` on 84%, `PrescriptionID` on 7%) are **not** validation failures.
4. Validation rules (reject the row, log the reason): non-null keys (sale id, medicine, pharmacy; demand id, hospital, medicine), price > 0, quantity > 0, parseable date within 2020-2030, non-negative demand quantities, no duplicate key inside a file. A schema mismatch (missing/extra column) or unknown file name fails the whole batch.
5. A load is "successful" if it finishes without an unhandled exception (spec definition). Rows rejected by validation are counted separately.
6. Re-delivering a file with a name that already loaded successfully is skipped (idempotent). Even if the same record arrives in another file, the fact load uses an anti-join on the natural key, so the warehouse never gets duplicates.

**Dimensional model**
7. `SalesChannel` in the source has only two values (Physical Pharmacy, Ecommerce). The spec's three-way split is derived: E-commerce if `SalesChannel = Ecommerce`; else Hospital if `PharmacyType = Hospital Pharmacy`; else Retail.
8. Non-hospital sales have no `HospitalID`; they point to the reserved member `hospital_key = -1` ("Not a hospital sale"). Every dimension has a -1 Unknown member.
9. `dim_medicine` is SCD Type 2. Tracked attributes: wholesale price, retail price, unit manufacturing cost, product status, primary supplier, primary plant. A medicine's first version is valid from 1900-01-01 so every historical sale finds a row. Facts are linked to the version valid **on the sale date** (point-in-time).
10. `dim_pharmacy` and `dim_hospital` are SCD Type 1 (overwrite). `dim_channel`, `dim_customer_segment`, `dim_promotion` are small static-ish dimensions. `dim_sales_junk` (payment method, payer type, prescription flag, return flag, sale status, e-commerce delivery status) and `dim_demand_status` are junk dimensions.
11. `dim_date` is one physical table used in three roles on `fact_sales` (sale / delivery / expiry date) via role-playing views.
12. `fact_sales` is a transaction fact (grain: one sales transaction). `fact_hospital_demand` is a periodic snapshot fact (grain: hospital x medicine x month). Hospital-level measures (disease cases, admissions, outpatient encounters) repeat on each medicine row, so they are not additive across medicines.
13. Aggregate tables are rebuilt in full from the facts after every load (they are derived, the facts hold the history).
14. "Top 10 per therapeutic class" is not meaningful (49 classes for 63 medicines, ~1-2 medicines each). We show top-10 overall plus fast/slow ranking inside each of the 7 disease categories. Only 3 of the 63 medicines are cold-chain; `cold_chain_flag` is carried in the results so BI can filter them.

**Generator (oversampling)**
15. Refresh 1 = January 2026, Refresh 2 = February 2026 (history ends Dec 2025, so the DWH keeps growing).
16. Sales volume: 2025 total (180,000) x last year's growth (+9.09%) = 196,364 projected for 2026, spread by number of days: 16,677 rows (Jan), 15,064 rows (Feb). The real history is very spiky around Dec/Jan; we deliberately smooth it so refresh files stay demo-sized.
17. Each new sale re-uses a real pharmacy / warehouse lot / batch / medicine combination from the previous 180 days whose batch still has >= 30 days of shelf life; date is uniform within the month; prices use the current master data; discount % by promotion code, 6% tax, COGS = wholesale price are formulas observed in the history; return and promotion rates are inherited from the sampled rows.
18. Hospital demand: exactly 756 rows per month (12 hospitals x 63 medicines). Values scale from the same month last year with the observed growth and ratios; opening stock = previous month's closing stock; closing = opening + received - dispensed - wastage (identity in the history).
19. Master data: 4 medicines per refresh get a 4-10% price rise and 2-5% cost rise, effective on the 1st of the month - this creates real SCD2 history.
20. Fixed random seed per refresh -> reproducible runs. Oversampling covers the Phase 1 sources (01, 05, 06); generators for 02, 03, 04 and 07 are added in the phases that use them.

**Storage / query layer**
21. Storage footprint: Postgres via `pg_total_relation_size` / `pg_database_size`, DuckDB via `os.path.getsize` of the database file. Date coverage = distinct year-months present vs months expected from 2023-01 (Jan 2023 holds only 3 sales rows - the history is partial for that month).
22. Query time is measured with `time.perf_counter()` around each execution. Daily query count and error rate come from the automated dashboard-refresh and benchmark runs (queries a BI tool sends directly are not counted unless it is pointed at the wrapper).
23. DuckDB is already fast on 500k rows: raw-vs-summary-table gains are large for the big scans (3-7x) but negligible for the tiny hospital queries; Parquet partitioning shows no gain at this size. We report the measured numbers as they are. DuckDB is columnar, so we rely on summary tables, insert ordering (zone maps) and partitioning rather than B-tree indexes.
24. DuckDB allows one writer, so transform tasks run sequentially and marts are published to Postgres schema `mart` for BI tools.
25. **Streaming ingestion** is simulated with one micro-batch per second (default 40 events/s, 60 s window). Events follow the schema of source file 07 (IoT) and are written to `stg.iot`. Each event carries a creation timestamp 0.05-2.5 s in the past (simulated gateway delay); latency = DB-insert time - event time. About 1.5% of events are deliberately malformed (null key, null device, unparseable timestamp) to exercise the malformed-record counter. Throughput = events ingested / length of the tick window. In Phase 3 the same mechanism will replay the real IoT file.
