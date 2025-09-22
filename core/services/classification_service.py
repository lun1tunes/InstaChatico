import asyncio
from typing import Dict, Any
from langchain.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.schema import HumanMessage
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class CommentClassificationService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.openai.api_key
        self.llm = ChatOpenAI(
            openai_api_key=self.api_key,
            model=settings.openai.model,
            temperature=0.1,
            max_tokens=100,
            streaming=False
        )
        
        self.classification_prompt = PromptTemplate(
            input_variables=["comment_text"],
            template="""
            Ты — AI-ассистент, который помогает владельцам бизнеса анализировать комментарии в Instagram. Классифицируй следующий комментарий строго в одну из категорий, наиболее полезных для бизнеса.
            **Категории:**
            1.  **Positive Feedback** (Позитивный отзыв): Выражение благодарности, одобрения, восхищения продуктом/услугой или упоминание положительного опыта. Может содержать рекомендацию.
                *   *Примеры: "Супер товар, спасибо!", "Обожаю вашу кофейню, лучший бариста в городе!", "Заказ пришел мгновенно, всем советую".*
            2.  **Critical Feedback** (Критический отзыв): Конструктивная критика или негативный отзыв о продукте, услуге, доставке, обслуживании. Без прямых оскорблений.
                *   *Примеры: "Платье село после стирки", "Ждал курьера 2 часа", "В этом филиале персонал не очень внимательный".*
            3.  **Urgent Issue / Complaint** (Срочная проблема / Жалоба): Жалоба, требующая немедленного решения (проблемы с заказом, доставкой, брак). Часто содержит эмоционально окрашенные слова или призыв "исправьте!", "верните деньги!".
                *   *Примеры: "Я не получил заказ №34521, где он?!", "В продукте был посторонний предмет, это опасно!", "Верните деньги, я передумал!".*
            4.  **Question / Inquiry** (Вопрос / Запрос): Прямой вопрос о продукте, услуге, наличии, ценах, доставке, сотрудничестве. Требует предоставления информации.
                *   *Примеры: "А эта модель есть в синем цвете?", "Доставляете ли вы в область?", "Какой у вас график работы в праздники?".*
            5.  **Spam / Irrelevant** (Спам / Не относящееся к делу): Реклама сторонних услуг, флуд, оскорбления, не имеющие отношения к бизнесу комментарии, ссылки, промокоды конкурентов.
                *   *Примеры: "Заходи на мой канал о похудении!", "Продам аккаунт", Бессмысленный набор символов.*
                
            **Инструкции по классификации:**
            -   Приоритет: Если комментарий содержит и вопрос, и жалобу, классифицируй его как **Urgent Issue / Complaint**.
            -   Разграничение критики и жалобы: **Critical Feedback** — это общая критика, **Urgent Issue / Complaint** — это конкретная проблема, требующая решения.
            -   Вопрос vs. Отзыв: Если комментарий выглядит как риторический вопрос ("как можно было так испортить хороший продукт?"), это **Critical Feedback**, а не вопрос.

            Верни ответ только в формате: `категория|уверенность(0-100)`
            
            Комментарий: {comment_text}
            """
        )
    
    async def classify_comment(self, comment_text: str) -> Dict[str, Any]:
        """Асинхронная классификация комментария"""
        try:
            # Санитизация ввода
            sanitized_text = self._sanitize_input(comment_text)
            
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
            
            prompt = self.classification_prompt.format(comment_text=sanitized_text)
            
            # Асинхронный вызов LLM
            response = await self.llm.agenerate([[HumanMessage(content=prompt)]])
            result = response.generations[0][0].text.strip()
            
            return self._parse_classification_result(result, comment_text)
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return self._create_error_response(str(e))
    
    def _sanitize_input(self, text: str) -> str:
        """Базовая санитизация текста"""
        import html
        sanitized = html.escape(text)
        sanitized = ' '.join(sanitized.split())
        return sanitized
    
    def _parse_classification_result(self, result: str, original_text: str) -> Dict[str, Any]:
        """Парсинг результата от LLM"""
        try:
            if '|' in result:
                classification, confidence_str = result.split('|', 1)
                classification = classification.strip().lower()
                confidence = min(100, max(0, int(confidence_str.strip())))
            else:
                classification = result.strip().lower()
                confidence = 80
            
            # Валидация категории
            valid_categories = {'positive', 'negative', 'spam', 'question'}
            if classification not in valid_categories:
                classification = "unknown"
                confidence = 0
            
            # Дополнительный анализ
            contains_question = self._detect_question(original_text)
            sentiment_score = self._estimate_sentiment(classification, confidence)
            toxicity_score = self._estimate_toxicity(classification, confidence)
            
            return {
                "classification": classification,
                "confidence": confidence,
                "contains_question": contains_question,
                "sentiment_score": sentiment_score,
                "toxicity_score": toxicity_score,
                "llm_raw_response": result,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Parse classification error: {e}")
            return self._create_error_response(f"Parse error: {e}")
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        return {
            "classification": "unknown",
            "confidence": 0,
            "contains_question": False,
            "sentiment_score": 0,
            "toxicity_score": 0,
            "llm_raw_response": None,
            "error": error_message
        }
    
    def _detect_question(self, text: str) -> bool:
        question_indicators = ['?', 'как', 'что', 'где', 'когда', 'почему', 'зачем']
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in question_indicators)
    
    def _estimate_sentiment(self, classification: str, confidence: int) -> int:
        sentiment_map = {
            'positive': confidence,
            'negative': -confidence,
            'spam': -50,
            'question': 0,
            'unknown': 0
        }
        return sentiment_map.get(classification, 0)
    
    def _estimate_toxicity(self, classification: str, confidence: int) -> int:
        if classification == 'negative':
            return min(100, confidence + 20)
        elif classification == 'spam':
            return 60
        return 0