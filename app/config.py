from pydantic import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost/dbname"
    secret_key: str = "your-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    stripe_api_key: str = "your-stripe-api-key"
    debug: bool = False

    class Config:
        env_file = ".env"

settings = Settings()
