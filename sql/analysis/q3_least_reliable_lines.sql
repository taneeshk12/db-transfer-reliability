-- Q3: least reliable lines (arrival punctuality), lines with >= 2,000 measured arrivals.
SELECT t.line_label,
       t.train_category,
       string_agg(DISTINCT s.hub, ', ')                          AS hubs,
       count(*) FILTER (WHERE f.is_arrival_on_time IS NOT NULL)  AS n_arrivals,
       round(100.0 * avg(f.is_arrival_on_time::int), 1)          AS pct_arrival_on_time,
       round(100.0 * avg(f.is_cancelled::int), 1)                AS pct_cancelled
FROM dw.fact_stop f
JOIN dw.dim_train t USING (train_key)
JOIN dw.dim_station s USING (station_key)
WHERE t.train_category IN ('long_distance', 'regional', 's_bahn')
GROUP BY t.line_label, t.train_category
HAVING count(*) FILTER (WHERE f.is_arrival_on_time IS NOT NULL) >= 2000
ORDER BY pct_arrival_on_time
LIMIT 15;
