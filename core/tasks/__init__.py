"""
Celery tasks for InstaChatico - organized by functionality.

Task Organization:
- classification.py: AI comment classification tasks
- answer_generation.py: AI answer generation tasks  
- instagram_replies.py: Instagram API interaction tasks
- maintenance.py: Background maintenance and retry tasks
"""

# Import all task modules to ensure they are registered with Celery
from . import classification
from . import answer_generation
from . import instagram_replies
from . import maintenance

__all__ = [
    "classification",
    "answer_generation", 
    "instagram_replies",
    "maintenance"
]
