@echo off
REM ---------------------------------------------------------------------------
REM KissanSetu price importer — Windows fallback (runs on YOUR PC, an Indian IP).
REM Use this if you don't set up the Fly.io Mumbai machine. Schedule it daily via
REM Windows Task Scheduler (see README.md). Your PC must be on at the scheduled
REM time for it to run.
REM
REM Fill in the three values below (or set them as system env vars and delete
REM these lines). Keep this file private — it contains your token/key.
REM ---------------------------------------------------------------------------
set DATA_GOV_IN_API_KEY=PUT_YOUR_DATA_GOV_IN_KEY_HERE
set BACKEND_URL=https://PUT-YOUR-RENDER-BACKEND.onrender.com
set CRON_TOKEN=PUT_THE_SAME_CRON_TOKEN_AS_ON_THE_BACKEND

python "%~dp0import_prices.py"
