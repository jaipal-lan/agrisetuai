# KissanSetu price auto-importer

Keeps the market-price screen fresh **automatically, daily**, from an Indian IP.

## Why this exists

`data.gov.in` (AGMARKNET) **refuses connections from the backend's datacenter IP**
(`ConnectionRefusedError 111` — confirmed via Admin → Price feed → *Diagnose feed*).
So the backend on Render can never fetch the feed itself. The feed **can** be fetched
from an Indian IP. This importer runs on an India-region host, pulls today's mandi
prices, and pushes them to the backend's token-protected import endpoint
(`POST /api/cron/import-prices`). Same upsert + stale-sweep as a live refresh.

It needs three secrets:

| Var | Value |
|---|---|
| `DATA_GOV_IN_API_KEY` | your data.gov.in key (same as on the backend) |
| `BACKEND_URL` | your Render backend, e.g. `https://agrisetuai-backend.onrender.com` |
| `CRON_TOKEN` | **the same** value set as `CRON_TOKEN` on the backend |

---

## Option A — Fly.io, Mumbai region (recommended: always-on, automatic)

Fly.io has an India region (`bom` = Mumbai), so the machine gets an Indian IP.
A *scheduled machine* runs the script once a day and exits (costs ~nothing).

**One-time setup** (install flyctl first: <https://fly.io/docs/flyctl/install/>, then `fly auth login`):

```bash
cd scripts/price-importer

# 1. Create the app (no deploy yet). Pick a unique name if this one is taken.
fly launch --no-deploy --name kissansetu-price-importer --region bom

# 2. Set the three secrets.
fly secrets set \
  DATA_GOV_IN_API_KEY="<your data.gov.in key>" \
  BACKEND_URL="https://<your-render-backend>.onrender.com" \
  CRON_TOKEN="<same token as on the backend>"

# 3. Build + push the image.
fly deploy

# 4. Test it once immediately — should print "DONE: upserted N prices".
fly machine run . --region bom

# 5. Schedule it to run every day automatically.
fly machine run . --region bom --schedule daily
```

- `--schedule daily` runs the machine ~once every 24h (Fly picks the time; fine for
  daily mandi prices). `hourly`, `weekly`, `monthly` also exist.
- Check runs/logs: `fly logs` or `fly machine list`.
- To update the code later: `fly deploy` again.

> Note: Fly's free allowance covers a tiny once-a-day machine, but Fly requires a
> card on file. Usage here is a few seconds of a shared-cpu-1x machine per day.

---

## Option B — Your own Windows PC (free, but PC must be on)

No new accounts. Runs on your PC, which already has an Indian IP. The catch: your
PC must be powered on at the scheduled time.

1. Edit **`run-importer.bat`** and fill in the three values at the top.
2. Double-click it once to test — you should see `DONE: upserted N prices`.
3. Schedule it daily with **Task Scheduler**:
   - Open *Task Scheduler* → *Create Basic Task* → name it "KissanSetu prices".
   - Trigger: *Daily*, time e.g. 7:00 AM.
   - Action: *Start a program* → Program/script: full path to `run-importer.bat`.
   - Finish. (Tip: in the task's properties, tick *Run whether user is logged on or
     not* so it runs in the background.)

---

## Option C — any other Indian server (cron)

On any Linux box with an Indian IP:

```bash
export DATA_GOV_IN_API_KEY=... BACKEND_URL=https://... CRON_TOKEN=...
python3 import_prices.py
```

Add a crontab line for 6 AM IST daily:

```
0 6 * * * DATA_GOV_IN_API_KEY=... BACKEND_URL=https://... CRON_TOKEN=... /usr/bin/python3 /path/to/import_prices.py >> /var/log/ks-prices.log 2>&1
```

---

## Verify it worked

After a run, open **Admin → Price feed**: *last refresh* should be just now and the
public prices should show today's date. The script prints the upserted count and the
feed's `as_of` date on success.
