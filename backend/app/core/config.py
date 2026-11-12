from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    dev_mode: bool = True
    database_url: str = "sqlite:///./agrisetu.db"
    auth_secret: str = ""
    currency: str = "INR"
    superadmin_phone: str = "919999999998"
    # Run `alembic upgrade head` on startup. Keep true for dev; set false in
    # production and run migrations from the deploy pipeline instead.
    auto_migrate: bool = True

    # OTP
    otp_ttl_seconds: int = 300
    master_otp: str = "123456"  # accepted only in dev_mode
    otp_max_per_window: int = 8
    otp_window_seconds: int = 600
    media_dir: str = "./var/media"
    media_max_bytes: int = 8 * 1024 * 1024

    # Logistics / routing. "haversine" computes straight-line distance between
    # mandal coordinates and scales it by road_distance_factor; swap in an
    # external maps/routing provider later behind the same distance service.
    distance_provider: str = "haversine"
    road_distance_factor: float = 1.3
    default_route_km: float = 40.0

    # SMS provider: "console" logs the OTP (dev/sandbox); swap for a real gateway
    # (Twilio/MSG91/Gupshup) by setting the provider + keys in production.
    sms_provider: str = "console"
    sms_api_key: str = ""
    sms_sender_id: str = "AGRSTU"

    # Payment provider: "mock" (in-app capture) or "sandbox" (intent + signed
    # webhook flow, same shape as a real marketplace provider). Real keys plug in.
    payment_provider: str = "mock"
    payment_webhook_secret: str = "dev-sandbox-webhook-secret"

    # Token lifetime
    token_ttl_seconds: int = 60 * 60 * 24 * 7

    # Market-price feed. "sample" uses the seeded demo rows (default, so dev and
    # tests need no network or key). Set to "data_gov_in" and provide a key from
    # https://data.gov.in to pull live AGMARKNET mandi prices on demand
    # (POST /api/admin/prices/refresh) and on the scheduler tick.
    prices_provider: str = "sample"
    data_gov_in_api_key: str = ""
    prices_feed_limit: int = 500
    # When the scheduler loop is on, refresh live prices at most this often (hours),
    # so a short scheduler interval doesn't hammer data.gov.in.
    prices_refresh_hours: int = 12
    # Optional comma-separated whitelists for the live feed (empty = fetch all).
    prices_feed_commodities: str = ""
    prices_feed_states: str = ""
    # Prices older than this (hours) are considered stale and flagged in Admin.
    prices_stale_hours: int = 48
    # Remind meeting attendees this many hours before a scheduled team meeting.
    meeting_reminder_hours: int = 24

    # Live delivery tracking. Assumed last-mile speed for a live ETA from the
    # courier's distance-to-door, and the radius at which the buyer is pinged
    # that the courier is nearby.
    courier_speed_kmph: float = 25.0
    courier_nearby_km: float = 2.0

    # Background scheduler (sandboxed): compiles daily digests and raises due
    # follow-up reminders on a timer. 0 disables the in-process loop (the default,
    # so tests and plain dev runs are unaffected); set >0 seconds to enable it.
    # The job can always be run on demand via POST /api/admin/scheduler/run.
    scheduler_interval_seconds: int = 0

    @property
    def effective_secret(self) -> str:
        if self.auth_secret:
            return self.auth_secret
        if self.dev_mode:
            return "dev-only-insecure-secret-change-me"
        raise RuntimeError(
            "AUTH_SECRET must be set when DEV_MODE is false."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
