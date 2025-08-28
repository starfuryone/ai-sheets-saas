#!/usr/bin/env python3
"""
Validate environment configuration before deployment.
Checks for required variables, database & redis connectivity, and external services.
Exit code 0 = OK, 1 = problems detected.
"""
import os
import sys
import logging
from typing import List, Dict, Any
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnvironmentValidator:
    """Validates environment configuration for production deployment."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def validate_all(self) -> bool:
        """Run all validation checks."""
        logger.info("Starting environment validation...")

        self.validate_required_variables()
        self.validate_optional_variables()
        self.validate_jwt_configuration()
        self.validate_database_connection()
        self.validate_redis_connection()
        self.validate_external_services()
        self.validate_security_settings()

        self.print_results()
        return len(self.errors) == 0

    def validate_required_variables(self):
        """Check all required environment variables."""
        required_vars = [
            ("DATABASE_URL", "Database connection string"),
            ("REDIS_URL", "Redis connection string"),
            ("JWT_SECRET", "JWT signing secret"),
            ("STRIPE_SECRET_KEY", "Stripe API secret key"),
            ("STRIPE_WEBHOOK_SECRET", "Stripe webhook signing secret"),
        ]
        for var, description in required_vars:
            value = os.getenv(var)
            if not value:
                self.errors.append(f"Missing required variable {var}: {description}")
            elif len(value.strip()) < 8:
                self.warnings.append(f"Variable {var} seems too short (< 8 characters)")

    def validate_optional_variables(self):
        """Check optional but recommended variables."""
        optional_vars = [
            ("OPENAI_API_KEY", "OpenAI integration will not work"),
            ("ANTHROPIC_API_KEY", "Anthropic integration will not work"),
            ("SMTP_HOST", "Email functionality will not work"),
            ("SMTP_USER", "Email authentication will not work"),
            ("SMTP_PASSWORD", "Email authentication will not work"),
            ("SENTRY_DSN", "Error tracking will not work"),
        ]
        for var, consequence in optional_vars:
            if not os.getenv(var):
                self.warnings.append(f"Optional variable {var} not set: {consequence}")

    def validate_jwt_configuration(self):
        """Validate JWT configuration."""
        jwt_secret = os.getenv("JWT_SECRET", "")
        if jwt_secret:
            if len(jwt_secret) < 32:
                self.errors.append("JWT_SECRET must be at least 32 characters for security")
            elif jwt_secret in ["your-secret-key", "changeme", "secret"]:
                self.errors.append("JWT_SECRET appears to be a default/example value")
            else:
                self.info.append(f"JWT_SECRET length: {len(jwt_secret)} characters")
        jwt_algorithm = os.getenv("JWT_ALGORITHM", "HS256")
        if jwt_algorithm not in ["HS256", "HS384", "HS512"]:
            self.warnings.append(f"JWT_ALGORITHM '{jwt_algorithm}' may not be supported")

    def validate_database_connection(self):
        """Test database connectivity."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return  # Already caught
        try:
            parsed = urlparse(database_url)
            if parsed.scheme.split('+')[0] not in ["postgresql", "postgres"]:
                self.warnings.append(f"Database scheme '{parsed.scheme}' - expected postgresql")
            from sqlalchemy import create_engine, text
            engine = create_engine(database_url, pool_pre_ping=True)
            with engine.connect() as conn:
                version = conn.execute(text("SELECT version()"))
                self.info.append(f"Database connection successful: {version.scalar()}")
                # Check for common extensions used by this app
                has_pgcrypto = conn.execute(text(
                    "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto')"
                )).scalar()
                if not has_pgcrypto:
                    self.warnings.append("PostgreSQL 'pgcrypto' extension not found (needed for gen_random_uuid())")
        except ImportError:
            self.warnings.append("SQLAlchemy not available - cannot test database connection")
        except Exception as e:
            self.errors.append(f"Database connection failed: {str(e)}")

    def validate_redis_connection(self):
        """Test Redis connectivity."""
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            return
        try:
            import redis  # type: ignore
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            info = client.info()
            version = info.get("redis_version", "unknown")
            memory_mb = round(info.get("used_memory", 0) / (1024*1024), 2)
            self.info.append(f"Redis connection successful: v{version}, {memory_mb}MB used")
        except ImportError:
            self.warnings.append("Redis library not available - cannot test Redis connection")
        except Exception as e:
            self.errors.append(f"Redis connection failed: {str(e)}")

    def validate_external_services(self):
        """Test external service connectivity (best-effort)."""
        services = [
            {"name": "Stripe API", "test": self._test_stripe, "required": True},
            {"name": "OpenAI API", "test": self._test_openai, "required": False},
            {"name": "Anthropic API", "test": self._test_anthropic, "required": False},
        ]
        for svc in services:
            try:
                ok = svc["test"]()
                if ok:
                    self.info.append(f"{svc['name']} connectivity verified")
                else:
                    msg = f"{svc['name']} connectivity test failed"
                    (self.errors if svc["required"] else self.warnings).append(msg)
            except Exception as e:
                msg = f"{svc['name']} test error: {str(e)}"
                (self.errors if svc["required"] else self.warnings).append(msg)

    def _test_stripe(self) -> bool:
        key = os.getenv("STRIPE_SECRET_KEY")
        if not key:
            return False
        try:
            import stripe  # type: ignore
            stripe.api_key = key
            _ = stripe.Account.retrieve()
            return True
        except Exception:
            return False

    def _test_openai(self) -> bool:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return False
        try:
            # Use requests to avoid importing SDKs that may not be installed
            import requests  # type: ignore
            resp = requests.get(
                "https://api.openai.com/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def _test_anthropic(self) -> bool:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return False
        try:
            import requests  # type: ignore
            resp = requests.get(
                "https://api.anthropic.com/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def validate_security_settings(self):
        """Check basic security toggles and headers expectations."""
        debug = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
        if debug:
            self.warnings.append("DEBUG is enabled; disable in production")        
        # Basic URL checks (if behind TLS)
        public_url = os.getenv("PUBLIC_BASE_URL")
        if public_url and public_url.startswith("http://"):
            self.warnings.append("PUBLIC_BASE_URL should use HTTPS in production")

    def print_results(self):
        print("\n===== Environment Validation Report =====\n")
        if self.info:
            print("Info:")
            for msg in self.info:
                print(f"  - {msg}")
            print("")
        if self.warnings:
            print("Warnings:")
            for msg in self.warnings:
                print(f"  - {msg}")
            print("")
        if self.errors:
            print("Errors:")
            for msg in self.errors:
                print(f"  - {msg}")
            print("")
        overall = "PASS" if not self.errors else "FAIL"
        print(f"Overall: {overall}")
        print("")


def main() -> int:
    validator = EnvironmentValidator()
    ok = validator.validate_all()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
