-- Calendar 2022-2030 (covers the 2023-2025 history plus the 2026 refreshes). Idempotent.
INSERT INTO dim_date
SELECT CAST(strftime(d, '%Y%m%d') AS INTEGER), CAST(d AS DATE), year(d), quarter(d), month(d),
       strftime(d, '%B'), strftime(d, '%Y-%m'), CAST(date_trunc('month', d) AS DATE), day(d),
       isodow(d), strftime(d, '%A'), weekofyear(d), isodow(d) >= 6
FROM generate_series(DATE '2022-01-01', DATE '2030-12-31', INTERVAL 1 DAY) t(d)
WHERE CAST(strftime(d, '%Y%m%d') AS INTEGER) NOT IN (SELECT date_key FROM dim_date);
