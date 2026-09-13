# F1 Laps – requirements review and design

## 1. Requirements review

| # | Requirement | Decision |
|---|---|---|
| 1 | Select season → race → session | Three cascading selects in the header. The calendar comes from the FastF1 schedule, so future sessions appear (greyed out) before they have data. |
| 2 | Show drivers and their team | Driver panel grouped by team, in team colours; the second car of a team uses a dashed line so team-mates are distinguishable without extra colours. |
| 3 | Line chart, x = lap, y = lap time | Apache ECharts line chart, one series per driver. Canvas rendering keeps 20 × 70 points smooth on phones. |
| 4 | Add / remove drivers | Checkboxes in the panel and in the table, chips on mobile, plus All / Top 10 / Top 5 / None. Selection is kept in the URL so a comparison can be shared. |
| 5 | Show tyre changes | A marker on the first flying lap of each new stint, filled with the compound colour and outlined in the team colour. The tooltip names the compound and the stint. |
| 6 | Y-axis that shows 2–3 s differences | "Tight" mode: range from the fastest shown lap to the 85th percentile (+0.8 s), at least 2.5 s tall. In/out laps and SC/VSC/yellow laps are filtered out by default because they are what flattens a lap chart. "Full" mode and shift+scroll / pinch zoom exist for the rest. |
| 7 | Desktop full view, easy mobile access | Responsive layout at 900 px: side panel becomes a chip strip, options collapse, chart height follows the viewport, table scrolls sideways. A web-app manifest lets the user add it to the home screen. |
| 8 | Check for updates Fri/Sat/Sun evening + manual trigger | APScheduler cron inside the app (days, time and zone configurable) and a "Check for new data" button that calls `POST /api/refresh`. Status, history and next run are visible in the UI. |
| 9 | Own Linux server, GitHub Actions deploy | Docker Compose (app + Caddy) deployed over SSH by a workflow that builds the image in Actions and pushes it to GHCR, so the server only pulls. |

## 2. Why FastF1

