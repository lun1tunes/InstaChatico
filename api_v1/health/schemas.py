"""
Pydantic v2 schemas for health check API endpoints.
"""

from typing import Dict, Any
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class HealthCheckResponse(BaseModel):
    """Response for health check endpoints"""
    model_config = ConfigDict()
    
    healthy: bool = Field(description="Overall health status")
    service: str = Field(description="Service name")
    timestamp: datetime = Field(description="Health check timestamp")
    details: Dict[str, Any] | None = Field(
        default=None,
        description="Additional health details"
    )


class ServiceHealthResponse(BaseModel):
    """Response for individual service health checks"""
    model_config = ConfigDict()
    
    healthy: bool = Field(description="Service health status")
    service: str = Field(description="Service name")
    timestamp: datetime = Field(description="Check timestamp")
    response_time_ms: int | None = Field(
        default=None,
        ge=0,
        description="Response time in milliseconds"
    )
    error: str | None = Field(default=None, description="Error message if unhealthy")
    details: Dict[str, Any] | None = Field(
        default=None,
        description="Service-specific details"
    )


class SystemHealthResponse(BaseModel):
    """Response for overall system health"""
    model_config = ConfigDict()
    
    healthy: bool = Field(description="Overall system health")
    timestamp: datetime = Field(description="Health check timestamp")
    services: Dict[str, bool] = Field(description="Health status of each service")
    details: Dict[str, Any] | None = Field(
        default=None,
        description="Detailed service information"
    )


class ServiceStatsResponse(BaseModel):
    """Response for service statistics"""
    model_config = ConfigDict()
    
    service: str = Field(description="Service name")
    timestamp: datetime = Field(description="Statistics timestamp")
    stats: Dict[str, Any] = Field(description="Service statistics")


class DatabaseHealthDetails(BaseModel):
    """Database-specific health details"""
    model_config = ConfigDict()
    
    connection_pool_size: int | None = Field(
        default=None,
        ge=0,
        description="Current connection pool size"
    )
    active_connections: int | None = Field(
        default=None,
        ge=0,
        description="Number of active connections"
    )
    query_response_time_ms: int | None = Field(
        default=None,
        ge=0,
        description="Test query response time"
    )


class ClassificationServiceHealthDetails(BaseModel):
    """Classification service health details"""
    model_config = ConfigDict()
    
    api_accessible: bool = Field(description="Whether OpenAI API is accessible")
    model: str | None = Field(default=None, description="AI model being used")
    cache_size: int | None = Field(
        default=None,
        ge=0,
        description="Current cache size"
    )
    request_count: int | None = Field(
        default=None,
        ge=0,
        description="Total requests processed"
    )
    error_rate: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Error rate (0.0 to 1.0)"
    )
