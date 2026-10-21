# Data dictionary: historical source

Source: `monthly_processed_data/data-YYYY-MM.parquet` from
[piebro/deutsche-bahn-data](https://huggingface.co/datasets/piebro/deutsche-bahn-data) (CC BY 4.0, data by Deutsche Bahn).
Months used: 2026-04 … 2026-09. Grain: **one row per train stop at one EVA number** (`id` is unique).
Evidence for every statement below is in [history_profile.md](history_profile.md).

## Columns used

| Column | Type | Meaning (verified) | Used for |
|---|---|---|---|
| `station_name` | string | Normalised station name; groups several EVA numbers of one hub. Berlin is `Berlin Hauptbahnhof`. | Hub filter (`config.HISTORY_STATION_NAMES`) |
| `xml_station_name` | string | Name of the individual EVA (e.g. `Hamburg Hbf (S-Bahn)`, `München Hbf Gl.27-36`) | Platform-area labels in `dim_station` |
| `eva` | string | EVA station number, zero-padded to 8 chars (e.g. `08000105`) | Station key, dedup |
| `train_type` | string | Product **or operator** code: `ICE`, `RE`, `S`, but also `BRB`, `NX`, `ME`, `ARV` … NULL for ~1.5 % (rows without plan record) | Train-type classification (with `line_number`) |
| `train_number` | string | Train number (`tl.n`) | Train label, dedup |
| `line_number` | string | Line (`S8`, `RE31`, `RB41`); NULL for most long-distance trains | Line analysis; product prefix for operator-coded types |
| `train_line_ride_id` | string | ID of one train run | Dedup across sub-EVAs |
| `arrival_planned_time` / `arrival_change_time` | timestamp | Planned / actual arrival, **naive Europe/Berlin local time**. NULL if the stop has no arrival (train starts here) | Arrival delay → transfer risk |
| `departure_planned_time` / `departure_change_time` | timestamp | Planned / actual departure, naive local time. NULL if the train terminates here | Departure delay, date/hour keys |
| `time` | timestamp | Actual departure, or actual arrival if there is no departure | Reference only |
| `delay_in_min` | int | **Departure delay** (`departure_change_time − departure_planned_time`) if a departure exists, else arrival delay. Matches the departure difference in 100 % of rows | Punctuality metrics |
| `arrival_is_canceled` / `departure_is_canceled` | bool | Stop cancelled for arrival / departure | `is_cancelled` |
| `has_plan_record` | bool | Stop appears in the planned timetable (`/plan`); FALSE = known only from change data | Data quality, dedup preference |
| `is_replacement_train` | bool | Replacement service | Quality flag |

## Columns not used

`final_destination_station`, `train_line_station_num`, `id` (only checked for uniqueness),
`is_additional_stop`, `replaced_train_type`, `replaced_train_number`.
Five columns (`is_additional_stop`, `is_replacement_train`, `replaced_train_type`,
`replaced_train_number`, `has_plan_record`) exist in the files but are **not documented in the dataset README**;
their meaning above is inferred from their names and values.

## Added by this project

| Column | Added in | Meaning |
|---|---|---|
| `hub` | `filter_hubs.py` | Canonical hub name from `config.FOCUS_HUBS` |
| `file_month` | `filter_hubs.py` | Source file month (lineage) |
