# Live collector (DB Timetables API)

## 1. Get API credentials

1. Register / log in at the **DB API Marketplace**: <https://developers.deutschebahn.com/db-api-marketplace>.
2. Tab **Anwendungen** (Applications) → create an application (only a name is required).
   It shows a **Client ID** and a **Client Secret**. The Client Secret is the API key.
3. **Katalog** → search for **Timetables** → open it → **Abonnieren** (subscribe).
4. Pick the **Free** plan (Nutzungsplan) → select your application → *Next* → *Fertig*.
5. Put both values into `.env` (never into code, never commit them):

   ```
   DB_CLIENT_ID=<Client ID>
   DB_API_KEY=<Client Secret>
   ```

They are sent as the `DB-Client-Id` / `DB-Api-Key` headers.

## 2. Rate limit

The Free plan allows **60 calls per minute** (Timetables product page on the DB API Marketplace,
checked 2026-10-21). The client spaces calls at least **3 s** apart (`API_MIN_INTERVAL_S`),
i.e. **≤ 20 calls/min**, a third of the limit. 429/5xx responses are retried with exponential
backoff (2 s, 4 s, 8 s, …) and `Retry-After` is honoured.

Calls per run: 1 `/fchg` per EVA (13 EVAs) + `/plan` only for hours not fetched yet
(on average ~1 per EVA per hour). At a 20-minute schedule that is ~17–18 calls (~1 min) per run.

## 3. Run once

```bash
source .venv/bin/activate
python -m src.collector.collect          # resolves EVAs on first run, then one snapshot
python -m src.collector.collect --refresh-stations   # force re-resolving EVA numbers
```

Overlapping runs are prevented by a lock file (`data/raw/api/.collect.lock`).

## 4. Schedule it for 2–4 weeks

Recommended interval: **every 20 minutes**. `/fchg` holds the latest forecast/actual time per
stop; the transform keeps the most recent snapshot per stop, so the interval is the maximum lag
between our last observation and the real departure.

### macOS / Linux: cron

```bash
mkdir -p logs
crontab -e
```

Add (one line; adjust the path):

```cron
*/20 * * * * cd /Users/taneeshkpatel/Desktop/kaggle/db-transfer-reliability && .venv/bin/python -m src.collector.collect >> logs/collector.log 2>&1
```

Check with `crontab -l` and `tail -f logs/collector.log`.

> **Laptop caveat:** cron does not run while the Mac sleeps, which would leave gaps in the data.
> Either keep it awake while plugged in (`System Settings → Battery → Options → Prevent automatic sleeping
> when the display is off`, or run `caffeinate -s` in a terminal), or run the collector on an always-on
> machine (Raspberry Pi, small cloud VM). Gaps are detected later by `quality_checks.py`.
> On recent macOS, cron may need **Full Disk Access** (System Settings → Privacy & Security) if the project
> is in a protected folder such as Desktop.

### Windows: Task Scheduler

PowerShell (adjust the path):

```powershell
$dir = "C:\path\to\db-transfer-reliability"
$action  = New-ScheduledTaskAction -Execute "$dir\.venv\Scripts\python.exe" `
           -Argument "-m src.collector.collect" -WorkingDirectory $dir
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) `
           -RepetitionInterval (New-TimeSpan -Minutes 20) -RepetitionDuration (New-TimeSpan -Days 28)
Register-ScheduledTask -TaskName "DB-Timetables-Collector" -Action $action -Trigger $trigger
```

Logs: Task Scheduler has no stdout redirect, so wrap the call in a `.bat` with `>> logs\collector.log 2>&1`
if you want a log file.

## 5. Storage

Raw XML is gzip-compressed. Exact sizes will be measured after the first runs (expect hundreds of MB
over four weeks, not GBs). Parsed parquet files are small.

## 6. Time zone and DST

API times are `YYMMddHHmm` in local time without an offset. Plan hours are computed by stepping in UTC
and converting to Europe/Berlin, so the hour sequence is correct across the **DST change on
25 Oct 2026 (03:00 → 02:00)**. During that repeated hour, local times are ambiguous; the transform step
documents how they are handled and flags affected rows.
