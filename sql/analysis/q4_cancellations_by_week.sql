-- Q4: cancellation rate per ISO week and hub.
SELECT d.iso_week,
       min(d.date)                                   AS week_start,
       s.hub,
       count(*)                                      AS n_stops,
       round(100.0 * avg(f.is_cancelled::int), 2)    AS pct_cancelled
FROM dw.fact_stop f
JOIN dw.dim_date d USING (date_key)
JOIN dw.dim_station s USING (station_key)
GROUP BY d.iso_week, s.hub
ORDER BY d.iso_week, s.hub;
