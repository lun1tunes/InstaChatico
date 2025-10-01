"""
Инструменты для агентов
"""

from .web_image_analyzer_tool import analyze_image_async
from .embedding_search_tool import embedding_search

__all__ = ["analyze_image_async", "embedding_search"]
