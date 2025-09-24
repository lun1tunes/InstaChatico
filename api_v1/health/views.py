"""
Health check API views - system monitoring endpoints.
Clean route handlers for health checks and system statistics.
"""

import time
from datetime import datetime
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.simple_dependencies import (
    get_db_session,
    get_classification_service,
    get_health_checker
)
from core.logging_config import get_logger

from .schemas import (
    HealthCheckResponse,
    ServiceHealthResponse,
    SystemHealthResponse,
    ServiceStatsResponse,
    DatabaseHealthDetails,
    ClassificationServiceHealthDetails
)

logger = get_logger(__name__, "health_views")
router = APIRouter(tags=["Health"])


@router.get("/health", response_model=SystemHealthResponse)
async def system_health(health_checker = Depends(get_health_checker)):
    """
    Overall system health check.
    
    Checks all critical services and returns overall health status.
    """
    try:
        health_status = await health_checker.get_overall_health()
        
        return SystemHealthResponse(
            healthy=health_status["healthy"],
            timestamp=datetime.utcnow(),
            services=health_status["services"],
            details=health_status.get("details")
        )
        
    except Exception as e:
        logger.error(
            "System health check failed",
            extra_fields={"error": str(e)},
            operation="system_health"
        )
        
        return SystemHealthResponse(
            healthy=False,
            timestamp=datetime.utcnow(),
            services={"error": False},
            details={"error": str(e)}
        )


@router.get("/health/database", response_model=ServiceHealthResponse)
async def database_health(
    session: AsyncSession = Depends(get_db_session),
    health_checker = Depends(get_health_checker)
):
    """
    Database-specific health check.
    
    Tests database connectivity and basic operations.
    """
    start_time = time.time()
    
    try:
        # Test database connectivity
        healthy = await health_checker.check_database()
        response_time_ms = int((time.time() - start_time) * 1000)
        
        details = DatabaseHealthDetails(
            query_response_time_ms=response_time_ms
        )
        
        return ServiceHealthResponse(
            healthy=healthy,
            service="database",
            timestamp=datetime.utcnow(),
            response_time_ms=response_time_ms,
            details=details.model_dump()
        )
        
    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        
        logger.error(
            "Database health check failed",
            extra_fields={"error": str(e), "response_time_ms": response_time_ms},
            operation="database_health"
        )
        
        return ServiceHealthResponse(
            healthy=False,
            service="database",
            timestamp=datetime.utcnow(),
            response_time_ms=response_time_ms,
            error=str(e)
        )


@router.get("/health/classification", response_model=ServiceHealthResponse)
async def classification_health(
    classification_service = Depends(get_classification_service)
):
    """
    Classification service health check.
    
    Tests AI classification service connectivity and performance.
    """
    start_time = time.time()
    
    try:
        # Get service health status
        health_status = await classification_service.health_check()
        response_time_ms = int((time.time() - start_time) * 1000)
        
        # Get service statistics
        stats = classification_service.stats
        
        details = ClassificationServiceHealthDetails(
            api_accessible=health_status.get("healthy", False),
            model=health_status.get("details", {}).get("model"),
            cache_size=health_status.get("details", {}).get("cache_size"),
            request_count=stats.get("requests"),
            error_rate=stats.get("error_rate")
        )
        
        return ServiceHealthResponse(
            healthy=health_status["healthy"],
            service="classification",
            timestamp=datetime.utcnow(),
            response_time_ms=response_time_ms,
            details=details.model_dump()
        )
        
    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        
        logger.error(
            "Classification service health check failed",
            extra_fields={"error": str(e), "response_time_ms": response_time_ms},
            operation="classification_health"
        )
        
        return ServiceHealthResponse(
            healthy=False,
            service="classification",
            timestamp=datetime.utcnow(),
            response_time_ms=response_time_ms,
            error=str(e)
        )


@router.get("/stats", response_model=ServiceStatsResponse)
async def service_stats(
    classification_service = Depends(get_classification_service)
):
    """
    Get comprehensive service statistics.
    
    Returns performance metrics and usage statistics for all services.
    """
    try:
        # Get classification service stats
        classification_stats = classification_service.stats
        
        # Compile all service statistics
        all_stats = {
            "classification": classification_stats,
            "system": {
                "timestamp": datetime.utcnow().isoformat(),
                "uptime_check": "healthy"
            }
        }
        
        return ServiceStatsResponse(
            service="system",
            timestamp=datetime.utcnow(),
            stats=all_stats
        )
        
    except Exception as e:
        logger.error(
            "Failed to get service statistics",
            extra_fields={"error": str(e)},
            operation="service_stats"
        )
        
        return ServiceStatsResponse(
            service="system",
            timestamp=datetime.utcnow(),
            stats={"error": str(e)}
        )


@router.get("/ping", response_model=HealthCheckResponse)
async def ping():
    """
    Simple ping endpoint for basic availability checks.
    
    Returns immediate response for load balancer health checks.
    """
    return HealthCheckResponse(
        healthy=True,
        service="api",
        timestamp=datetime.utcnow(),
        details={"message": "pong"}
    )
