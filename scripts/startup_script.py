#!/usr/bin/env python3
"""
Production startup script with comprehensive configuration validation.
Fails fast if any critical configuration is missing or invalid.
"""
import sys
import os
import logging
import asyncio
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def setup_logging():
    """Setup basic logging for startup validation."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    return logging.getLogger(__name__)

async def validate_configuration():
    """Comprehensive configuration validation before startup."""
    logger = setup_logging()
    
    logger.info("Starting SaaS Sheets AI configuration validation...")
    
    try:
        # Import and validate configuration
        from app.config import settings, validate_runtime_config, is_production
        
        logger.info(f"Environment: {settings.environment}")
        logger.info(f"Debug mode: {settings.debug}")
        logger.info(f"API version: {settings.api_version}")
        
        # Run runtime configuration checks
        if not await run_runtime_validation():
            logger.error("Runtime configuration validation failed")
            return False
        
        # Production-specific checks
        if is_production():
            if not await validate_production_readiness():
                logger.error("Production readiness validation failed")
                return False
        
        logger.info("Configuration validation completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        logger.error("Please check your environment variables and .env file")
        return False

async def run_runtime_validation():
    """Run runtime validation checks."""
    logger = logging.getLogger(__name__)
    
    checks = []
    
    # Database connection check
    async def check_database():
        try:
            from sqlalchemy import create_engine, text
            from app.config import get_database_url
            
            engine = create_engine(get_database_url(), pool_pre_ping=True)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("Database connection validated")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False
    
    # Redis connection check
    async def check_redis():
        try:
            import redis
            from app.config import get_redis_url
            
            redis_client = redis.from_url(get_redis_url())
            redis_client.ping()
            logger.info("Redis connection validated")
            return True
        except Exception as e:
            logger.error(f"Redis connection failed: {e}")
            return False
    
    # LLM provider validation
    async def check_llm_providers():
        try:
            from app.config import settings
            
            valid_providers = []
            
            if settings.openai_api_key:
                if settings.openai_api_key.startswith("sk-"):
                    valid_providers.append("openai")
                    logger.info("OpenAI API key format validated")
                else:
                    logger.error("Invalid OpenAI API key format")
                    return False
            
            if settings.anthropic_api_key:
                if settings.anthropic_api_key.startswith("sk-ant-"):
                    valid_providers.append("anthropic")
                    logger.info("Anthropic API key format validated")
                else:
                    logger.error("Invalid Anthropic API key format")
                    return False
            
            if not valid_providers:
                logger.error("No valid LLM providers configured")
                return False
            
            logger.info(f"LLM providers validated: {', '.join(valid_providers)}")
            return True
            
        except Exception as e:
            logger.error(f"LLM provider validation failed: {e}")
            return False
    
    # Run all checks concurrently
    try:
        results = await asyncio.gather(
            check_database(),
            check_redis(),
            check_llm_providers(),
            return_exceptions=True
        )
        
        # Check if any validation failed
        failed_checks = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                failed_checks.append(f"Check {i}: {result}")
            elif not result:
                failed_checks.append(f"Check {i}: Failed")
        
        if failed_checks:
            logger.error(f"Failed validation checks: {failed_checks}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Runtime validation error: {e}")
        return False

async def validate_production_readiness():
    """Additional validation for production environment."""
    logger = logging.getLogger(__name__)
    from app.config import settings
    
    logger.info("Running production readiness checks...")
    
    # Check that all production secrets are configured
    required_production_configs = [
        ("Database URL", settings.database_url),
        ("Redis URL", settings.redis_url),
        ("JWT Secret", settings.jwt_secret),
        ("Stripe Secret Key", settings.stripe_secret_key),
        ("Stripe Webhook Secret", settings.stripe_webhook_secret),
    ]
    
    missing_configs = []
    for name, value in required_production_configs:
        if not value or str(value).strip() == "":
            missing_configs.append(name)
    
    if missing_configs:
        logger.error(f"Missing production configurations: {', '.join(missing_configs)}")
        return False
    
    # Validate Stripe keys are live keys (not test)
    if settings.stripe_secret_key.startswith("sk_test_"):
        logger.error("Using Stripe test keys in production environment")
        return False
    
    # Check HTTPS URLs
    if not str(settings.frontend_url).startswith("https://"):
        logger.error("Frontend URL must use HTTPS in production")
        return False
    
    if not str(settings.api_base_url).startswith("https://"):
        logger.error("API base URL must use HTTPS in production")
        return False
    
    # Validate JWT secret strength
    if len(settings.jwt_secret) < 32:
        logger.error("JWT secret too short for production (minimum 32 characters)")
        return False
    
    logger.info("Production readiness validation passed")
    return True

def print_startup_banner():
    """Print application startup banner."""
    from app.config import settings
    
    banner = f"""
╔══════════════════════════════════════════════════════════════╗
║                    SaaS Sheets AI Server                     ║
║                                                              ║
║  Environment: {settings.environment:>47} ║
║  Version:     {settings.api_version:>47} ║
║  Debug:       {str(settings.debug):>47} ║
╚══════════════════════════════════════════════════════════════╝

Starting server on {settings.host}:{settings.port}
"""
    print(banner)

async def main():
    """Main startup function."""
    # Validate configuration first
    if not await validate_configuration():
        print("\nConfiguration validation failed. Server startup aborted.")
        print("\nPlease check:")
        print("1. Environment variables are set correctly")
        print("2. Database and Redis are accessible")
        print("3. API keys are valid and properly formatted")
        print("4. .env file matches .env.example template")
        sys.exit(1)
    
    # Print startup banner
    print_startup_banner()
    
    # Import and start the FastAPI application
    try:
        import uvicorn
        from app.main import app
        from app.config import settings
        
        # Start server
        config = uvicorn.Config(
            app=app,
            host=settings.host,
            port=settings.port,
            workers=settings.workers if settings.workers > 1 else None,
            log_level=settings.log_level.lower(),
            access_log=not settings.environment == "production",
            reload=settings.debug,
        )
        
        server = uvicorn.Server(config)
        await server.serve()
        
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Server startup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
        sys.exit(0)
    except Exception as e:
        print(f"Startup failed: {e}")
        sys.exit(1)