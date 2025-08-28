from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any
import time
import psutil
import logging
from datetime import datetime, timedelta
from urllib.parse import urlparse

from app.db import get_db, get_redis
from app.config import settings
from app.models import User, CreditTransaction, UsageEvent, StripeEventLog

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/health")
async def basic_health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

@router.get("/healthz")
async def health_alias():
    """Health check alias for platforms that expect /healthz."""
    return await basic_health_check()

@router.get("/readyz")
async def readiness_check(db: Session = Depends(get_db)):
    """
    Comprehensive readiness check for Kubernetes/container orchestration.
    Returns 200 if all critical dependencies are available.
    """
    checks = {}
    all_healthy = True
    
    # Database connectivity with latency measurement
    try:
        start_time = time.time()
        db.execute(text("SELECT 1"))
        latency_ms = int((time.time() - start_time) * 1000)
        checks["database"] = {"status": "healthy", "latency_ms": latency_ms}
        
        # Check for required extensions
        result = db.execute(text("SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'uuid-ossp')"))
        if not result.scalar():
            checks["database"]["warning"] = "uuid-ossp extension missing"
            
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False
    
    # Redis connectivity with latency measurement
    try:
        redis_client = get_redis()
        start_time = time.time()
        redis_client.ping()
        latency_ms = int((time.time() - start_time) * 1000)
        checks["redis"] = {"status": "healthy", "latency_ms": latency_ms}
        
        # Check memory usage
        info = redis_client.info("memory")
        used_memory_mb = round(info.get("used_memory", 0) / (1024 * 1024), 2)
        checks["redis"]["memory_mb"] = used_memory_mb
        
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
        all_healthy = False
    
    # External services health check (non-critical)
    if hasattr(settings, 'openai_api_key') and settings.openai_api_key:
        try:
            # Quick validation without actual API call
            checks["openai"] = {"status": "configured"}
        except Exception as e:
            checks["openai"] = {"status": "degraded", "error": str(e)}
    
    status_code = 200 if all_healthy else 503
    response_data = {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if not all_healthy:
        raise HTTPException(status_code=status_code, detail=response_data)
    
    return response_data

@router.get("/livez")
async def liveness_check():
    """
    Liveness check for Kubernetes.
    Should only fail if the application is in an unrecoverable state.
    """
    try:
        # Check system resources
        memory = psutil.virtual_memory()
        if memory.percent > 95:  # Critical memory usage
            raise Exception(f"Critical memory usage: {memory.percent}%")
        
        # Check disk space
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        if disk_percent > 95:
            raise Exception(f"Critical disk usage: {disk_percent:.1f}%")
        
        return {
            "status": "alive",
            "memory_percent": memory.percent,
            "disk_percent": round(disk_percent, 1),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.critical(f"Liveness check failed: {e}")
        raise HTTPException(status_code=503, detail=f"Application not alive: {str(e)}")

@router.get("/metrics")
async def prometheus_metrics(db: Session = Depends(get_db)):
    """
    Prometheus-style metrics endpoint with Stripe event tracking.
    Returns metrics in a format that Prometheus can scrape.
    """
    try:
        # Application metrics
        total_users = db.query(User).count()
        
        # Usage metrics (with fallback if tables don't exist)
        try:
            active_users_24h = db.query(User).join(UsageEvent).filter(
                UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).distinct().count()
            
            total_api_calls_24h = db.query(UsageEvent).filter(
                UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24)
            ).count()
            
            successful_calls_24h = db.query(UsageEvent).filter(
                UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24),
                UsageEvent.success == True
            ).count()
            
            # API call latency buckets (basic histogram)
            fast_calls = db.query(UsageEvent).filter(
                UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24),
                UsageEvent.execution_time_ms <= 1000
            ).count()
            
            medium_calls = db.query(UsageEvent).filter(
                UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24),
                UsageEvent.execution_time_ms > 1000,
                UsageEvent.execution_time_ms <= 5000
            ).count()
            
            slow_calls = db.query(UsageEvent).filter(
                UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=24),
                UsageEvent.execution_time_ms > 5000
            ).count()
            
        except Exception:
            # If UsageEvent table doesn't exist yet, use defaults
            active_users_24h = 0
            total_api_calls_24h = 0
            successful_calls_24h = 0
            fast_calls = medium_calls = slow_calls = 0
        
        # Stripe webhook metrics
        try:
            stripe_events_processed_24h = db.query(StripeEventLog).filter(
                StripeEventLog.created_at >= datetime.utcnow() - timedelta(hours=24),
                StripeEventLog.processed == True
            ).count()
            
            stripe_events_failed_24h = db.query(StripeEventLog).filter(
                StripeEventLog.created_at >= datetime.utcnow() - timedelta(hours=24),
                StripeEventLog.processed == False,
                StripeEventLog.processing_attempts >= 5
            ).count()
            
            stripe_events_pending = db.query(StripeEventLog).filter(
                StripeEventLog.processed == False,
                StripeEventLog.processing_attempts < 5
            ).count()
            
        except Exception:
            # If StripeEventLog table doesn't exist yet
            stripe_events_processed_24h = 0
            stripe_events_failed_24h = 0
            stripe_events_pending = 0
        
        # System metrics
        memory = psutil.virtual_memory()
        cpu_percent = psutil.cpu_percent()
        disk = psutil.disk_usage('/')
        disk_percent = (disk.used / disk.total) * 100
        
        # Format as Prometheus metrics
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

