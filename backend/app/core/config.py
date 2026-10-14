"""Application settings, loaded from environment variables.

Uses pydantic-settings to validate and type env vars at startup.
All secrets come from the environment; see .env.example for the full list.
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Validated application configuration.

    Every field maps to an environment variable (case-insensitive).
    Defaults are safe for local development; production overrides via env.
    """

    app_env: str = "development"
    log_level: str = "info"

    # Database (used from T0.3 onward)
    database_url: str = "postgresql+asyncpg://codecourt:codecourt@localhost:5432/codecourt"

    # GitHub (used from T1.1 onward)
    github_webhook_secret: str = ""
    github_token: str = ""

    # LLM (used from T2.1 onward)
    gemini_api_key: str = ""

    # Authentication & Rate Limiting (T6.1)
    jwt_secret_key: str = "dev-insecure-jwt-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60
    rate_limit_per_minute: int = 60
    rate_limit_trigger_per_minute: int = 10

    # Cost Caps & Budget Limits (T6.2)
    max_review_budget_usd: float = 0.50
    tenant_daily_budget_usd: float = 10.00
    circuit_breaker_token_limit: int = 50_000

    # Observability & Tracing (T6.3)
    langfuse_enabled: bool = False
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


def get_settings() -> Settings:
    """Return a cached Settings instance.

    Called once at app startup; FastAPI dependency injection uses this.
    """
    return Settings()
