-- Business question 5: missed-transfer share by planned arrival hour (5-minute buffer, weekdays).
SELECT arrival_hour,
       sum(n_pairs)                                   AS n_pairs,
       round(100.0 * sum(n_missed) / sum(n_pairs), 1) AS pct_missed
FROM dw.agg_transfer_risk
WHERE buffer_min = 5 AND NOT is_weekend
GROUP BY arrival_hour
ORDER BY arrival_hour;
