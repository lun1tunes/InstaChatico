"""
Clean Celery worker entry point for InstaChatico.
Imports all tasks and provides the Celery app for workers.
"""
import os
import sys

# Add the app directory to Python path
sys.path.insert(0, '/app')

# Initialize logging first
from core.logging_config import setup_logging
setup_logging(
    log_level=os.getenv("LOG_LEVEL", "INFO"),
    log_format="structured"
)

# Import the configured Celery app
from core.celery_config import celery_app

# Import all task modules to ensure they are registered with Celery
# This is required for Celery to discover and execute tasks
import core.tasks

# Export the celery app for Celery workers to use
app = celery_app
