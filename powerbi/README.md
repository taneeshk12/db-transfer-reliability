# Power BI report

Built in Power BI Desktop (Windows; here in a UTM VM) on the PostgreSQL star schema `dw`.
Measures: [measures.dax](measures.dax). Expected values for checking: [../docs/findings.md](../docs/findings.md).

## 1. Connect from the VM

PostgreSQL runs in Docker on the Mac and listens on port 5434 on all interfaces.

| Setting | Value |
|---|---|
| Server | `<mac-ip>:5434`. With UTM "Shared Network" the Mac is usually `192.168.64.1` (check `ipconfig` in the VM: the Default Gateway) |
| Database | `POSTGRES_DB` from `.env` |
| Data connectivity mode | **Import** (1.7M rows, small enough; keeps the report fast and works offline) |
| Credentials | Database: `POSTGRES_USER` / `POSTGRES_PASSWORD` from `.env` |

*Get data → PostgreSQL database.* The local Postgres has no TLS; when Power BI says the encrypted connection
failed, choose **OK** to connect unencrypted (fine on the host-only VM network, not for remote servers).

Test from the VM first if it fails: `Test-NetConnection 192.168.64.1 -Port 5434` in PowerShell.

## 2. Model

Load `dw.dim_date`, `dw.dim_station`, `dw.dim_train`, `dw.fact_stop`, `dw.agg_transfer_risk`.

Add a hub table in Power Query (*New source → Blank query*):

```m
let
    Source = Table.Distinct(Table.SelectColumns(dim_station, {"hub"}))
in
    Source
```

Name it `dim_hub`. Relationships (single direction, one → many):

| From (one) | To (many) |
|---|---|
| `dim_date[date_key]` | `fact_stop[date_key]` |
| `dim_station[station_key]` | `fact_stop[station_key]` |
| `dim_train[train_key]` | `fact_stop[train_key]` |
| `dim_hub[hub]` | `dim_station[hub]` |
| `dim_hub[hub]` | `agg_transfer_risk[hub]` |

Use `dim_hub[hub]` in every hub slicer so it filters both punctuality and transfer pages.
Sort `dim_date[weekday_name]` by `weekday_num` and `month_name` by `month`. Hide key columns.
Format the % measures as percentage, 1 decimal.

## 3. Pages

| Page | Visuals |
|---|---|
| **Overview** | Cards: Stops, Arrival On-Time %, Cancellation %, Missed Transfer % (buffer 5). Bar: Arrival On-Time % by hub. Line: Arrival On-Time % by month |
| **When** | Matrix heatmap: `planned_hour` × `weekday_name`, Arrival On-Time % with background colour scale. Line: by `planned_hour`, legend `is_weekend` |
| **Train types & lines** | Clustered bar: Arrival On-Time % by hub, legend `train_category`. Table: `line_label`, `train_category`, Measured Arrivals, Arrival On-Time %, Cancellation %; visual filter Measured Arrivals ≥ 2000, sorted ascending |
| **Cancellations** | Line: Cancellation % by `date` (or `iso_week`), legend `train_category`. Bar: Cancellation % by hub |
| **Transfer risk** | Slicer: `buffer_min` (single select). Bar: Missed Transfer % and Missed If Connection On Time % by hub. Line: Missed Transfer % by `arrival_hour`. Matrix: `arrival_category` × `departure_category`, Missed Transfer %. Text box with the method and the "no walking time" caveat |

Slicers on every page: hub, `train_category` (where it applies), month.

## 4. Check against SQL

With no filters, the report must show: Arrival On-Time % Hamburg 84.7 %, Hannover 64.5 %;
Missed Transfer % at buffer 5 = 17.8 %, 15 = 6.8 %.

Save as `powerbi/db_transfer_reliability.pbix` and export screenshots to `powerbi/screenshots/` for the README.
