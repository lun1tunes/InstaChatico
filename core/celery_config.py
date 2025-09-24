"""
Clean and understanding-friendly Celery configuration for InstaChatico.
Centralized setup with clear documentation and organized settings.
"""

from celery import Celery
from celery.schedules import crontab
from typing import Dict, Any

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__, "celery_config")


class CeleryConfig:
    """Centralized Celery configuration with clear organization"""
    
    # Basic Celery settings
    BROKER_URL = settings.celery.broker_url
    RESULT_BACKEND = settings.celery.result_backend
    
    # Task serialization settings
    TASK_SERIALIZER = 'json'
    ACCEPT_CONTENT = ['json']
    RESULT_SERIALIZER = 'json'
    
    # Timezone settings
    TIMEZONE = 'UTC'
    ENABLE_UTC = True
    
    # Worker settings for performance and reliability
    WORKER_PREFETCH_MULTIPLIER = 1  # Prevent memory issues
    TASK_ACKS_LATE = True           # Acknowledge tasks only after completion
    WORKER_MAX_TASKS_PER_CHILD = 100  # Restart workers periodically
    
    # Task timeout settings
    TASK_SOFT_TIME_LIMIT = 300      # 5 minutes soft limit
    TASK_TIME_LIMIT = 600           # 10 minutes hard limit
    
    # Task routing - organize tasks by type
    TASK_ROUTES = {
        # AI/LLM tasks go to specialized queue
        'core.tasks.classification.classify_comment': {'queue': 'ai_queue'},
        'core.tasks.answer_generation.generate_answer': {'queue': 'ai_queue'},
        
        # Instagram API tasks go to separate queue
        'core.tasks.instagram_replies.send_reply': {'queue': 'instagram_queue'},
        
        # Maintenance tasks go to background queue
        'core.tasks.maintenance.retry_failed_tasks': {'queue': 'maintenance_queue'},
        'core.tasks.maintenance.cleanup_old_records': {'queue': 'maintenance_queue'},
    }
    
    # Periodic tasks schedule
    BEAT_SCHEDULE = {
        # Retry failed classifications every 15 minutes
        'retry-failed-classifications': {
            'task': 'core.tasks.maintenance.retry_failed_classifications',
            'schedule': crontab(minute='*/15'),
            'options': {'queue': 'maintenance_queue'}
        },
        
        # Retry failed answer generation every 20 minutes
        'retry-failed-answers': {
            'task': 'core.tasks.maintenance.retry_failed_answers', 
            'schedule': crontab(minute='*/20'),
            'options': {'queue': 'maintenance_queue'}
        },
        
        # Process pending questions every 2 minutes
        'process-pending-questions': {
            'task': 'core.tasks.answer_generation.process_pending_questions',
            'schedule': crontab(minute='*/2'),
            'options': {'queue': 'ai_queue'}
        },
        
        # Process pending Instagram replies every 5 minutes
        'process-pending-replies': {
            'task': 'core.tasks.instagram_replies.process_pending_replies',
            'schedule': crontab(minute='*/5'),
            'options': {'queue': 'instagram_queue'}
        },
        
        # Cleanup old completed tasks daily at 2 AM
        'cleanup-old-records': {
            'task': 'core.tasks.maintenance.cleanup_old_records',
            'schedule': crontab(hour=2, minute=0),
            'options': {'queue': 'maintenance_queue'}
        }
    }


def create_celery_app() -> Celery:
    """
    Create and configure Celery application with organized settings.
    
    Returns:
        Configured Celery application instance
    """
    # Create Celery app
    app = Celery(
        'instachatico',
        broker=CeleryConfig.BROKER_URL,
        backend=CeleryConfig.RESULT_BACKEND
    )
    
    # Apply configuration
    app.conf.update(
        # Serialization
        task_serializer=CeleryConfig.TASK_SERIALIZER,
        accept_content=CeleryConfig.ACCEPT_CONTENT,
        result_serializer=CeleryConfig.RESULT_SERIALIZER,
        
        # Timezone
        timezone=CeleryConfig.TIMEZONE,
        enable_utc=CeleryConfig.ENABLE_UTC,
        
        # Worker settings
        worker_prefetch_multiplier=CeleryConfig.WORKER_PREFETCH_MULTIPLIER,
        task_acks_late=CeleryConfig.TASK_ACKS_LATE,
        worker_max_tasks_per_child=CeleryConfig.WORKER_MAX_TASKS_PER_CHILD,
        
        # Task limits
        task_soft_time_limit=CeleryConfig.TASK_SOFT_TIME_LIMIT,
        task_time_limit=CeleryConfig.TASK_TIME_LIMIT,
        
        # Task routing
        task_routes=CeleryConfig.TASK_ROUTES,
        
        # Periodic tasks
        beat_schedule=CeleryConfig.BEAT_SCHEDULE,
    )
    
    # Import task modules to register them
    from . import tasks
    
    logger.info(
        "Celery application configured",
        extra_fields={
            "broker": CeleryConfig.BROKER_URL,
            "queues": list(set(route['queue'] for route in CeleryConfig.TASK_ROUTES.values())),
            "periodic_tasks": len(CeleryConfig.BEAT_SCHEDULE)
        }
    )
    
    return app


# Create the global Celery app instance
celery_app = create_celery_app()


def get_celery_app() -> Celery:
    """Get the configured Celery application instance"""
    return celery_app


def get_queue_info() -> Dict[str, Any]:
    """Get information about configured queues and routing"""
    queues = set()
    for route in CeleryConfig.TASK_ROUTES.values():
        queues.add(route['queue'])
    
    return {
        "queues": list(queues),
        "task_routes": CeleryConfig.TASK_ROUTES,
        "periodic_tasks": list(CeleryConfig.BEAT_SCHEDULE.keys()),
        "worker_settings": {
            "prefetch_multiplier": CeleryConfig.WORKER_PREFETCH_MULTIPLIER,
            "max_tasks_per_child": CeleryConfig.WORKER_MAX_TASKS_PER_CHILD,
            "soft_time_limit": CeleryConfig.TASK_SOFT_TIME_LIMIT,
            "time_limit": CeleryConfig.TASK_TIME_LIMIT
        }
    }
