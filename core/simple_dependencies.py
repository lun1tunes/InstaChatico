"""
Simplified dependency injection with essential services only.
"""

from typing import AsyncGenerator
from functools import lru_cache
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .models.db_helper import db_helper
from .services.classification import CommentClassificationService
from .logging_config import get_logger

logger = get_logger(__name__, "dependencies")


# Service instances (singletons)
_classification_service = None


@lru_cache()
def get_classification_service() -> CommentClassificationService:
    """Get classification service singleton"""
    global _classification_service
    if _classification_service is None:
        _classification_service = CommentClassificationService(settings.openai.api_key)
        logger.info("Classification service initialized")
    return _classification_service


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get database session dependency"""
    async with db_helper.session_dependency() as session:
        try:
            yield session
        except Exception as e:
            logger.error("Database session error", extra_fields={"error": str(e)})
            raise
        finally:
            logger.debug("Database session closed")


def get_settings():
    """Get application settings"""
    return settings


class HealthChecker:
    """Simple health checker"""
    
    async def check_database(self) -> bool:
        """Check database connectivity"""
        try:
            async with db_helper.session_dependency() as session:
                from sqlalchemy import text
                await session.execute(text("SELECT 1"))
                return True
        except Exception as e:
            logger.error("Database health check failed", extra_fields={"error": str(e)})
            return False
    
    async def check_classification_service(self) -> bool:
        """Check classification service"""
        try:
            service = get_classification_service()
            health = await service.health_check()
            return health.get("healthy", False)
        except Exception as e:
            logger.error("Classification service health check failed", extra_fields={"error": str(e)})
            return False
    
    async def get_overall_health(self) -> dict:
        """Get overall system health"""
        db_healthy = await self.check_database()
        classification_healthy = await self.check_classification_service()
        
        return {
            "healthy": db_healthy and classification_healthy,
            "services": {
                "database": db_healthy,
                "classification": classification_healthy
            }
        }


@lru_cache()
def get_health_checker() -> HealthChecker:
    """Get health checker instance"""
    return HealthChecker()


# Reset function for testing
def reset_dependencies():
    """Reset all cached dependencies"""
    global _classification_service
    _classification_service = None
    get_classification_service.cache_clear()
    get_health_checker.cache_clear()
    logger.info("Dependencies reset")
