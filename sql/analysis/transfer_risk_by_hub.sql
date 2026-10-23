-- Business question 5: share of missed transfers per hub and planned buffer (all train types).
-- missed = arriving train arrives at/after the connecting train's actual departure (no walking time).
SELECT hub,
       buffer_min,
       sum(n_pairs)                                                        AS n_pairs,
       round(100.0 * sum(n_missed) / sum(n_pairs), 1)                      AS pct_missed,
       round(100.0 * sum(n_missed_if_departure_on_time) / sum(n_pairs), 1) AS pct_missed_if_departure_on_time
FROM dw.agg_transfer_risk
GROUP BY hub, buffer_min
ORDER BY buffer_min, pct_missed DESC;
