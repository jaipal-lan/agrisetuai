"""Fetch live mandi prices from data.gov.in and push them to the deployed backend.

Run this from a machine on an Indian network (data.gov.in refuses foreign/cloud
datacenter IPs, so the Render server can't fetch directly). It:
  1. reads the data.gov.in key (env DATA_GOV_IN_API_KEY, else backend/.env),
  2. fetches up to LIMIT records,
  3. logs in to the backend as the superadmin,
  4. POSTs them to /api/admin/prices/import (upsert + stale-sweep).

Usage (PowerShell):
    python scripts/push_prices.py
Optional env: RENDER_API, ADMIN_PHONE, ADMIN_PW, LIMIT, DATA_GOV_IN_API_KEY
Schedule it (Windows Task Scheduler / cron) to keep prices fresh.
"""
import json
import os
import sys
import urllib.parse
import urllib.request

API_BASE = os.getenv("RENDER_API", "https://agrisetuai-backend.onrender.com").rstrip("/")
ADMIN_PHONE = os.getenv("ADMIN_PHONE", "919999999998")
ADMIN_PW = os.getenv("ADMIN_PW", "demo1234")
LIMIT = int(os.getenv("LIMIT", "2000"))
RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"


def _read_key() -> str:
    key = os.getenv("DATA_GOV_IN_API_KEY")
    if key:
        return key.strip()
    here = os.path.dirname(os.path.abspath(__file__))
    env_path = os.path.join(here, "..", "backend", ".env")
    try:
        for line in open(env_path, encoding="utf-8"):
            if line.strip().startswith("DATA_GOV_IN_API_KEY"):
                return line.split("=", 1)[1].strip().strip('"').strip()
    except OSError:
        pass
    sys.exit("No data.gov.in key: set DATA_GOV_IN_API_KEY or put it in backend/.env")


def _post(url: str, payload: dict, token: str | None = None) -> dict:
    data = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def main() -> None:
    key = _read_key()
    print(f"Fetching up to {LIMIT} rows from data.gov.in ...")
    params = {"api-key": key, "format": "json", "limit": str(LIMIT)}
    url = f"https://api.data.gov.in/resource/{RESOURCE}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "agrisetuai/price-push"}), timeout=60) as r:
        feed = json.loads(r.read().decode())
    records = feed.get("records", []) or []
    print(f"  got {len(records)} records (total available: {feed.get('total')})")
    if not records:
        sys.exit(f"data.gov.in returned no records (status={feed.get('status')}, msg={feed.get('message')})")

    print(f"Logging in to {API_BASE} as {ADMIN_PHONE} ...")
    tok = _post(f"{API_BASE}/api/auth/login", {"phone": ADMIN_PHONE, "password": ADMIN_PW}).get("token")
    if not tok:
        sys.exit("Login failed — check ADMIN_PHONE/ADMIN_PW.")
    print("Pushing records to the backend ...")
    res = _post(f"{API_BASE}/api/admin/prices/import", {"records": records}, token=tok)
    print("Result:", json.dumps(res))


if __name__ == "__main__":
    main()
