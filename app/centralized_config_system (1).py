"""
Centralized configuration management with Pydantic validation.
Single source of truth for all environment variables and settings.
"""
import os
from typing import Optional, Literal
from pydantic import BaseSettings, Field, validator, HttpUrl, EmailStr
from pydantic.networks import PostgresDsn, RedisDsn


class Settings(BaseSettings):
    """Application settings with validation and environment variable loading."""
    
    # Application
    debug: bool = Field(default=False, env="DEBUG")
    environment: Literal["development", "staging", "production"] = Field(
        default="development", env="ENVIRONMENT"
    )
    api_title: str = Field(default="SaaS Sheets AI", env="API_TITLE")
    api_version: str = Field(default="1.0.0", env="API_VERSION")
    
    # Server
    host: str = Field(default="0.0.0.0", env="HOST")
    port: int = Field(default=8000, env="PORT")
    workers: int = Field(default=1, env="WORKERS")
    
    # Database - Required
    database_url: PostgresDsn = Field(env="DATABASE_URL")
    redis_url: RedisDsn = Field(env="REDIS_URL")
    
    # Security - Required
    jwt_secret: str = Field(min_length=32, env="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", env="JWT_ALGORITHM")
    jwt_expiration_hours: int = Field(default=24, env="JWT_EXPIRATION_HOURS")
    
    # Stripe - Required
    stripe_secret_key: str = Field(regex=r"^sk_(test_|live_).+", env="STRIPE_SECRET_KEY")
    stripe_publishable_key: str = Field(regex=r"^pk_(test_|live_).+", env="STRIPE_PUBLISHABLE_KEY")
    stripe_webhook_secret: str = Field(regex=r"^whsec_.+", env="STRIPE_WEBHOOK_SECRET")
    
    # LLM Providers - At least one required
    openai_api_key: Optional[str] = Field(None, regex=r"^sk-.+", env="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(None, regex=r"^sk-ant-.+", env="ANTHROPIC_API_KEY")
    default_llm_provider: Literal["openai", "anthropic"] = Field(
        default="openai", env="DEFAULT_LLM_PROVIDER"
    )
    
    # Email Configuration
    smtp_host: Optional[str] = Field(None, env="SMTP_HOST")
    smtp_port: int = Field(default=587, env="SMTP_PORT")
    smtp_user: Optional[EmailStr] = Field(None, env="SMTP_USER")
    smtp_password: Optional[str] = Field(None, env="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, env="SMTP_USE_TLS")
    from_email: Optional[EmailStr] = Field(None, env="FROM_EMAIL")
    
    # Frontend URLs
    frontend_url: HttpUrl = Field(default="https://sheets.google.com", env="FRONTEND_URL")
    api_base_url: HttpUrl = Field(default="https://api.yourapp.com", env="API_BASE_URL")
    
    # Rate Limiting
    rate_limit_calls_per_minute: int = Field(default=100, env="RATE_LIMIT_CALLS_PER_MINUTE")
    rate_limit_burst: int = Field(default=20, env="RATE_LIMIT_BURST")
    
    # Credits System
    free_trial_credits: int = Field(default=10, env="FREE_TRIAL_CREDITS")
    max_credits_per_user: int = Field(default=100000, env="MAX_CREDITS_PER_USER")
    
    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        default="INFO", env="LOG_LEVEL"
    )
    log_format: Literal["json", "text"] = Field(default="json", env="LOG_FORMAT")
    
    # Monitoring (Optional)
    sentry_dsn: Optional[str] = Field(None, env="SENTRY_DSN")
    prometheus_multiproc_dir: Optional[str] = Field(None, env="PROMETHEUS_MULTIPROC_DIR")
    
    # CORS Configuration
    cors_origins: list[str] = Field(
        default=["https://script.google.com", "https://sheets.google.com"],
        env="CORS_ORIGINS"
    )
    
    @validator("cors_origins", pre=True)
    def parse_cors_origins(cls, v):
        """Parse comma-separated CORS origins from environment variable."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v
    
    @validator("jwt_secret")
    def validate_jwt_secret_strength(cls, v):
        """Ensure JWT secret is not a common weak value."""
        weak_secrets = {
            "secret", "changeme", "your-secret-key", "jwt-secret", 
            "supersecret", "my-secret", "test-secret"
        }
        if v.lower() in weak_secrets:
            raise ValueError("JWT secret appears to be a default/weak value")
        return v
    
    @validator("environment")
    def validate_production_settings(cls, v, values):
        """Enforce stricter validation in production environment."""
        if v == "production":
            # Debug must be False in production
            if values.get("debug"):
                raise ValueError("DEBUG must be False in production")
            
            # Require HTTPS URLs in production
            frontend_url = values.get("frontend_url")
            api_base_url = values.get("api_base_url")
            
            if frontend_url and not str(frontend_url).startswith("https://"):
                raise ValueError("FRONTEND_URL must use HTTPS in production")
            if api_base_url and not str(api_base_url).startswith("https://"):
                raise ValueError("API_BASE_URL must use HTTPS in production")
            
            # Require Stripe live keys in production
            stripe_secret = values.get("stripe_secret_key", "")
            stripe_public = values.get("stripe_publishable_key", "")
            
            if stripe_secret.startswith("sk_test_"):
                raise ValueError("Must use Stripe live keys in production (not test keys)")
            if stripe_public.startswith("pk_test_"):
                raise ValueError("Must use Stripe live keys in production (not test keys)")
        
        return v
    
    @validator("default_llm_provider")
    def validate_llm_provider_availability(cls, v, values):
        """Ensure the default LLM provider has a valid API key."""
        openai_key = values.get("openai_api_key")
        anthropic_key = values.get("anthropic_api_key")
        
        if v == "openai" and not openai_key:
            raise ValueError("OPENAI_API_KEY required when using OpenAI as default provider")
        elif v == "anthropic" and not anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY required when using Anthropic as default provider")
        
        # Ensure at least one LLM provider is configured
        if not openai_key and not anthropic_key:
            raise ValueError("At least one LLM provider API key must be configured")
        
        return v
    
    @validator("smtp_host")
    def validate_email_config(cls, v, values):
        """If SMTP host is provided, ensure other email settings are configured."""
        if v:
            required_email_fields = ["smtp_user", "smtp_password", "from_email"]
            missing_fields = [
                field for field in required_email_fields 
                if not values.get(field)
            ]
            if missing_fields:
                raise ValueError(
                    f"Email configuration incomplete. Missing: {', '.join(missing_fields)}"
                )
        return v
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        # Validate assignment to catch runtime changes
        validate_assignment = True
        
        @classmethod
        def customise_sources(
            cls,
            init_settings,
            env_settings,
            file_secret_settings,
        ):
            """Prioritize environment variables over .env file."""
            return (
                init_settings,
                env_settings,
                file_secret_settings,
            )


# Global settings instance
try:
    settings = Settings()
except Exception as e:
    print(f"❌ Configuration Error: {e}")
    print("\n🔧 Required Environment Variables:")
    print("   DATABASE_URL - PostgreSQL connection string")
    print("   REDIS_URL - Redis connection string") 
    print("   JWT_SECRET - JWT signing secret (min 32 chars)")
    print("   STRIPE_SECRET_KEY - Stripe secret key (sk_test_* or sk_live_*)")
    print("   STRIPE_PUBLISHABLE_KEY - Stripe publishable key")
    print("   STRIPE_WEBHOOK_SECRET - Stripe webhook secret (whsec_*)")
    print("   OPENAI_API_KEY or ANTHROPIC_API_KEY - At least one LLM provider")
    print("\n📖 See .env.example for complete configuration template")
    exit(1)


def get_settings() -> Settings:
    """Get the global settings instance."""
    return settings


def validate_runtime_config():
    """Perform additional runtime configuration validation."""
    import asyncio
    import logging
    
    logger = logging.getLogger(__name__)
    
    async def check_database_connection():
        """Validate database connectivity."""
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(str(settings.database_url), pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Database connection validated")
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False
        return True
    
    async def check_redis_connection():
        """Validate Redis connectivity."""
        try:
            import redis
            redis_client = redis.from_url(str(settings.redis_url))
            redis_client.ping()
            logger.info("✅ Redis connection validated")
        except Exception as e:
            logger.error(f"❌ Redis connection failed: {e}")
            return False
        return True
    
    async def check_llm_providers():
        """Validate LLM provider API keys."""
        valid_providers = []
        
        if settings.openai_api_key:
            try:
                # Basic format validation only (avoid actual API calls during startup)
                assert settings.openai_api_key.startswith("sk-")
                valid_providers.append("openai")
                logger.info("✅ OpenAI API key format validated")
            except Exception as e:
                logger.warning(f"⚠️ OpenAI API key validation failed: {e}")
        
        if settings.anthropic_api_key:
            try:
                assert settings.anthropic_api_key.startswith("sk-ant-")
                valid_providers.append("anthropic")
                logger.info("✅ Anthropic API key format validated")
            except Exception as e:
                logger.warning(f"⚠️ Anthropic API key validation failed: {e}")
        
        if not valid_providers:
            logger.error("❌ No valid LLM providers configured")
            return False
        
        return True
    
    # Run validation checks
    async def run_all_checks():
        checks = await asyncio.gather(
            check_database_connection(),
            check_redis_connection(), 
            check_llm_providers(),
            return_exceptions=True
        )
        
        failed_checks = [i for i, check in enumerate(checks) if not check]
        if failed_checks:
            logger.error(f"❌ Configuration validation failed ({len(failed_checks)} checks)")
            return False
        
        logger.info("✅ All configuration checks passed")
        return True
    
    return asyncio.run(run_all_checks())


# Environment-specific configuration helpers
def is_production() -> bool:
    """Check if running in production environment."""
    return settings.environment == "production"


def is_development() -> bool:
    """Check if running in development environment."""
    return settings.environment == "development"


def get_database_url() -> str:
    """Get the database URL as a string."""
    return str(settings.database_url)


def get_redis_url() -> str:
    """Get the Redis URL as a string.""" 
    return str(settings.redis_url)