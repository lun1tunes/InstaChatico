"""Service for analyzing media images using AI."""

import logging
from typing import Optional

from .base_service import BaseService
from ..agents.tools.web_image_analyzer_tool import _analyze_image_implementation

logger = logging.getLogger(__name__)


class MediaAnalysisService(BaseService):
    """Analyze media images using OpenAI Vision API."""

    async def analyze_media_image(self, media_url: str, caption: Optional[str] = None) -> Optional[str]:
        """
        Analyze media image and generate detailed context description.

        Args:
            media_url: URL of the media image to analyze
            caption: Optional caption text to provide additional context

        Returns:
            Detailed context description or None if analysis fails
        """
        try:
            logger.info(f"Starting media analysis for URL: {media_url[:100]}...")

            # Prepare context for the image analysis
            additional_context = """Это изображение из поста Instagram. Проанализируй его детально для использования в ответах на комментарии клиентов.

ВАЖНО: При описании продуктов используй РУССКИЕ ТЕРМИНЫ и КАТЕГОРИИ, а не английские названия брендов.

Примеры:
- ❌ НЕПРАВИЛЬНО: "Lumiere Coffee Scrub"
- ✅ ПРАВИЛЬНО: "кофейный скраб для тела антицеллюлитный"

- ❌ НЕПРАВИЛЬНО: "Keratin Shampoo"
- ✅ ПРАВИЛЬНО: "кератиновый шампунь для восстановления волос"

- ❌ НЕПРАВИЛЬНО: "Vitamin C Serum"
- ✅ ПРАВИЛЬНО: "сыворотка с витамином С для лица"

Описывай продукты через их НАЗНАЧЕНИЕ и ХАРАКТЕРИСТИКИ на русском языке, чтобы клиенты могли легко их найти."""

            if caption:
                additional_context += f"\n\nПодпись к посту: {caption}"
                additional_context += "\n\nИзвлеки всю информацию, которая может быть полезна для ответов на вопросы клиентов о продуктах, услугах, ценах. Используй русские термины для описания продуктов."

            # Call the image analyzer tool directly (no agent wrapper needed)
            analysis_result = await _analyze_image_implementation(
                image_url=media_url,
                additional_context=additional_context
            )

            if not analysis_result:
                logger.warning(f"Image analysis returned empty result for {media_url}")
                return None

            # Check if it's an error message
            if analysis_result.startswith("Ошибка"):
                logger.error(f"Image analysis failed: {analysis_result}")
                return None

            logger.info(f"Media analysis completed. Context length: {len(analysis_result)} characters")

            return analysis_result

        except Exception as e:
            logger.error(f"Error analyzing media image {media_url}: {e}")
            logger.exception("Full traceback:")
            return None
