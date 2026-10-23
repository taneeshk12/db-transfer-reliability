# Transfer risk: method and first results

Code: [src/transfer_risk.py](../src/transfer_risk.py). Table: `dw.agg_transfer_risk`.
Queries: [sql/analysis/transfer_risk_by_hub.sql](../sql/analysis/transfer_risk_by_hub.sql),
[transfer_risk_by_hour.sql](../sql/analysis/transfer_risk_by_hour.sql). Data: Apr–Sep 2026.

## Method

1. Take every non-cancelled arrival at a hub.
2. Pair it with every non-cancelled departure at the **same hub** planned **exactly B minutes later**
   (B = 5, 10, 15), excluding the same train run (through trains).
3. A pair is **missed** if the arriving train's actual arrival is at or after the connecting train's actual
   departure.

The naive rule "arrival delay ≥ B" (`n_missed_if_departure_on_time`) is kept for comparison. It assumes
the connecting train always leaves on time and overstates the risk.

### Limitations

- **No walking time.** Changing platforms takes time, so the real risk for a traveller is higher than
  `pct_missed`, by an unknown amount. `pct_missed` is a lower bound; the naive rule is an upper bound for the same pairs.
- **Pairs, not passengers.** Every possible arrival/departure combination counts once, whether or not
  anyone makes that change. Hubs and categories with many S-Bahn trains contribute many pairs.
- **Platform areas are pooled.** A pair between e.g. Hamburg Hbf and Hamburg Hbf (S-Bahn) counts like a
  same-platform change.
- Cancelled connections are excluded; with a cancellation the transfer fails for a different reason.

## First results (all train types)

| Buffer | Pairs | Missed | Missed if connection on time |
|---|---|---|---|
| 5 min | 1,423,539 | 17.8 % | 27.3 % |
| 10 min | 1,058,230 | 12.4 % | 17.1 % |
| 15 min | 1,425,181 | 6.8 % | 9.0 % |

- **Hubs (5 min):** Hannover 32.2 %, Frankfurt 26.1 %, Köln 23.8 %, München 20.4 %, Berlin 15.7 %, Hamburg 11.2 %.
  With 15 min: Hannover 12.2 % down to Hamburg 3.2 %.
- **Time of day (5 min, weekdays):** lowest in the early morning (10–11 % at 05–06), highest in the
  evening peak (21–23 % at 16–19).
- **Train type (5 min):** arriving long-distance trains are the main risk: ICE/IC → S-Bahn 47.4 %,
  → regional 46.4 %, → long distance 37.1 %. S-Bahn → S-Bahn only 7.1 %.
