-- Q4: cancellation rate per month and train category.
SELECT d.month, d.month_name, t.train_category,
       count(*)                                      AS n_stops,
       round(100.0 * avg(f.is_cancelled::int), 2)    AS pct_cancelled
FROM dw.fact_stop f
JOIN dw.dim_date d USING (date_key)
JOIN dw.dim_train t USING (train_key)
WHERE t.train_category IN ('long_distance', 'regional', 's_bahn')
GROUP BY d.month, d.month_name, t.train_category
ORDER BY d.month, t.train_category;
