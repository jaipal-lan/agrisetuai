#!/usr/bin/env python3
"""KissanSetu market-price auto-importer.

data.gov.in refuses the backend's datacenter IP (ConnectionRefusedError), so the
feed cannot be pulled server-side from Render. This tiny script fetches today's
mandi prices from data.gov.in and POSTs them to the backend's token-protected
import endpoint. It MUST run from an Indian IP — schedule it on an India-region
host (Fly.io Mumbai region is set up in this folder) or any Indian machine.

Standard library only — no pip install needed.

Required env vars:
  DATA_GOV_IN_API_KEY   your data.gov.in API key
  BACKEND_URL           e.g. https://agrisetuai-backend.onrender.com
  CRON_TOKEN            must equal CRON_TOKEN set on the backend
Optional:
  PRICES_LIMIT          page size per data.gov.in request (default 1000)
"""
import json
import os
import sys
import urllib.parse
import urllib.request

# "Current Daily Price of Various Commodities from Various Markets (Mandi)".
RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
API = f"https://api.data.gov.in/resource/{RESOURCE}"


def _env(name: str) -> str:
    val = (os.environ.get(name) or "").strip()
    if not val:
        sys.exit(f"ERROR: missing required env var {name}")
    return val


def fetch_all(api_key: str, page: int) -> list[dict]:
    """Pull every reported row via offset pagination."""
    out: list[dict] = []
    offset = 0
    while True:
        qs = urllib.parse.urlencode(
            {"api-key": api_key, "format": "json", "limit": page, "offset": offset}
        )
        req = urllib.request.Request(
            f"{API}?{qs}", headers={"User-Agent": "kissansetu-price-importer"}
        )
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 (fixed gov URL)
            data = json.loads(resp.read().decode("utf-8"))
        recs = data.get("records") or []
        out.extend(recs)
        print(f"fetched {len(out)} rows...", flush=True)
        if len(recs) < page:
            break
        offset += page
        if offset > 100000:  # safety cap
            break
    return out


def push(backend_url: str, token: str, records: list[dict]) -> dict:
    url = (f"{backend_url.rstrip('/')}/api/cron/import-prices?"
           + urllib.parse.urlencode({"token": token}))
    body = json.dumps({"records": records}).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json",
                 "User-Agent": "kissansetu-price-importer"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> None:
    api_key = _env("DATA_GOV_IN_API_KEY")
    backend_url = _env("BACKEND_URL")
    token = _env("CRON_TOKEN")
    page = int(os.environ.get("PRICES_LIMIT", "1000"))

    try:
        records = fetch_all(api_key, page)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"ERROR fetching data.gov.in (are you on an Indian IP?): {exc!r}")

    if not records:
        sys.exit("ERROR: data.gov.in returned no records.")

    try:
        result = push(backend_url, token, records)
    except Exception as exc:  # noqa: BLE001
        sys.exit(f"ERROR pushing to backend: {exc!r}")

    print("import result:", json.dumps(result), flush=True)
    if not result.get("ok"):
        sys.exit(1)
    print(f"DONE: upserted {result.get('upserted')} prices "
          f"(as of {result.get('as_of')}).", flush=True)


if __name__ == "__main__":
    main()
