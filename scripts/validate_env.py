#!/usr/bin/env python3
"""
Validate environment configuration before deployment.
Checks for required variables, database connectivity, and external services.
"""
import os
import sys
import requests
import logging
from typing import List, Dict, Any

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class EnvironmentValidator:
    """Validates environment configuration for production deployment."""
    
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.info = []
    
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
    
    def validate_database_connection(self):
        """Test database connectivity."""
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            return
        
        try:
            from sqlalchemy import create_engine, text
            engine = create_engine(database_url, pool_pre_ping=True)
            
            with engine.connect() as conn:
                result = conn.execute(text("SELECT version()"))
                version = result.scalar()
                self.info.append(f"Database connection successful: {version}")
                
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
            import redis
            redis_client = redis.from_url(redis_url)
            redis_client.ping()
            
            info = redis_client.info()
            version = info.get("redis_version", "unknown")
            self.info.append(f"Redis connection successful: v{version}")
            
        except ImportError:
            self.warnings.append("Redis library not available - cannot test Redis connection")
        except Exception as e:
            self.errors.append(f"Redis connection failed: {str(e)}")
    
    def validate_external_services(self):
        """Test external service connectivity."""
        # Test Stripe
        if self._test_stripe():
            self.info.append("Stripe API connectivity verified")
        else:
            self.errors.append("Stripe API connectivity test failed")
        
        # Test OpenAI (optional)
        if os.getenv("OPENAI_API_KEY"):
            if self._test_openai():
                self.info.append("OpenAI API connectivity verified")
            else:
                self.warnings.append("OpenAI API connectivity test failed")
    
    def _test_stripe(self) -> bool:
        """Test Stripe API connectivity."""
        stripe_key = os.getenv("STRIPE_SECRET_KEY")
        if not stripe_key:
            return False
        
        try:
            import stripe
            stripe.api_key = stripe_key
            stripe.Account.retrieve()
            return True
        except Exception:
            return False
    
    def _test_openai(self) -> bool:
        """Test OpenAI API connectivity."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return False
        
        try:
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(
                "https://api.openai.com/v1/models",
                headers=headers,
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False
    
    def validate_security_settings(self):
        """Validate security-related configuration."""
        debug = os.getenv("DEBUG", "false").lower()
        if debug in ["true", "1", "yes"]:
            self.warnings.append("DEBUG mode is enabled - should be false in production")
        
        # Check for default/weak secrets
        jwt_secret = os.getenv("JWT_SECRET", "")
        if any(weak in jwt_secret.lower() for weak in ["secret", "changeme", "your-secret-key"]):
            self.errors.append("JWT_SECRET contains weak/default value")
    
    def print_results(self):
        """Print validation results."""
        print("\n" + "="*60)
        print("ENVIRONMENT VALIDATION RESULTS")
        print("="*60)
        
        if self.info:
            print(f"\n✅ Information ({len(self.info)}):")
            for item in self.info:
                print(f"   • {item}")
        
        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                print(f"   • {warning}")
        
        if self.errors:
            print(f"\n❌ Errors ({len(self.errors)}):")
            for error in self.errors:
                print(f"   • {error}")
        else:
            print("\n✅ No errors found!")
        
        print("\n" + "="*60)
        
        if self.errors:
            print("❌ VALIDATION FAILED - Fix errors before deploying")
        elif self.warnings:
            print("⚠️  VALIDATION PASSED WITH WARNINGS")
        else:
            print("✅ VALIDATION PASSED - Ready for deployment!")
        
        print("="*60)

def main():
    """Main validation function."""
    validator = EnvironmentValidator()
    success = validator.validate_all()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
