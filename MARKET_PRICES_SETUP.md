# Market prices — live feed & automatic refresh

Market prices come from **data.gov.in / AGMARKNET** (daily government mandi
prices). They refresh automatically once the feed is configured and a scheduler
is pinging the service.

## Why prices can look stale

1. **No API key set.** `DATA_GOV_IN_API_KEY` is a `sync:false` secret in
   `render.yaml` — if it's empty, the feed is off and the app keeps serving the
   seeded sample rows (which never change). Admin → Market prices status shows
   `configured: false` in that case.
2. **The free instance sleeps.** On Render's free plan the service spins down
   when idle, so an in-process hourly timer rarely survives long enough to fire.
3. (Fixed in code) the timer used to wait a full hour *before* its first run.

## How to make it refresh automatically

### 1. Turn on the feed
Set on the backend (Render → Environment):
```
PRICES_PROVIDER=data_gov_in
DATA_GOV_IN_API_KEY=<your key from https://data.gov.in>   # free: register → profile → API key
PRICES_REFRESH_HOURS=12     # how often an actual fetch is allowed
```
Get a key: sign in at data.gov.in → **My Account → API key** (instant, free).

### 2. Set the cron secret
Set the same random string in **both** places:
- Render env: `CRON_TOKEN=<random-secret>`
- GitHub repo → Settings → Secrets and variables → Actions:
  - `CRON_TOKEN` = the same value
  - `BACKEND_URL` = e.g. `https://agrisetuai-backend.onrender.com`

### 3. The daily refresh (6 AM IST)
`.github/workflows/cron.yml` runs every morning at **06:00 IST**: it wakes the
backend, then calls `GET /api/cron/run?token=…&force_prices=1` to force a fresh
pull of the day's prices. The rows are stored in the database, so they stay
served even after the free web instance sleeps again — no always-on instance is
needed just for prices.

(You can run it any time from the GitHub **Actions tab → Run workflow**, or hit
the same URL from cron-job.org / UptimeRobot instead. If you also want the site
itself to respond instantly at all hours, add a separate UptimeRobot monitor on
`/api/health` every 10 min — optional; not needed for price freshness.)

## Verify
- `GET /api/cron/run?token=…` → returns a JSON report incl. `prices_refreshed`.
- Admin → Market prices (superadmin): the status shows `last_refresh_at`,
  row counts and freshness.
- `POST /api/admin/prices/refresh` (superadmin) forces an immediate fetch.

## Notes
- With the code change, every cold start also runs the jobs ~15s after boot, so
  prices refresh whenever the service wakes even without the external pinger
  (the pinger just makes it regular and keeps the instance warm).
- A paid always-on instance makes the in-process hourly timer sufficient on its
  own; the external cron is only needed because the free tier sleeps.
