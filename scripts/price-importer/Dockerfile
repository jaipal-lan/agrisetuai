# Tiny image for the KissanSetu price auto-importer (runs once and exits).
FROM python:3.12-slim
WORKDIR /app
COPY import_prices.py .
# Secrets (DATA_GOV_IN_API_KEY, BACKEND_URL, CRON_TOKEN) are provided at runtime
# via `fly secrets set` (or -e for a local docker run), never baked into the image.
ENTRYPOINT ["python", "import_prices.py"]
