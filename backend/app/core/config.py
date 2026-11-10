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
