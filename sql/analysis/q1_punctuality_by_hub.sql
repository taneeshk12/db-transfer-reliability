-- Q1: punctuality per hub (on time = delay < 6 min). Arrival and departure measured separately;
-- cancelled sides and implausible delays are excluded (flags are NULL there).
SELECT s.hub,
       count(*)                                               AS n_stops,
       round(100.0 * avg(f.is_arrival_on_time::int), 1)       AS pct_arrival_on_time,
       round(100.0 * avg(f.is_departure_on_time::int), 1)     AS pct_departure_on_time,
       round(avg(f.arrival_delay_min)::numeric, 1)            AS avg_arrival_delay_min,
       percentile_cont(0.9) WITHIN GROUP (ORDER BY f.arrival_delay_min) AS p90_arrival_delay_min
FROM dw.fact_stop f
JOIN dw.dim_station s USING (station_key)
GROUP BY s.hub
ORDER BY pct_arrival_on_time DESC;
