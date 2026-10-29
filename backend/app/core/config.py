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

    # Token lifetime
    token_ttl_seconds: int = 60 * 60 * 24 * 7

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
