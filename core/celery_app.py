from celery import Celery
from celery.schedules import crontab
from .config import settings

celery_app = Celery(
    'instagram_classifier',
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
    include=['core.tasks.classification_tasks']
)

# Настройки Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
    task_routes={
        'core.tasks.classification_tasks.classify_comment_task': {'queue': 'llm_queue'},
    },
    task_soft_time_limit=300,
    task_time_limit=600,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=100,
)

# Периодические задачи
celery_app.conf.beat_schedule = {
    'retry-failed-classifications': {
        'task': 'core.tasks.classification_tasks.retry_failed_classifications',
        'schedule': crontab(minute='*/15'),
    },
}