from celery import Celery
from celery.schedules import crontab
from .config import settings

celery_app = Celery(
    'instagram_classifier',
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
    include=['core.tasks.classification_tasks', 'core.tasks.answer_tasks', 'core.tasks.instagram_reply_tasks', 'core.tasks.telegram_tasks']
)

# Force import of all task modules to ensure they are registered
import core.tasks.classification_tasks
import core.tasks.answer_tasks
import core.tasks.instagram_reply_tasks
import core.tasks.telegram_tasks

# Настройки Celery
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Europe/Moscow',
    enable_utc=True,
    task_routes={
        'core.tasks.classification_tasks.classify_comment_task': {'queue': 'llm_queue'},
        'core.tasks.answer_tasks.generate_answer_task': {'queue': 'llm_queue'},
        'core.tasks.instagram_reply_tasks.send_instagram_reply_task': {'queue': 'instagram_queue'},
        'core.tasks.instagram_reply_tasks.process_pending_replies_task': {'queue': 'instagram_queue'},
        'core.tasks.telegram_tasks.send_telegram_notification_task': {'queue': 'instagram_queue'},
        'core.tasks.telegram_tasks.test_telegram_connection': {'queue': 'instagram_queue'},
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
    'retry-failed-answers': {
        'task': 'core.tasks.answer_tasks.retry_failed_answers',
        'schedule': crontab(minute='*/20'),
    },
    'process-pending-questions': {
        'task': 'core.tasks.answer_tasks.process_pending_questions_task',
        'schedule': crontab(minute='*'),  # Every minute
    },
    'process-pending-replies': {
        'task': 'core.tasks.instagram_reply_tasks.process_pending_replies_task',
        'schedule': crontab(minute='*/5'),  # Every 5 minutes
    },
}