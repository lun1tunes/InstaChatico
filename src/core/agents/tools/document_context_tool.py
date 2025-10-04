"""
Business documents context tool for answer agent.
Provides access to client business information (hours, location, promotions, policies).
IMPORTANT: This tool does NOT provide prices - prices come from embedding_search only.
"""

import logging
from typing import Optional
from agents import function_tool
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from ...config import settings
from ...services.document_context_service import document_context_service

logger = logging.getLogger(__name__)


async def _document_context_implementation(client_id: Optional[str] = None) -> str:
    """
    Получить контекст бизнес-документов компании для ответов клиентам.

    Этот инструмент предоставляет информацию из загруженных документов компании (PDF, Excel и т.д.),
    преобразованных в формат Markdown для анализа AI-агентом.

    ⚠️ КРИТИЧЕСКИ ВАЖНО: Этот инструмент НЕ СОДЕРЖИТ информации о ценах!
    Цены ВСЕГДА берутся ТОЛЬКО из инструмента embedding_search (векторный поиск).

    ИСПОЛЬЗУЙ ЭТОТ ИНСТРУМЕНТ ДЛЯ:
    - Время работы и график компании
    - Адрес и местоположение
    - Текущие акции и специальные предложения
    - Политика компании (доставка, возврат, гарантия)
    - Контактная информация
    - Общее описание услуг и продуктов (БЕЗ ЦЕН)

    НЕ ИСПОЛЬЗУЙ для:
    - Вопросов о ценах (используй embedding_search)
    - Информации, которая может быстро устареть

    Args:
        client_id: ID клиента (Instagram аккаунт). Опционально - если не указан,
                  используется username из медиа-контекста или "default_client".

    Returns:
        Отформатированный Markdown-контекст с бизнес-информацией из документов,
        или сообщение что документы отсутствуют.

    Examples:
        Правильное использование:
        - Клиент: "Какой у вас график работы?" → Вызови document_context() и найди режим работы
        - Клиент: "Где вы находитесь?" → Вызови document_context() и найди адрес
        - Клиент: "Какие сейчас акции?" → Вызови document_context() и найди акции

        Неправильное использование:
        - Клиент: "Сколько стоит услуга?" → ❌ НЕ используй document_context, используй embedding_search
    """
    try:
        logger.info(f"Document context tool called with client_id: '{client_id}'")

        # Create database session
        engine = create_async_engine(settings.db.url, echo=settings.db.echo)
        session_factory = async_sessionmaker(bind=engine, autoflush=False, autocommit=False)

        async with session_factory() as session:
            # If no client_id specified, get ALL documents (for single Instagram account apps)
            # Or try to get from the first available client
            if not client_id:
                from sqlalchemy import select
                from ...models.client_document import ClientDocument

                # Get first available client_id with completed documents
                result = await session.execute(
                    select(ClientDocument.client_id).where(ClientDocument.processing_status == "completed").limit(1)
                )
                first_client = result.scalar_one_or_none()

                if first_client:
                    client_id = first_client
                    logger.info(f"Auto-detected client_id: '{client_id}'")
                else:
                    return (
                        f"⚠️ NO BUSINESS DOCUMENTS AVAILABLE\n\n"
                        f"No business documents have been uploaded yet.\n"
                        f"Please inform the customer that specific business information "
                        f"(hours, location, policies) should be requested via direct contact.\n\n"
                        f"💡 Suggestion: Provide contact information (phone, email, DM) for detailed inquiries."
                    )

            # Get formatted context from service
            context = await document_context_service.get_client_context(client_id=client_id, session=session)

            if not context or context.strip() == "# Business Information":
                return (
                    f"⚠️ NO BUSINESS DOCUMENTS AVAILABLE\n\n"
                    f"No business documents have been uploaded for client '{client_id}'.\n"
                    f"Please inform the customer that specific business information "
                    f"(hours, location, policies) should be requested via direct contact.\n\n"
                    f"💡 Suggestion: Provide contact information (phone, email, DM) for detailed inquiries."
                )

            # Return the formatted markdown context
            formatted_output = f"✅ Business Documents Context:\n\n{context}\n\n"
            formatted_output += (
                f"💡 Usage: Use this information to answer questions about business hours, "
                f"location, promotions, and policies. DO NOT use prices from these documents - "
                f"always use embedding_search for price information."
            )

            logger.info(f"Document context retrieved: {len(context)} characters for client '{client_id}'")
            return formatted_output

    except Exception as e:
        error_msg = f"❌ Error retrieving business documents: {str(e)}"
        logger.error(error_msg)
        return error_msg
    finally:
        # Clean up database connection
        if "engine" in locals():
            await engine.dispose()


# Create the tool using @function_tool decorator
# This makes it available to OpenAI Agents SDK
document_context = function_tool(_document_context_implementation)
