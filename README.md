# F1 Laps

A self-hosted web app for comparing Formula 1 lap times. Pick a season, Grand Prix
and session (FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint, Race), then
compare the pace of any set of drivers lap by lap, see where they changed tyres,
and read the sector and stint numbers underneath.

Data comes from the official F1 live-timing feed via the
[FastF1](https://docs.fastf1.dev/) library (2018 onwards). The app checks for
new session data automatically on Friday, Saturday and Sunday evenings and on
demand with the **Check for new data** button.

## Features

- **Session picker**: season → Grand Prix → session. Sessions that are not
  available yet are shown greyed out.
- **Line chart** of lap time (or sector time, or gap to a reference driver) vs
  lap number, one line per driver in team colours (second car dashed).
- **Tyre-change markers** on each line, coloured by compound (soft red, medium
  yellow, hard white, intermediate green, wet blue).
- **Driver panel** grouped by team with best lap and gap to the session-best lap;
  add/remove drivers with checkboxes, or use All / Top 10 / Top 5 / None.
- **Tight y-axis** by default: slow outliers are cut so 2–3 s differences fill the
  plot. In/out laps and Safety Car / VSC / yellow-flag laps are hidden by default
  (all toggleable). Scroll/pinch to zoom, drag to pan.
- **Smoothing** (3- or 5-lap rolling average) to see who improved or faded.
- **Summary table** with best, average, median and ideal lap, best S1/S2/S3,
  a first-half vs second-half trend, and the tyre stints of every driver.
- **Sharable URLs**: the selected session, drivers and metric live in the URL hash.
- **Mobile layout**: driver chips, collapsible options, touch zoom, and a
  web-app manifest so it can be added to the home screen.
- **Scheduled + manual data checks** with a visible status/history.

See [docs/DESIGN.md](docs/DESIGN.md) for the requirements review, the
architecture, and how sector data is integrated.

## Architecture

```
 browser  ──HTTPS──▶  Caddy  ──▶  FastAPI (uvicorn)  ──▶  SQLite (/data/f1laps.db)
                                    │  APScheduler (Fri/Sat/Sun check)
                                    └─ FastF1 ──▶ F1 live timing API (+ on-disk cache)
```

| Part | Technology | Notes |
|---|---|---|
| Backend | Python 3.12, FastAPI, SQLAlchemy, APScheduler | `backend/` |
| Data | FastF1, pandas | fetch + normalise laps, sectors, stints, track status |
| Database | SQLite (WAL) | one file on a Docker volume, no DB server to run |
| Frontend | React 18, TypeScript, Vite, Apache ECharts | `frontend/`, built to static files |
| Runtime | Docker Compose: app + Caddy | Caddy gives automatic HTTPS |
| Deployment | GitHub Actions → GHCR → SSH → `docker compose up` | `.github/workflows/deploy.yml` |

Everything runs on a single small Linux VM (1 vCPU / 1 GB RAM is enough; the
FastF1 cache for two seasons is a few GB of disk).

## Local development

Backend (Python 3.11+):

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                       # unit tests (no network needed)
f1laps demo-seed             # optional: synthetic race so the UI has data offline
f1laps refresh               # fetch every finished session of the configured seasons
f1laps serve                 # http://localhost:8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev                  # http://localhost:5173, proxies /api to :8000
npm run build                # -> frontend/dist
```

To serve the built frontend from the backend locally, point
`F1LAPS_STATIC_DIR` at `frontend/dist`.

### Configuration

All settings are environment variables with the prefix `F1LAPS_`
(see `backend/f1laps/config.py`):

| Variable | Default | Meaning |
|---|---|---|
| `F1LAPS_DATA_DIR` | `./data` | SQLite database + FastF1 cache |
| `F1LAPS_STATIC_DIR` | `./static` | built frontend to serve at `/` |
| `F1LAPS_SEASONS` | `2025,2026` | seasons to keep in sync |
| `F1LAPS_REFRESH_DAYS` | `fri,sat,sun` | days of the scheduled check |
| `F1LAPS_REFRESH_TIME` | `23:30` | local time of the check |
| `F1LAPS_REFRESH_TZ` | `UTC` | time zone for the schedule, e.g. `America/New_York` |
| `F1LAPS_REFRESH_ON_STARTUP` | `true` | run a check shortly after the service starts |
| `F1LAPS_SESSION_GRACE_MINUTES` | `180` | a session is fetchable this long after its start |
| `F1LAPS_MAX_FETCH_ATTEMPTS` | `12` | give up on a session after this many failures |

### API

| Endpoint | Purpose |
|---|---|
| `GET /api/seasons` | seasons and how many events are known |
| `GET /api/seasons/{year}/events` | events with their sessions and data status |
| `GET /api/sessions/{id}` | drivers, per-driver stats and all laps of a session |
| `POST /api/refresh` | start a data check (`{"season": 2025, "session_id": 12, "force": false}` all optional) |
| `GET /api/refresh/status` | running/last/next check |
| `GET /api/health` | liveness |

## Deployment

The `Deploy` workflow runs on every push to `main` (and manually via
*Run workflow*). It builds the image, pushes it to
`ghcr.io/thehatchcloud/f1laps`, copies `deploy/docker-compose.yml` and
`deploy/Caddyfile` to the server, and runs `docker compose up -d` over SSH.
The `CI` workflow runs tests and builds on every pull request.

One-time server setup (Ubuntu/Debian VM, as root):

```bash
curl -fsSL https://raw.githubusercontent.com/thehatchcloud/f1laps/main/deploy/server-setup.sh | bash
```

This installs Docker, creates a `deploy` user, and writes `/opt/f1laps/.env`.
Then:

1. Generate a deploy key locally: `ssh-keygen -t ed25519 -f f1laps_deploy -N ""`
   and append `f1laps_deploy.pub` to `/home/deploy/.ssh/authorized_keys` on the server.
2. Edit `/opt/f1laps/.env`: set `SITE_ADDRESS` to your domain for automatic
   HTTPS (DNS must already point at the server) or leave `:80` for plain HTTP,
   and set `F1LAPS_REFRESH_TZ` to your time zone.
3. In the GitHub repository add the secrets `DEPLOY_HOST`, `DEPLOY_USER`
   (`deploy`), `DEPLOY_SSH_KEY` (contents of `f1laps_deploy`) and optionally
   `DEPLOY_PORT`. Optionally create a `production` environment to require approval.
4. Push to `main` or run the *Deploy* workflow. The first start triggers a data
   check after 15 s; the first full season download takes a while (a few minutes
   per session on a small VM).

Useful commands on the server:

```bash
cd /opt/f1laps
docker compose logs -f app                       # follow the app log
docker compose exec app f1laps refresh --season 2024   # backfill another season
docker compose exec app f1laps refresh --force   # re-download everything
```

## Data notes

- Lap, sector and tyre data are what the F1 timing feed publishes; FastF1
  flags laps it could not time accurately, and the app excludes those, in/out
  laps and non-green laps from the averages.
- "Clean laps" for the averages are green-flag, non-pit laps within 107 % of the
  driver's best lap, so cool-down laps in practice do not skew the numbers.
- Deleted laps (track limits) keep their time and are shown, but never count as
  a driver's best.
- The F1 timing feed usually has a session available within an hour or two of
  its end; a session that is not there yet is retried on the next check.