# HELP saas_sheets_api_latency_bucket API call latency buckets in last 24h
# TYPE saas_sheets_api_latency_bucket counter
saas_sheets_api_latency_bucket{{le="1000"}} {fast_calls}
saas_sheets_api_latency_bucket{{le="5000"}} {medium_calls}
saas_sheets_api_latency_bucket{{le="+Inf"}} {slow_calls}

# HELP saas_sheets_stripe_events_processed Stripe events processed successfully in last 24h
# TYPE saas_sheets_stripe_events_processed counter
saas_sheets_stripe_events_processed {stripe_events_processed_24h}

# HELP saas_sheets_stripe_events_failed Stripe events failed (dead letter) in last 24h
# TYPE saas_sheets_stripe_events_failed counter
saas_sheets_stripe_events_failed {stripe_events_failed_24h}

# HELP saas_sheets_stripe_events_pending Stripe events pending retry
# TYPE saas_sheets_stripe_events_pending gauge
saas_sheets_stripe_events_pending {stripe_events_pending}

# HELP saas_sheets_memory_usage_percent Memory usage percentage
# TYPE saas_sheets_memory_usage_percent gauge
saas_sheets_memory_usage_percent {memory.percent}

# HELP saas_sheets_cpu_usage_percent CPU usage percentage
# TYPE saas_sheets_cpu_usage_percent gauge
saas_sheets_cpu_usage_percent {cpu_percent}

# HELP saas_sheets_disk_usage_percent Disk usage percentage
# TYPE saas_sheets_disk_usage_percent gauge
saas_sheets_disk_usage_percent {disk_percent:.1f}
"""
        
        return Response(content=metrics, media_type="text/plain")
        
    except Exception as e:
        logger.error(f"Failed to generate metrics: {e}")
        raise HTTPException(status_code=500, detail="Metrics generation failed")

@router.get("/debug")
async def debug_info(db: Session = Depends(get_db)):
    """
    Debug information endpoint (only available in debug mode).
    Security hardened to prevent information disclosure.
    """
    if not getattr(settings, 'debug', False):
        raise HTTPException(status_code=404, detail="Debug endpoint not available")
    
    try:
        # System information
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Application statistics
        try:
            recent_errors = db.query(UsageEvent).filter(
                UsageEvent.success == False,
                UsageEvent.created_at >= datetime.utcnow() - timedelta(hours=1)
            ).count()
            
            recent_stripe_failures = db.query(StripeEventLog).filter(
                StripeEventLog.processed == False,
                StripeEventLog.created_at >= datetime.utcnow() - timedelta(hours=1)
            ).count()
        except Exception:
            recent_errors = 0
            recent_stripe_failures = 0
        
        # Database URL parsing for safe exposure
        db_driver = "unknown"
        if hasattr(settings, 'database_url'):
            try:
                parsed = urlparse(str(settings.database_url))
                db_driver = parsed.scheme  # Only expose the driver, not credentials
            except Exception:
                pass
        
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
                "debug_mode": True,  # Only exposed when debug is true anyway
                "database_driver": db_driver,  # Safe to expose driver type
                "recent_errors_1h": recent_errors,
                "recent_stripe_failures_1h": recent_stripe_failures
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Failed to generate debug info: {e}")
        raise HTTPException(status_code=500, detail="Debug info generation failed")
