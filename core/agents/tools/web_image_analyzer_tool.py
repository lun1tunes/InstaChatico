"""
Web Image Analyzer Tool

Асинхронный инструмент для анализа изображений с помощью OpenAI Vision API.
Анализирует изображения по URL и извлекает детальную информацию, особенно финансовые данные.
"""

import logging
from typing import Optional
from openai import AsyncOpenAI
from ...config import settings
from agents import function_tool

logger = logging.getLogger(__name__)


async def _analyze_image_implementation(image_url: str, additional_context: Optional[str] = None) -> str:
    """
    Анализирует изображение по URL с помощью OpenAI Vision API

    Args:
        image_url: URL изображения для анализа
        additional_context: Дополнительный контекст для анализа (опционально, если есть описание поста и т.п.)

    Returns:
        Строка с результатами анализа изображения
    """
    try:
        logger.info(f"Starting image analysis for URL: {image_url}")

        # Инициализируем OpenAI клиент
        client = AsyncOpenAI(api_key=settings.openai.api_key)

        # Базовый промт с подробными инструкциями
        base_prompt = """
        Ты - эксперт по анализу изображений с особым фокусом на извлечение максимально полной информации.
        
        Твоя задача - детально анализировать изображение и извлекать всю доступную информацию.
        
        Для финансовых графиков и диаграмм ОБЯЗАТЕЛЬНО:
        - Внимательно анализируй ВСЕ цифры, цены, даты на графике
        - Определяй тренды: рост, падение, стабильность
        - Извлекай конкретные значения: цены, проценты, временные периоды
        - Анализируй масштаб и единицы измерения
        - Определяй тип графика: линейный, свечной, гистограмма, круговая диаграмма
        - Выделяй ключевые точки: максимумы, минимумы, развороты
        - Обращай внимание на подписи осей, легенды, заголовки
        - Если видишь конкретные числа - обязательно их указывай точно
        
        Для изображений с описанием акций или услуг:
        - Извлекай всю текстовую информацию
        - Выделяй названия компаний, продуктов, услуг
        - Указывай цены, скидки, акции
        - Определяй контактную информацию
        - Выделяй ключевые преимущества и особенности
        
        Для расписаний и календарей:
        - Извлекай все даты и время
        - Определяй события, встречи, мероприятия
        - Указывай места проведения
        - Выделяй участников и организаторов
        
        Для обычных изображений:
        - Описывай что изображено
        - Указывай стиль, композицию, цвета
        - Выделяй ключевые элементы
        - Определяй эмоциональную окраску
        
        Всегда будь точным и объективным в описаниях. Извлекай максимум информации из визуального контента.
        """

        # Добавляем дополнительный контекст если предоставлен
        if additional_context:
            prompt = f"{base_prompt}\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ: {additional_context}"
        else:
            prompt = base_prompt

        # Вызываем OpenAI Vision API
        response = await client.chat.completions.create(
            model="gpt-4o",  # Используем GPT-4o для анализа изображений
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": image_url,
                                "detail": "high",  # Высокое качество для детального анализа
                            },
                        },
                    ],
                }
            ],
            max_tokens=2000,
            temperature=0.1,  # Низкая температура для более точного анализа
        )

        # Извлекаем результат
        analysis_result = response.choices[0].message.content

        logger.info(f"Image analysis completed for URL: {image_url}")

        return analysis_result

    except Exception as e:
        logger.error(f"Error in image analysis for {image_url}: {e}")
        return f"Ошибка при анализе изображения: {str(e)}"


# Создаем инструмент с декоратором @function_tool
analyze_image_async = function_tool(_analyze_image_implementation)
