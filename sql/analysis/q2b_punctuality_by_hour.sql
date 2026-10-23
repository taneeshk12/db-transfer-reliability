-- Q2: arrival punctuality by planned hour, weekdays vs weekends.
SELECT f.planned_hour,
       round(100.0 * avg(f.is_arrival_on_time::int) FILTER (WHERE NOT d.is_weekend), 1) AS pct_on_time_weekday,
       round(100.0 * avg(f.is_arrival_on_time::int) FILTER (WHERE d.is_weekend), 1)     AS pct_on_time_weekend
FROM dw.fact_stop f
JOIN dw.dim_date d USING (date_key)
GROUP BY f.planned_hour
ORDER BY f.planned_hour;
