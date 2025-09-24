"""
Simplified service base classes with essential functionality only.
"""

import time
import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime

from ..logging_config import get_logger
from ..exceptions import ServiceError


class BaseService(ABC):
    """Simplified base service with essential functionality"""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        self.logger = get_logger(f"service.{service_name}", service_name)
        self._initialized_at = datetime.utcnow()
        self._request_count = 0
        self._error_count = 0
    
    @property
    def stats(self) -> Dict[str, Any]:
        """Get basic service statistics"""
        uptime = (datetime.utcnow() - self._initialized_at).total_seconds()
        return {
            "service": self.service_name,
            "uptime_seconds": uptime,
            "requests": self._request_count,
            "errors": self._error_count,
            "error_rate": self._error_count / max(self._request_count, 1)
        }
    
    def _track_request(self) -> None:
        """Track a request"""
        self._request_count += 1
    
    def _track_error(self) -> None:
        """Track an error"""
        self._error_count += 1
    
    async def health_check(self) -> Dict[str, Any]:
        """Basic health check"""
        try:
            result = await self._perform_health_check()
            return {"healthy": True, "service": self.service_name, **result}
        except Exception as e:
            return {"healthy": False, "service": self.service_name, "error": str(e)}
    
    @abstractmethod
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Service-specific health check implementation"""
        pass


class EnhancedService(BaseService):
    """Service with retry logic and basic caching"""
    
    def __init__(self, service_name: str, max_retries: int = 3, cache_ttl: int = 300):
        super().__init__(service_name)
        self.max_retries = max_retries
        self.cache_ttl = cache_ttl
        self._cache = {}
        self._cache_timestamps = {}
    
    async def execute_with_retry(self, operation_name: str, operation_func, *args, **kwargs):
        """Execute operation with retry logic"""
        last_exception = None
        
        for attempt in range(self.max_retries + 1):
            try:
                self._track_request()
                result = await operation_func(*args, **kwargs)
                
                if attempt > 0:
                    self.logger.info(f"Operation {operation_name} succeeded on attempt {attempt + 1}")
                
                return result
                
            except Exception as e:
                last_exception = e
                self._track_error()
                
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    self.logger.warning(
                        f"Operation {operation_name} failed (attempt {attempt + 1}), retrying in {wait_time}s",
                        extra_fields={"error": str(e)}
                    )
                    await asyncio.sleep(wait_time)
                else:
                    self.logger.error(f"Operation {operation_name} failed after {self.max_retries + 1} attempts")
        
        raise ServiceError(f"Operation {operation_name} failed: {str(last_exception)}")
    
    def _get_from_cache(self, key: str) -> Optional[Any]:
        """Get value from cache if valid"""
        if key in self._cache_timestamps:
            age = time.time() - self._cache_timestamps[key]
            if age < self.cache_ttl:
                return self._cache[key]
            else:
                # Remove expired entry
                del self._cache[key]
                del self._cache_timestamps[key]
        return None
    
    def _set_cache(self, key: str, value: Any) -> None:
        """Set value in cache"""
        self._cache[key] = value
        self._cache_timestamps[key] = time.time()
    
    def clear_cache(self) -> None:
        """Clear all cache entries"""
        self._cache.clear()
        self._cache_timestamps.clear()
        self.logger.info("Cache cleared")
