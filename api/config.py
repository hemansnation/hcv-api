from pydantic import BaseModel
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Configuration
    app_name: str = "HCV API"
    app_version: str = "1.0.0"
    app_env: str = "development"
    app_secret_key: str = "change-me-in-production"
    api_version: str = "v1"
    debug: bool = False

    # Database Configuration
    database_url: str = "postgresql://localhost/hcv_api"
    database_pool_min_size: int = 10
    database_pool_max_size: int = 20

    # Redis Configuration
    redis_url: str = "redis://localhost:6379"

    # Rate Limiting
    max_requests_per_minute: int = 60
    max_citations_per_request: int = 100
    rate_limit_per_minute: int = 60
    rate_limit_per_month: int = 10000

    # External APIs
    courtlistener_base_url: str = "https://www.courtlistener.com/api/rest/v4"
    courtlistener_token: str = ""
    justia_base_url: str = "https://supreme.justia.com/cases/federal/us"
    lexisnexis_api_key: str = ""
    westlaw_api_key: str = ""

    # Security
    api_key_algorithm: str = "HS256"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()