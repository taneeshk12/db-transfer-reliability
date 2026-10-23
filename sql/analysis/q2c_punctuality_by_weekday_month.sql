-- Q2: arrival punctuality by weekday and by month.
SELECT 'weekday' AS dimension, d.weekday_num AS sort_key, d.weekday_name AS label,
       round(100.0 * avg(f.is_arrival_on_time::int), 1) AS pct_arrival_on_time
FROM dw.fact_stop f JOIN dw.dim_date d USING (date_key)
GROUP BY d.weekday_num, d.weekday_name
UNION ALL
SELECT 'month', d.month, d.month_name,
       round(100.0 * avg(f.is_arrival_on_time::int), 1)
FROM dw.fact_stop f JOIN dw.dim_date d USING (date_key)
GROUP BY d.month, d.month_name
ORDER BY dimension DESC, sort_key;
