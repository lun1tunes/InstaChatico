"""
Celery worker entry point that ensures all tasks are imported
"""
import os
import sys

# Add the app directory to Python path
sys.path.insert(0, '/app')

# Import all task modules to ensure they are registered
import core.tasks.classification_tasks
import core.tasks.answer_tasks
import core.tasks.telegram_tasks        
import core.tasks.instagram_reply_tasks

# Import the celery app
from core.celery_app import celery_app

# Export the celery app for Celery to use
app = celery_app
