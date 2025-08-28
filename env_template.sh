# SaaS Sheets AI - Environment Configuration Template
# Copy this file to .env and fill in your actual values

# =============================================================================
# APPLICATION SETTINGS
# =============================================================================
ENVIRONMENT=development
DEBUG=true
API_TITLE="SaaS Sheets AI"
API_VERSION="1.0.0"

# Server Configuration  
HOST=0.0.0.0
PORT=8000
WORKERS=1

# =============================================================================
# DATABASE CONFIGURATION (Required)
# =============================================================================
# PostgreSQL connection string
# Format: postgresql://username:password@host:port/database
DATABASE_URL=postgresql://saas_user:your_password@localhost:5432/saas_sheets_dev

# Redis connection string  
# Format: redis://host:port/db or redis://username:password@host:port/db
REDIS_URL=redis://localhost:6379/0

# =============================================================================
# SECURITY CONFIGURATION (Required)
# =============================================================================
# JWT secret for token signing (MUST be 32+ characters)
# Generate with: openssl rand -base64 32
JWT_SECRET=your-super-secure-jwt-secret-key-32-plus-characters-required

# JWT Configuration
JWT_ALGORITHM=HS256
JWT_EXPIRATION_HOURS=24

# =============================================================================
# STRIPE PAYMENT INTEGRATION (Required)
# =============================================================================
# Stripe API Keys (get from https://dashboard.stripe.com/apikeys)
STRIPE_SECRET_KEY=sk_test_your_stripe_secret_key
STRIPE_PUBLISHABLE_KEY=pk_test_your_stripe_publishable_key

# Stripe Webhook Secret (get from webhook endpoint configuration)
STRIPE_WEBHOOK_SECRET=whsec_your_webhook_signing_secret

# =============================================================================
# LLM PROVIDERS (At least one required)
# =============================================================================
# OpenAI API Key (get from https://platform.openai.com/api-keys)
OPENAI_API_KEY=sk-your-openai-api-key

# Anthropic API Key (get from https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-your-anthropic-api-key

# Default LLM provider to use
DEFAULT_LLM_PROVIDER=openai

# =============================================================================
# EMAIL CONFIGURATION (Optional but recommended)
# =============================================================================
# SMTP settings for magic link authentication
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_USE_TLS=true
FROM_EMAIL=noreply@yourapp.com

# =============================================================================
# FRONTEND & API URLs
# =============================================================================
# Frontend URL (where users access the application)
FRONTEND_URL=https://sheets.google.com

# API base URL (for webhook callbacks and API documentation)
API_BASE_URL=https://api.yourapp.com

# =============================================================================
# RATE LIMITING
# =============================================================================
# API rate limiting configuration
RATE_LIMIT_CALLS_PER_MINUTE=100
RATE_LIMIT_BURST=20

# =============================================================================
# CREDITS SYSTEM
# =============================================================================
# Number of free credits for new users
FREE_TRIAL_CREDITS=10

# Maximum credits a user can hold
MAX_CREDITS_PER_USER=100000

# =============================================================================
# CORS CONFIGURATION
# =============================================================================
# Allowed origins for CORS (comma-separated)
CORS_ORIGINS=https://script.google.com,https://sheets.google.com

# =============================================================================
# LOGGING & MONITORING
# =============================================================================
# Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# Log format: json (production) or text (development)
LOG_FORMAT=text

# Sentry DSN for error tracking (optional)
# SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# Prometheus metrics directory (optional)
# PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus_multiproc_dir

# =============================================================================
# DEVELOPMENT SETTINGS
# =============================================================================
# These settings are only used in development/testing

# Test database (separate from main database)
TEST_DATABASE_URL=postgresql://saas_user:your_password@localhost:5432/saas_sheets_test

# Development-specific overrides
DEV_SKIP_EMAIL_VERIFICATION=true
DEV_ALLOW_HTTP_URLS=true