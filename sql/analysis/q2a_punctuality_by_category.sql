-- Q2: arrival punctuality by train category and hub.
SELECT t.train_category,
       s.hub,
       count(*) FILTER (WHERE f.is_arrival_on_time IS NOT NULL) AS n_arrivals,
       round(100.0 * avg(f.is_arrival_on_time::int), 1)         AS pct_arrival_on_time
FROM dw.fact_stop f
JOIN dw.dim_train t USING (train_key)
JOIN dw.dim_station s USING (station_key)
WHERE t.train_category IN ('long_distance', 'regional', 's_bahn')
GROUP BY t.train_category, s.hub
ORDER BY t.train_category, pct_arrival_on_time;
