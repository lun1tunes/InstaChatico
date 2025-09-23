import asyncio
from typing import Dict, Any, Literal
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from pydantic import BaseModel, Field
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class ClassificationResult(BaseModel):
    """Pydantic model for structured classification output"""
    classification: Literal[
        "positive feedback",
        "critical feedback", 
        "urgent issue / complaint",
        "question / inquiry",
        "spam / irrelevant"
    ] = Field(description="The classification category for the comment")
    confidence: int = Field(ge=0, le=100, description="Confidence score from 0 to 100")
    reasoning: str = Field(description="Brief explanation of why this classification was chosen")
    contains_question: bool = Field(description="Whether the comment contains a question")
    sentiment_score: int = Field(ge=-100, le=100, description="Sentiment score from -100 (negative) to 100 (positive)")
    toxicity_score: int = Field(ge=0, le=100, description="Toxicity score from 0 (safe) to 100 (toxic)")

class CommentClassificationService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.openai.api_key
        self.llm = ChatOpenAI(
            openai_api_key=self.api_key,
            model=settings.openai.model,
            temperature=0.1,
            max_tokens=500,  # Increased for structured output
            streaming=False
        )
        
        # Note: Using JSON parsing instead of structured output for compatibility
        
        self.classification_prompt = PromptTemplate(
            input_variables=["comment_text"],
            template="""
            You are an AI assistant that helps business owners analyze Instagram comments. Classify the following comment strictly into one of the categories most useful for business operations.
            
            **Categories:**
            1.  **positive feedback**: Expressions of gratitude, approval, admiration for products/services, or mentions of positive experiences. May include recommendations.
                *Examples: "Great product, thanks!", "Love your coffee shop, best barista in town!", "Order arrived instantly, I recommend to everyone".*
            2.  **critical feedback**: Constructive criticism or negative reviews about products, services, delivery, customer service. Without direct insults.
                *Examples: "Dress shrunk after washing", "Waited for courier for 2 hours", "Staff at this branch is not very attentive".*
            3.  **urgent issue / complaint**: Complaints requiring immediate resolution (order problems, delivery issues, defects). Often contains emotionally charged words or calls to "fix this!", "refund my money!".
                *Examples: "I didn't receive order #34521, where is it?!", "There was a foreign object in the product, this is dangerous!", "Refund my money, I changed my mind!".*
            4.  **question / inquiry**: Direct questions about BUSINESS-RELATED topics only: products, services, availability, prices, delivery, business hours, collaboration, technical specifications, warranty, returns, etc. Questions about weather, movies, personal life, or unrelated topics should be classified as spam/irrelevant.
                *Examples: "Is this model available in blue?", "Do you deliver to my region?", "What are your business hours on holidays?", "What's the warranty period?", "Can I return this item?".*
            5.  **spam / irrelevant**: Advertisements for other services, spam, insults, comments unrelated to business, competitor links/promo codes, personal questions about weather/cinema/life, off-topic discussions.
                *Examples: "Check out my weight loss channel!", "Selling account", "What's the weather like today?", "Did you see the new movie?", Random character strings.*
                
            **Classification Instructions:**
            -   Priority: If a comment contains both a question and a complaint, classify it as **urgent issue / complaint**.
            -   Distinction between criticism and complaint: **critical feedback** is general criticism, **urgent issue / complaint** is a specific problem requiring resolution.
            -   Question vs. Review: If a comment looks like a rhetorical question ("how could you ruin such a good product?"), it's **critical feedback**, not a question.
            -   Business Focus: Only classify as **question / inquiry** if the question is DIRECTLY related to the business, products, or services. Personal questions, weather, entertainment, or general chit-chat should be **spam / irrelevant**.
            
            **Additional Requirements:**
            - confidence: Rate confidence in classification from 0 to 100
            - reasoning: Briefly explain why this specific category was chosen. IMPORTANT: Provide the reasoning in the same language as the comment (if comment is in Russian, respond in Russian; if in English, respond in English, etc.)
            - contains_question: Determine if the comment contains a direct question (even if it's not the main category)
            - sentiment_score: Rate overall tone from -100 (very negative) to 100 (very positive)
            - toxicity_score: Rate toxicity from 0 (safe) to 100 (very toxic)
            
            Comment: {comment_text}
            
            CRITICAL LANGUAGE REQUIREMENT: The reasoning field MUST be written in the EXACT SAME LANGUAGE as the comment above. 
            Examples:
            - If comment is "What is the price?" (English) → reasoning should be in English: "The comment asks about pricing..."
            - If comment is "Какая цена?" (Russian) → reasoning should be in Russian: "Комментарий спрашивает о цене..."
            - If comment is "¿Cuál es el precio?" (Spanish) → reasoning should be in Spanish: "El comentario pregunta sobre el precio..."
            
            Return response in JSON format with fields: classification, confidence, reasoning, contains_question, sentiment_score, toxicity_score
            """
        )
    
    async def classify_comment(self, comment_text: str) -> Dict[str, Any]:
        """Asynchronous comment classification using JSON output"""
        try:
            # Input sanitization
            sanitized_text = self._sanitize_input(comment_text)
            
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
            
            prompt = self.classification_prompt.format(comment_text=sanitized_text)
            
            # Asynchronous LLM call
            response = await self.llm.agenerate([[HumanMessage(content=prompt)]])
            result_text = response.generations[0][0].text.strip()
            
            # Attempt JSON parsing
            try:
                import json
                json_result = json.loads(result_text)
                
                # Validation and creation of ClassificationResult
                classification_result = ClassificationResult(**json_result)
                
                return {
                    "classification": classification_result.classification,
                    "confidence": classification_result.confidence,
                    "contains_question": classification_result.contains_question,
                    "sentiment_score": classification_result.sentiment_score,
                    "toxicity_score": classification_result.toxicity_score,
                    "reasoning": classification_result.reasoning,
                    "llm_raw_response": result_text,
                    "error": None
                }
                
            except (json.JSONDecodeError, ValueError) as json_error:
                logger.warning(f"JSON parsing failed: {json_error}, falling back to manual parsing")
                return self._parse_classification_result(result_text, comment_text)
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            return self._create_error_response(str(e))
    
    def _sanitize_input(self, text: str) -> str:
        """Basic text sanitization"""
        import html
        sanitized = html.escape(text)
        sanitized = ' '.join(sanitized.split())
        return sanitized
    
    def _parse_classification_result(self, result: str, original_text: str) -> Dict[str, Any]:
        """Parsing LLM result"""
        try:
            if '|' in result:
                classification, confidence_str = result.split('|', 1)
                classification = classification.strip().lower()
                confidence = min(100, max(0, int(confidence_str.strip())))
            else:
                classification = result.strip().lower()
                confidence = 80
            
            # Category validation
            valid_categories = {
                'positive feedback', 'critical feedback', 'urgent issue / complaint', 
                'question / inquiry', 'spam / irrelevant'
            }
            if classification not in valid_categories:
                classification = "unknown"
                confidence = 0
            
            # Additional analysis
            contains_question = self._detect_question(original_text)
            sentiment_score = self._estimate_sentiment(classification, confidence)
            toxicity_score = self._estimate_toxicity(classification, confidence)
            
            return {
                "classification": classification,
                "confidence": confidence,
                "contains_question": contains_question,
                "sentiment_score": sentiment_score,
                "toxicity_score": toxicity_score,
                "reasoning": f"Manual parsing: {classification} with {confidence}% confidence",
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
            "reasoning": f"Error occurred: {error_message}",
            "llm_raw_response": None,
            "error": error_message
        }
    
    def _detect_question(self, text: str) -> bool:
        question_indicators = ['?', 'как', 'что', 'где', 'когда', 'почему', 'зачем']
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in question_indicators)
    
    def _estimate_sentiment(self, classification: str, confidence: int) -> int:
        sentiment_map = {
            'positive feedback': confidence,
            'critical feedback': -confidence,
            'urgent issue / complaint': -confidence,
            'question / inquiry': 0,
            'spam / irrelevant': -50,
            'unknown': 0
        }
        return sentiment_map.get(classification, 0)
    
    def _estimate_toxicity(self, classification: str, confidence: int) -> int:
        if classification in ['critical feedback', 'urgent issue / complaint']:
            return min(100, confidence + 20)
        elif classification == 'spam / irrelevant':
            return 60
        return 0