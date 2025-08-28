from fastapi import HTTPException, status
from typing import Any, Dict, Optional
import logging

logger = logging.getLogger(__name__)

class SaaSException(Exception):
    """Base exception for SaaS Sheets application."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)

        # Log the exception for monitoring
        logger.error(f"{self.__class__.__name__}: {message}", extra={"details": self.details})

class InsufficientCreditsError(SaaSException):
    """Raised when user has insufficient credits for operation."""

    def __init__(self, required: int, available: int, user_id: str = None):
        message = f"Insufficient credits. Required: {required}, Available: {available}"
        details = {
            "required_credits": required,
            "available_credits": available,
            "user_id": user_id
        }
        super().__init__(message, details)

class LLMProviderError(SaaSException):
    """Raised when LLM provider fails."""

    def __init__(self, provider: str, error_message: str, status_code: int = None):
        message = f"LLM provider '{provider}' failed: {error_message}"
        details = {
            "provider": provider,
            "original_error": error_message,
            "status_code": status_code
        }
        super().__init__(message, details)

class AuthenticationError(SaaSException):
    """Raised when authentication fails."""

    def __init__(self, reason: str = "Authentication failed"):
        super().__init__(reason, {"auth_failure_reason": reason})

class TokenExpiredError(AuthenticationError):
    """Raised when JWT token has expired."""

    def __init__(self):
        super().__init__("Authentication token has expired")

class InvalidTokenError(AuthenticationError):
    """Raised when JWT token is invalid."""

    def __init__(self, reason: str = "Invalid token"):
        super().__init__(f"Invalid authentication token: {reason}")

class RateLimitExceeded(SaaSException):
    """Raised when rate limit is exceeded."""

    def __init__(self, limit: int, window: str, client_id: str = None):
        message = f"Rate limit exceeded: {limit} requests per {window}"
        details = {
            "limit": limit,
            "window": window,
            "client_id": client_id
        }
        super().__init__(message, details)

class WebhookValidationError(SaaSException):
    """Raised when webhook signature validation fails."""

    def __init__(self, provider: str, reason: str = "Invalid signature"):
        message = f"Webhook validation failed for {provider}: {reason}"
        details = {"provider": provider, "validation_error": reason}
        super().__init__(message, details)

class DatabaseError(SaaSException):
    """Raised when database operations fail."""

    def __init__(self, operation: str, error: str):
        message = f"Database operation '{operation}' failed: {error}"
        details = {"operation": operation, "database_error": error}
        super().__init__(message, details)

class ConfigurationError(SaaSException):
    """Raised when application configuration is invalid."""

    def __init__(self, setting: str, reason: str):
        message = f"Configuration error for '{setting}': {reason}"
        details = {"setting": setting, "reason": reason}
        super().__init__(message, details)

class ExternalServiceError(SaaSException):
    """Raised when external service calls fail."""

    def __init__(self, service: str, error: str, status_code: int = None):
        message = f"External service '{service}' error: {error}"
        details = {
            "service": service,
            "error": error,
            "status_code": status_code
        }
        super().__init__(message, details)

# Exception to HTTP status code mapping
def to_http_exception(exc: SaaSException) -> HTTPException:
    """Convert SaaS exception to HTTP exception with appropriate status code."""

    # Determine status code based on exception type
    status_code_mapping = {
        InsufficientCreditsError: status.HTTP_402_PAYMENT_REQUIRED,
        AuthenticationError: status.HTTP_401_UNAUTHORIZED,
        TokenExpiredError: status.HTTP_401_UNAUTHORIZED,
        InvalidTokenError: status.HTTP_401_UNAUTHORIZED,
        RateLimitExceeded: status.HTTP_429_TOO_MANY_REQUESTS,
        WebhookValidationError: status.HTTP_400_BAD_REQUEST,
        DatabaseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ConfigurationError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ExternalServiceError: status.HTTP_502_BAD_GATEWAY,
    }

    status_code = status_code_mapping.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

    return HTTPException(
        status_code=status_code,
        detail={
            "error": exc.__class__.__name__,
            "message": exc.message,
            **exc.details
        }
    )

# Global exception handler decorator (sync)
def handle_saas_exceptions(func):
    """Decorator to automatically convert SaaS exceptions to HTTP exceptions."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except SaaSException as e:
            raise to_http_exception(e)
        except Exception as e:
            # Log unexpected exceptions
            logger.exception(f"Unexpected error in {func.__name__}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={
                    "error": "InternalServerError",
                    "message": "An unexpected error occurred"
                }
            )
    return wrapper
