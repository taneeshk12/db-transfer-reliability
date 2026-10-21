# Test fixtures

Real DB Timetables API responses for **Frankfurt(Main)Hbf (EVA 8000105)**, recorded on
2026-09-08 around 23:25 by the [piebro/deutsche-bahn-data](https://huggingface.co/datasets/piebro/deutsche-bahn-data)
collector and published in its `raw_data/year=2026/month=9/day=8/date_2026-09-08_hour_23.parquet`
(CC BY 4.0, data by Deutsche Bahn).

| File | Endpoint | Content |
|---|---|---|
| `plan_8000105_2609082300.xml` | `/plan/08000105/260908/23` | Full, unmodified response (27 stops) |
| `fchg_8000105_subset.xml` | `/fchg/08000105` | Subset of the original 688 `<s>` elements: the 27 stops that are also in the plan, 3 other cancelled stops and 2 other stops that carry their own `<tl>` (not in the plan). Elements are copied unchanged; only the selection was made and the file re-serialised. |

No values were invented or edited. A `/station` fixture will be added from the first real
collector run (the piebro dump does not contain `/station` responses).
