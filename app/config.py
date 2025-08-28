from pydantic import BaseSettings, AnyHttpUrl
from typing import List

class Settings(BaseSettings):
    app_name: str = "SaaS Sheets AI Functions"
    debug: bool = True
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/saas_sheets"
    redis_url: str = "redis://localhost:6379/0"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"

    # Stripe
    stripe_secret_key: str = "sk_test_change_me"
    stripe_webhook_secret: str = "whsec_change_me"

    # CORS
    cors_origins: List[str] = [
        "https://script.google.com",
        "https://script.googleusercontent.com",
        "https://docs.google.com",
        "http://localhost:3000",
    ]

    class Config:
        env_file = ".env"

settings = Settings()