Two sources cover what the app needs: the [OpenF1](https://openf1.org) REST
API and [FastF1](https://docs.fastf1.dev/), a Python library that reads the
same F1 live-timing feed the broadcast graphics use (plus the Jolpica/Ergast
API for schedules).

FastF1 was chosen because it

- provides laps, sector times, compound, tyre age, stint numbers, pit in/out
  times, track status per lap, deleted-lap flags and an "is accurate" flag in a
  single, well-documented data frame;
- covers 2018 to the current season, while OpenF1 starts in 2023;
- keeps a local HTTP cache, so a session is downloaded once and re-processing
  is free;
- has no API key or paid tier for historical data.

The trade-off is that it is a Python dependency with pandas, which is why the
backend is Python. Only the schedule and session download touch FastF1
(`backend/f1laps/ingest.py`); everything else works on plain rows, and
`store_session_data` is tested with hand-built data frames.

## 3. Architecture

```
                  ┌──────────────────────── server (Docker Compose) ───────────────────────┐
 phone/desktop ─▶ │ Caddy (HTTPS) ─▶ FastAPI                                                │
                  │                   ├─ /api/*            JSON                              │
                  │                   ├─ /                 built React app (static)          │
                  │                   ├─ RefreshRunner     one background thread at a time   │
                  │                   ├─ APScheduler       Fri/Sat/Sun 23:30 (configurable) │
                  │                   └─ FastF1 ─▶ livetiming.formula1.com (cache on /data) │
                  │                   SQLite  /data/f1laps.db                               │
                  └──────────────────────────────────────────────────────────────────────────┘
```

**Backend** (`backend/f1laps/`)

- `config.py` – settings from `F1LAPS_*` environment variables.
- `db.py` – SQLAlchemy models: `events`, `sessions`, `session_drivers`,
  `laps`, `refresh_runs`.
- `ingest.py` – `sync_schedule`, `fetch_session_frames`, `store_session_data`,
  `run_refresh`. A session is "due" when it started more than
  `session_grace_minutes` ago and is not stored; failures are retried on the
  next check up to `max_fetch_attempts`.
- `analysis.py` – per-driver statistics (best/avg/median/ideal lap, best
  sectors, stints with degradation slope, first-half vs second-half trend).
- `refresh.py` / `scheduler.py` – background runner with status, cron trigger.
- `main.py` – the API and static file serving.
- `demo.py` – synthetic race for trying the UI without network access.

**Frontend** (`frontend/src/`)

- `series.ts` – turns laps into chart points: filtering, smoothing, gap to a
  reference driver, tyre-change detection, tight y-range.
- `chart/LapChart.tsx` – ECharts configuration and the axis tooltip.
- `components/` – session picker, driver panel, controls, summary table,
  refresh bar. `hashState.ts` keeps session/drivers/metric in the URL.

**Database**: SQLite is deliberate. The data set is small (a race is ~1,400
lap rows), writes happen a few times a weekend, reads are one query per page
load, and a single file on a volume is the simplest thing to back up.

## 4. Sector data: how it is integrated

Sector times are useful for two questions: *where* a car is fast, and whether
a lap-time difference comes from one corner sequence or from everywhere.
Putting three more lines per driver on the lap chart answers neither and
triples the clutter. The app therefore keeps one chart and one y-axis and
exposes sectors in three places:

1. **Metric switch** ("Show: Lap time / Sector 1 / Sector 2 / Sector 3 / Gap to
   driver"). The chart, its interactions and the y-range logic are identical;
   only the quantity changes. Comparing S2 of two drivers over a stint is one
   click away and never mixed with lap times on the same axis.
2. **Tooltip**: hovering a lap lists every shown driver with lap time, tyre and
   tyre age, and the three sector times, so the split of a single lap is
   visible without switching the metric.
3. **Summary table**: best S1/S2/S3 per driver with the session-best in each
   column highlighted, plus the *ideal lap* (sum of best sectors) next to the
   real best lap. A large ideal-vs-best gap says a driver never put a lap
   together; a driver who is best in one sector but slow overall points at a
   car characteristic.

Together this keeps the chart focused on pace and trend, which is the reason
for the app, while sectors are one interaction away.

## 5. Reading pace and trend

- **Clean laps** (green flag, not in/out, timed accurately) within 107 % of the
  driver's best are used for average and median; the threshold removes
  cool-down laps and traffic laps in practice/qualifying.
- **Smoothing** (3- or 5-lap rolling average) hides the lap-to-lap noise and
  shows who improved or faded over a stint.
- **Gap to driver** subtracts a reference driver's time on the same lap, which
  turns a race into a flat line around zero where the differences are obvious.
- **Trend** in the table is the average of the second half of a driver's clean
  laps minus the first half (negative = got faster); the per-stint degradation
  slope (in the stint chip tooltip) does the same within a stint.

## 6. Scheduled checks

The requirement is "end of the day Friday, Saturday and Sunday". The default
is 23:30 in `F1LAPS_REFRESH_TZ` (set it to your own time zone in
`/opt/f1laps/.env`). Because a check fetches *every* finished session that is
missing, a session that the timing feed publishes late is simply picked up by
the next check, and a race in a far time zone that ends after Sunday 23:30 is
fetched on the following Friday or by the manual button. The service also
runs a check 15 s after every start (a deploy or reboot), and the CLI
(`f1laps refresh`) works for backfilling older seasons.

Only one refresh runs at a time; the scheduled one is skipped if a manual one
is still running.

## 7. Deployment

- `deploy/Dockerfile` – multi-stage: Node builds the frontend, the Python
  image installs the backend and serves the static files. Runs as a non-root
  user, has a health check, stores everything under `/data`.
- `deploy/docker-compose.yml` – `app` + `caddy`. Caddy terminates TLS
  (automatic Let's Encrypt when `SITE_ADDRESS` is a domain) and caches the
  hashed assets.
- `.github/workflows/deploy.yml` – build in Actions, push to GHCR, SSH to the
  server, `docker compose pull && up -d`, wait for the health check. SSH was
  chosen over a pull-based agent because it needs nothing on the server beyond
  Docker and a key, and the workflow log shows exactly what happened.
- `deploy/server-setup.sh` – one-time provisioning of a fresh VM.

## 8. Possible next steps

- Qualifying view: best lap per Q1/Q2/Q3 segment rather than a lap sequence.
- Position chart for races (position vs lap) next to the pace chart.
- Track-status bands (SC/VSC/red) drawn on the x-axis instead of only hiding
  those laps.
- Weather (air/track temperature, rain) in the session header.
- Backfill 2018–2024 with `f1laps refresh --season YEAR`.
