# Findings (Apr–Sep 2026, six hubs)

Every number comes from a query in [sql/analysis/](../sql/analysis/) on `dw` (1,666,989 stops).
On time = delay < 6 min. Arrival and departure punctuality are measured separately; cancelled stops
are excluded from punctuality and counted in the cancellation rate.

## Q1: How punctual are the hubs?

`q1_punctuality_by_hub.sql`

| Hub | Arrivals on time | Departures on time | Avg arrival delay | 90th pct arrival delay |
|---|---|---|---|---|
| Hamburg Hbf | 84.7 % | 86.7 % | 3.6 min | 8 min |
| Berlin Hbf | 83.1 % | 84.0 % | 4.6 min | 12 min |
| Frankfurt (Main) Hbf | 72.7 % | 77.4 % | 5.8 min | 15 min |
| München Hbf | 69.7 % | 78.0 % | 6.1 min | 13 min |
| Köln Hbf | 67.9 % | 70.1 % | 7.5 min | 21 min |
| Hannover Hbf | 64.5 % | 72.7 % | 8.7 min | 24 min |

Hamburg and Berlin lead largely because of their punctual S-Bahn networks (see Q2), which make up a
large share of their stops. Arrivals are less punctual than departures everywhere: trains make up
some time during the stop.

## Q2: Train type, hour, weekday, month

`q2a_…`, `q2b_…`, `q2c_…`

- **Train type is the biggest factor.** Long-distance arrivals are on time only 37–50 % of the time
  (Köln 36.6 %, worst). Regional: 62–79 %. S-Bahn: 74–96 % (Berlin 96.1 %, Hamburg 91.8 %, München 74.4 %).
  Ranking hubs within a category gives a fairer comparison than the overall table.
- **Hour of day:** on weekdays punctuality falls from 91 % at 04:00 to its low of 65–66 % at
  16:00–18:00 (evening peak), then recovers to ~73 % late in the evening. Weekends are better at every hour (75–92 %).
- **Weekday:** Monday 75.0 % → Friday 72.3 %, gradually worse through the week; Saturday 78.7 %, Sunday 81.9 %.
- **Month:** best in April (79.0 %), worst in July (72.8 %); summer months are 2–6 points below spring.

## Q3: Least reliable lines

`q3_least_reliable_lines.sql` (lines with ≥ 2,000 measured arrivals)

| Line | Category | Arrivals on time | Cancelled |
|---|---|---|---|
| FLX 10 | long distance | 29.0 % | 15.6 % |
| IC | long distance | 39.1 % | 9.4 % |
| FLX 30 | long distance | 41.2 % | 7.2 % |
| RJ | long distance | 43.7 % | 4.5 % |
| ECE | long distance | 47.5 % | 6.6 % |
| ICE | long distance | 48.0 % | 5.8 % |
| RE50 | regional (Frankfurt) | 48.5 % | 3.0 % |
| RB82 | regional (Frankfurt) | 52.6 % | 2.8 % |

Long-distance trains (which have no line number in the data and are grouped by product) fill the top of
the list. The least reliable regional lines are around Frankfurt (RE50, RB82, RB51) and München (RB16, RB6).

## Q4: Cancellations over time

`q4_cancellations_by_week.sql`, `q4b_cancellations_by_month.sql`

- Overall 5.1 % of stops are cancelled (arrival or departure side).
- **Late June is the outlier:** week 26 (22–28 Jun) averages 11.2 % across hubs; the eight worst days
  of the period are 24–29 Jun and 28–29 May (12–15 %). Single hubs reach 16–18 % in weeks 20, 22 and 26.
  The data does not say why (storms, strikes and construction are all possible), so this is reported as a pattern only.
- Long distance is cancelled most in June (8.6 %) and July (7.4 %), against 3.8 % in April.

## Q5: Transfer risk

See [transfer_risk.md](transfer_risk.md). With a 5-minute transfer, 17.8 % of planned connections are
missed (Hannover 32.2 % … Hamburg 11.2 %). With 15 minutes it is 6.8 %. Arriving long-distance trains are the main risk:
47 % of 5-minute changes from a long-distance train to an S-Bahn are missed.
