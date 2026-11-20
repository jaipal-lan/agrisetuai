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
    # One-time convenience for hosts without a shell (e.g. Render free tier): when
    # true, seed reference + demo data on startup IF the catalogue is empty. Safe
    # to leave on (it no-ops once seeded); turn on, let it boot once, then off.
    auto_seed: bool = False

    # Extra exact CORS origins (comma-separated), e.g. the deployed web app:
    # CORS_ORIGINS=https://agrisetuai.vercel.app  (dev LAN origins stay allowed
    # via the built-in regex; use this for the staging/prod frontend).
    cors_origins: str = ""

    # OTP
    otp_ttl_seconds: int = 300
    master_otp: str = "123456"  # accepted only in dev_mode
    otp_max_per_window: int = 8
    otp_window_seconds: int = 600
    media_dir: str = "./var/media"
    media_max_bytes: int = 8 * 1024 * 1024          # images / PDFs
    media_video_max_bytes: int = 60 * 1024 * 1024   # packing / sample videos
    # How long a signed view-link for a PRIVATE file (KYC/ID docs) stays valid.
    # The link is only ever handed to the owner (/auth/me) or verification staff
    # (/admin/kyc); both re-fetch often, so a short window is plenty.
    media_token_ttl_seconds: int = 3600
    # Cloudinary object storage (product photos, videos, KYC docs, profile pics).
    # When all three are set, uploads go to Cloudinary's CDN (permanent URLs);
    # otherwise they fall back to local disk (fine for dev, ephemeral on Render).
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""

    # Logistics / routing. "haversine" computes straight-line distance between
    # mandal coordinates and scales it by road_distance_factor; swap in an
    # external maps/routing provider later behind the same distance service.
    distance_provider: str = "haversine"
    road_distance_factor: float = 1.3
    default_route_km: float = 40.0

    # SMS provider: "console" logs the OTP (dev/sandbox). Real gateways plug in by
    # setting SMS_PROVIDER + the keys below: "2factor" (India, uses sms_api_key;
    # ships a pre-approved DLT OTP template so no DLT registration is needed —
    # recommended), "fast2sms" (India, uses sms_api_key), "msg91" (sms_api_key=
    # authkey + msg91_template_id + sms_sender_id), "twilio" (twilio_account_sid +
    # twilio_auth_token + sms_sender_id as From).
    sms_provider: str = "console"
    sms_api_key: str = ""
    sms_sender_id: str = "AGRSTU"
    # Fast2SMS route for OTP: "otp" (dedicated OTP API — needs Fast2SMS website
    # verification) or "q" (Quick SMS — works immediately, no verification/DLT).
    fast2sms_route: str = "otp"
    # 2Factor.in: optional named OTP template (TWOFACTOR_TEMPLATE_NAME). Leave blank
    # to use 2Factor's default pre-approved OTP template (works out of the box).
    twofactor_template_name: str = ""
    msg91_template_id: str = ""
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""

    # Payment provider:
    #   "mock"    — in-app capture via POST /orders/{id}/pay (dev/demo only).
    #   "sandbox" — intent + our signed webhook (provider-shaped, no live API).
    #   "razorpay"— live/live-sandbox: create a real Razorpay Order for checkout;
    #               confirm via Razorpay's webhook (X-Razorpay-Signature = HMAC-
    #               SHA256 hex of the raw body with payment_webhook_secret).
    # The in-app /pay bypass is accepted ONLY for "mock" (or dev_mode); any other
    # provider must be paid through the real checkout + webhook.
    payment_provider: str = "mock"
    payment_webhook_secret: str = "dev-sandbox-webhook-secret"
    # Razorpay keys (only used when payment_provider == "razorpay").
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""

    # WhatsApp (via Gupshup BSP) for transactional alerts — order/payment/sale,
    # payout and dispute updates reach farmers where they actually are. Gated:
    # nothing is sent unless whatsapp_enabled is true AND the keys below are set
    # (so dev/tests never message anyone). Get these from your Gupshup app:
    #   gupshup_api_key  — the app's API key
    #   gupshup_source   — your WhatsApp Business number (digits, e.g. 9180...)
    #   gupshup_src_name — the Gupshup app name
    # Business-initiated messages outside the 24h session window need Gupshup-
    # approved message templates; see WHATSAPP_SETUP.md.
    whatsapp_enabled: bool = False
    gupshup_api_key: str = ""
    gupshup_source: str = ""
    gupshup_src_name: str = ""

    # A GPS point counts as "inside the delivery footprint" when the nearest
    # serviceable mandal is within this many km (else the UI says "not serviced
    # here yet" instead of snapping to a far-away mandal).
    serviceable_radius_km: float = 30.0

    # Token lifetime
    token_ttl_seconds: int = 60 * 60 * 24 * 7
    # Short-lived token proving phone ownership between OTP verify and the
    # register / password-reset submit (so the single-use OTP isn't re-sent).
    phone_token_ttl_seconds: int = 15 * 60
    # Minimum length for a self-chosen account password.
    password_min_length: int = 6

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
    # Escalate an open buyer request (RFQ) to field agents if no farmer has
    # accepted within this many hours (the "agents source it like a PO" flow).
    rfq_escalation_hours: int = 24

    # Live delivery tracking. Assumed last-mile speed for a live ETA from the
    # courier's distance-to-door, and the radius at which the buyer is pinged
    # that the courier is nearby.
    courier_speed_kmph: float = 25.0
    courier_nearby_km: float = 2.0

    # External cron: a shared secret that lets a free off-box pinger
    # (GitHub Actions / cron-job.org / UptimeRobot) call GET/POST /api/cron/run
    # to run the scheduled jobs (refresh prices, digests, reminders) AND keep a
    # sleep-when-idle free host awake. Empty = the endpoint is disabled.
    cron_token: str = ""

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
