from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any
import time
import psutil
import logging
from datetime import datetime, timedelta

from app.db import get_db, get_redis
from app.config import settings
from app.models import User, CreditTransaction, UsageEvent
from app.services.credits import get_balance as get_user_credits  # import present function

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health")
async def basic_health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@router.get("/readyz")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Comprehensive readiness check for Kubernetes/container orchestration.
    Returns 200 if all critical dependencies are available.
    """
    checks: Dict[str, Any] = {}
    all_healthy = True

    # Database connectivity
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy", "latency_ms": None}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # Redis connectivity
    try:
        redis_client = get_redis()
        start_time = time.time()
        redis_client.ping()
        latency = int((time.time() - start_time) * 1000)
        checks["redis"] = {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False

    # External services (if critical for operation)
    if getattr(settings, "openai_api_key", None):
        try:
            import openai  # type: ignore
            client = openai.OpenAI(api_key=settings.openai_api_key)
            _ = client.models.list()
            checks["openai"] = {"status": "healthy"}
        except Exception as e:
            checks["openai"] = {"status": "degraded", "error": str(e)}
            # Not critical for readiness

    status_code = 200 if all_healthy else 503
    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }, status_code

@router.get("/livez")
async def liveness_check():
    """
    Liveness check for Kubernetes.
    Should only fail if the application is in an unrecoverable state.
    """
    try:
        # Import presence check for critical modules
        from app.models import User  # noqa: F401
        from app.services.credits import get_balance  # noqa: F401

        # Check system resources
        memory = psutil.virtual_memory()
        if memory.percent > 95:  # Critical memory usage
            raise Exception(f"Critical memory usage: {memory.percent}%")

        return {
            "status": "alive",
            "memory_percent": memory.percent,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.critical(f"Liveness check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Application not alive: {str(e)}")

@router.get("/metrics")
async def prometheus_metrics(db: Session = Depends(get_db)):
    """
    Prometheus-style metrics endpoint.
    Returns metrics in a format that Prometheus can scrape.
    """
    try:
        total_users = db.query(User).count()
        active_users_24h = db.query(User).join(UsageEvent).filter(
            UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).distinct().count()

        total_api_calls_24h = db.query(UsageEvent).filter(
            UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).count()

        successful_calls_24h = db.query(UsageEvent).filter(
            UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24),
            UsageEvent.success == True  # noqa: E712
        ).count()

        # System metrics
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent()

        metrics = f"""# HELP saas_sheets_users_total Total number of registered users
# TYPE saas_sheets_users_total counter
saas_sheets_users_total {total_users}

# HELP saas_sheets_active_users_24h Number of active users in last 24 hours
# TYPE saas_sheets_active_users_24h gauge
saas_sheets_active_users_24h {active_users_24h}

# HELP saas_sheets_api_calls_total Total API calls in last 24 hours
# TYPE saas_sheets_api_calls_total counter
saas_sheets_api_calls_total {total_api_calls_24h}

# HELP saas_sheets_api_calls_success Successful API calls in last 24 hours
# TYPE saas_sheets_api_calls_success counter
saas_sheets_api_calls_success {successful_calls_24h}

# HELP saas_sheets_memory_usage_percent Memory usage percentage
# TYPE saas_sheets_memory_usage_percent gauge
saas_sheets_memory_usage_percent {memory.percent}

# HELP saas_sheets_cpu_usage_percent CPU usage percentage
# TYPE saas_sheets_cpu_usage_percent gauge
saas_sheets_cpu_usage_percent {cpu_percent}
"""
        return Response(content=metrics, media_type="text/plain")

    except Exception as e:
        logger.error(f"Failed to generate metrics: {e}")
        raise HTTPException(status_code=500, detail="Metrics generation failed")

@router.get("/debug")
async def debug_info(db: Session = Depends(get_db)):
    """
    Debug information endpoint (only available in debug mode).
    """
    if not settings.debug:
        raise HTTPException(status_code=404, detail="Debug endpoint not available")

    try:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        recent_errors = db.query(UsageEvent).filter(
            UsageEvent.success == False,  # noqa: E712
            UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=1)
        ).count()

        return {
            "system": {
                "memory": {
                    "total_gb": round(memory.total / (1024**3), 2),
                    "available_gb": round(memory.available / (1024**3), 2),
                    "percent_used": memory.percent
                },
                "disk": {
                    "total_gb": round(disk.total / (1024**3), 2),
                    "free_gb": round(disk.free / (1024**3), 2),
                    "percent_used": round((disk.used / disk.total) * 100, 2)
                },
                "cpu_count": psutil.cpu_count(),
                "load_average": psutil.getloadavg() if hasattr(psutil, 'getloadavg') else None
            },
            "application": {
                "debug_mode": settings.debug,
                "database_url": settings.database_url.split('@')[0] + '@***',
                "redis_url": settings.redis_url,
                "recent_errors_1h": recent_errors
            },
            "timestamp": datetime.utcnow().isoformat()
        }

    except Exception as e:
        logger.error(f"Failed to generate debug info: {e}")
        raise HTTPException(status_code=500, detail="Debug info generation failed")
