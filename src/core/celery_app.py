from celery import Celery
from celery.schedules import crontab
from .config import settings
import os
from celery.signals import before_task_publish, task_prerun
from core.logging_config import trace_id_ctx

celery_app = Celery(
    "instagram_classifier",
    broker=settings.celery.broker_url,
    backend=settings.celery.result_backend,
    include=[
        "core.tasks.classification_tasks",
        "core.tasks.answer_tasks",
        "core.tasks.instagram_reply_tasks",
        "core.tasks.telegram_tasks",
        "core.tasks.health_tasks",
        "core.tasks.media_tasks",
    ],
)

# Force import of all task modules to ensure they are registered
import core.tasks.classification_tasks
import core.tasks.answer_tasks
import core.tasks.instagram_reply_tasks
import core.tasks.telegram_tasks
import core.tasks.health_tasks
import core.tasks.media_tasks

# Настройки Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
    # Keep Celery from reconfiguring root logger; we configure in celery_worker.py
    worker_hijack_root_logger=False,
    # Unify Celery's own log formats with our console formatter
    worker_log_format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    worker_task_log_format="%(asctime)s | %(levelname)s | %(task_name)s[%(task_id)s] | %(message)s",
    # Redirect stdout/stderr to suppress banner noise at WARNING level
    worker_redirect_stdouts=True,
    worker_redirect_stdouts_level="WARNING",
    # Suppress verbose Celery startup output
    worker_log_color=False,
    worker_disable_rate_limits=True,
    task_routes={
        "core.tasks.classification_tasks.classify_comment_task": {"queue": "llm_queue"},
        "core.tasks.answer_tasks.generate_answer_task": {"queue": "llm_queue"},
        "core.tasks.media_tasks.analyze_media_image_task": {"queue": "llm_queue"},
        "core.tasks.instagram_reply_tasks.send_instagram_reply_task": {"queue": "instagram_queue"},
        "core.tasks.instagram_reply_tasks.hide_instagram_comment_task": {"queue": "instagram_queue"},
        "core.tasks.telegram_tasks.send_telegram_notification_task": {"queue": "instagram_queue"},
    },
    task_soft_time_limit=300,
    task_time_limit=600,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    worker_max_tasks_per_child=100,
    # Suppress deprecation warning about task cancellation on connection loss
    # This will be the default behavior in Celery 6.0
    worker_cancel_long_running_tasks_on_connection_loss=True,
)

# Периодические задачи
celery_app.conf.beat_schedule = {
    "retry-failed-classifications": {
        "task": "core.tasks.classification_tasks.retry_failed_classifications",
        "schedule": crontab(minute="*/15"),
    },
    "retry-failed-answers": {
        "task": "core.tasks.answer_tasks.retry_failed_answers",
        "schedule": crontab(minute="*/20"),
    },
    "process-pending-questions": {
        "task": "core.tasks.answer_tasks.process_pending_questions_task",
        "schedule": crontab(minute="*"),  # Every minute
    },
    "check-system-health": {
        "task": "core.tasks.health_tasks.check_system_health_task",
        "schedule": settings.health.check_interval_seconds,
    },
}


# Propagate trace_id via Celery headers
@before_task_publish.connect
def add_trace_id_on_publish(headers=None, body=None, **kwargs):
    trace_id = trace_id_ctx.get()
    if trace_id:
        headers = headers or {}
        headers.setdefault("trace_id", trace_id)


@task_prerun.connect
def bind_trace_id_on_worker(task_id=None, task=None, **kwargs):
    try:
        tid = getattr(task.request, "headers", {}).get("trace_id")
        if tid:
            trace_id_ctx.set(tid)
    except Exception:
        pass
