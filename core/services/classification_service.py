import asyncio
import time
from typing import Dict, Any, Literal, Optional
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from pydantic import BaseModel, Field

from ..config import settings
from ..exceptions import (
    ClassificationError, 
    ClassificationServiceError, 
    ClassificationTimeoutError,
    handle_llm_error
)
from .base import RetryableService, CacheableService, TimedOperation

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

class CommentClassificationService(RetryableService, CacheableService):
    """Enhanced comment classification service with retry, caching, and better error handling"""
    
    def __init__(
        self, 
        api_key: Optional[str] = None,
        max_retries: int = 3,
        cache_ttl: int = 3600,  # Cache for 1 hour
        timeout_seconds: int = 30
    ):
        # Initialize parent classes
        RetryableService.__init__(self, "classification", max_retries=max_retries)
        CacheableService.__init__(self, "classification", cache_ttl=cache_ttl)
        
        self.api_key = api_key or settings.openai.api_key
        self.timeout_seconds = timeout_seconds
        
        # Validate API key
        if not self.api_key:
            raise ClassificationServiceError("OpenAI API key is required")
        
        # Initialize LLM
        try:
            self.llm = ChatOpenAI(
                openai_api_key=self.api_key,
                model=settings.openai.model,
                temperature=0.1,
                max_tokens=500,
                streaming=False,
                request_timeout=self.timeout_seconds
            )
        except Exception as e:
            raise ClassificationServiceError(f"Failed to initialize OpenAI client: {str(e)}")
        
        self.logger.info(
            "Classification service initialized",
            extra_fields={
                "model": settings.openai.model,
                "max_retries": max_retries,
                "cache_ttl": cache_ttl,
                "timeout_seconds": timeout_seconds
            }
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
    
    async def classify_comment(
        self, 
        comment_text: str, 
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> Dict[str, Any]:
        """
        Classify a comment with enhanced error handling and caching
        
        Args:
            comment_text: Text to classify
            use_cache: Whether to use cached results
            force_refresh: Force refresh cache even if valid entry exists
            
        Returns:
            Classification result dictionary
        """
        if not comment_text or not comment_text.strip():
            raise ClassificationError("Comment text cannot be empty")
        
        # Clear cache if force refresh requested
        if force_refresh and use_cache:
            cache_key = self._get_cache_key("classify", comment_text.strip())
            if cache_key in self._cache:
                del self._cache[cache_key]
                del self._cache_timestamps[cache_key]
        
        try:
            return await self._execute_with_cache(
                "classify_comment",
                self._perform_classification,
                cache_enabled=use_cache,
                comment_text=comment_text
            )
        except Exception as e:
            self.logger.error(
                "Failed to classify comment",
                extra_fields={
                    "error": str(e),
                    "comment_length": len(comment_text),
                    "use_cache": use_cache
                }
            )
            raise handle_llm_error(e)
    
    async def _perform_classification(self, comment_text: str) -> Dict[str, Any]:
        """Perform the actual classification with retry logic"""
        return await self._execute_with_retry(
            "llm_classification",
            self._classify_with_llm,
            comment_text
        )
    
    async def _classify_with_llm(self, comment_text: str) -> Dict[str, Any]:
        """Core LLM classification logic"""
        start_time = time.time()
        
        try:
            # Input sanitization and validation
            sanitized_text = self._sanitize_input(comment_text)
            
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
                self.logger.warning(
                    "Comment text truncated for classification",
                    extra_fields={"original_length": len(comment_text)}
                )
            
            # Generate prompt
            prompt = self.classification_prompt.format(comment_text=sanitized_text)
            
            # Execute LLM call with timeout
            with TimedOperation(self.logger, "llm_api_call"):
                try:
                    response = await asyncio.wait_for(
                        self.llm.agenerate([[HumanMessage(content=prompt)]]),
                        timeout=self.timeout_seconds
                    )
                except asyncio.TimeoutError:
                    raise ClassificationTimeoutError(
                        f"Classification timed out after {self.timeout_seconds} seconds"
                    )
            
            result_text = response.generations[0][0].text.strip()
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Parse and validate result
            classification_result = await self._parse_and_validate_result(
                result_text, 
                sanitized_text,
                processing_time_ms
            )
            
            self.logger.info(
                "Comment classified successfully",
                extra_fields={
                    "classification": classification_result["classification"],
                    "confidence": classification_result["confidence"],
                    "processing_time_ms": processing_time_ms
                }
            )
            
            return classification_result
            
        except (ClassificationTimeoutError, ClassificationError):
            raise
        except Exception as e:
            processing_time_ms = int((time.time() - start_time) * 1000)
            self.logger.error(
                "LLM classification failed",
                extra_fields={
                    "error": str(e),
                    "processing_time_ms": processing_time_ms
                }
            )
            raise ClassificationServiceError(f"LLM classification failed: {str(e)}")
    
    async def _parse_and_validate_result(
        self, 
        result_text: str, 
        original_text: str,
        processing_time_ms: int
    ) -> Dict[str, Any]:
        """Parse and validate LLM result"""
        try:
            import json
            
            # Attempt JSON parsing
            json_result = json.loads(result_text)
            
            # Validate with Pydantic model
            classification_result = ClassificationResult(**json_result)
            
            return {
                "classification": classification_result.classification,
                "confidence": classification_result.confidence,
                "contains_question": classification_result.contains_question,
                "sentiment_score": classification_result.sentiment_score,
                "toxicity_score": classification_result.toxicity_score,
                "reasoning": classification_result.reasoning,
                "llm_raw_response": result_text,
                "processing_time_ms": processing_time_ms,
                "error": None
            }
            
        except (json.JSONDecodeError, ValueError) as json_error:
            self.logger.warning(
                "JSON parsing failed, attempting manual parsing",
                extra_fields={"json_error": str(json_error)}
            )
            return self._parse_classification_result(result_text, original_text, processing_time_ms)
        except Exception as e:
            self.logger.error(
                "Result validation failed",
                extra_fields={"error": str(e)}
            )
            return self._create_error_response(str(e), processing_time_ms)
    
    def _sanitize_input(self, text: str) -> str:
        """Basic text sanitization"""
        import html
        sanitized = html.escape(text)
        sanitized = ' '.join(sanitized.split())
        return sanitized
    
    def _parse_classification_result(
        self, 
        result: str, 
        original_text: str, 
        processing_time_ms: int = 0
    ) -> Dict[str, Any]:
        """Fallback parsing for non-JSON LLM results"""
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
                classification = "spam / irrelevant"  # Default fallback
                confidence = 30
            
            # Additional analysis
            contains_question = self._detect_question(original_text)
            sentiment_score = self._estimate_sentiment(classification, confidence)
            toxicity_score = self._estimate_toxicity(classification, confidence)
            
            self.logger.warning(
                "Used fallback parsing for classification result",
                extra_fields={
                    "classification": classification,
                    "confidence": confidence
                }
            )
            
            return {
                "classification": classification,
                "confidence": confidence,
                "contains_question": contains_question,
                "sentiment_score": sentiment_score,
                "toxicity_score": toxicity_score,
                "reasoning": f"Manual parsing: {classification} with {confidence}% confidence",
                "llm_raw_response": result,
                "processing_time_ms": processing_time_ms,
                "error": None
            }
            
        except Exception as e:
            self.logger.error(
                "Fallback parsing failed",
                extra_fields={"error": str(e)}
            )
            return self._create_error_response(f"Parse error: {e}", processing_time_ms)
    
    def _create_error_response(self, error_message: str, processing_time_ms: int = 0) -> Dict[str, Any]:
        """Create standardized error response"""
        return {
            "classification": "spam / irrelevant",  # Safe default
            "confidence": 0,
            "contains_question": False,
            "sentiment_score": 0,
            "toxicity_score": 0,
            "reasoning": f"Error occurred: {error_message}",
            "llm_raw_response": None,
            "processing_time_ms": processing_time_ms,
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
        """Estimate toxicity score based on classification"""
        if classification in ['critical feedback', 'urgent issue / complaint']:
            return min(100, confidence + 20)
        elif classification == 'spam / irrelevant':
            return 60
        return 0
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Perform health check by testing classification"""
        try:
            # Test with a simple comment
            test_result = await self._classify_with_llm("Hello, great product!")
            
            return {
                "api_accessible": True,
                "model": settings.openai.model,
                "test_classification": test_result.get("classification"),
                "test_confidence": test_result.get("confidence"),
                "cache_size": len(self._cache),
                "service_stats": self.stats
            }
        except Exception as e:
            return {
                "api_accessible": False,
                "error": str(e),
                "cache_size": len(self._cache),
                "service_stats": self.stats
            }
    
    async def batch_classify(
        self, 
        comments: list[str], 
        use_cache: bool = True,
        max_concurrent: int = 5
    ) -> list[Dict[str, Any]]:
        """
        Classify multiple comments concurrently
        
        Args:
            comments: List of comment texts to classify
            use_cache: Whether to use caching
            max_concurrent: Maximum concurrent classifications
            
        Returns:
            List of classification results
        """
        if not comments:
            return []
        
        self.logger.info(
            f"Starting batch classification of {len(comments)} comments",
            extra_fields={"batch_size": len(comments), "max_concurrent": max_concurrent}
        )
        
        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def classify_with_semaphore(comment_text: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    return await self.classify_comment(comment_text, use_cache=use_cache)
                except Exception as e:
                    self.logger.error(
                        "Batch classification item failed",
                        extra_fields={"error": str(e), "comment_length": len(comment_text)}
                    )
                    return self._create_error_response(str(e))
        
        # Execute all classifications concurrently
        start_time = time.time()
        results = await asyncio.gather(
            *[classify_with_semaphore(comment) for comment in comments],
            return_exceptions=False
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        # Count successes and failures
        successful = sum(1 for result in results if not result.get("error"))
        failed = len(results) - successful
        
        self.logger.info(
            f"Batch classification completed",
            extra_fields={
                "total": len(comments),
                "successful": successful,
                "failed": failed,
                "processing_time_ms": processing_time_ms
            }
        )
        
        return results
    
    def get_classification_stats(self) -> Dict[str, Any]:
        """Get detailed service statistics"""
        base_stats = self.stats
        
        return {
            **base_stats,
            "cache_stats": {
                "size": len(self._cache),
                "hit_rate": getattr(self, "_cache_hits", 0) / max(self._request_count, 1)
            },
            "model_config": {
                "model": settings.openai.model,
                "temperature": 0.1,
                "max_tokens": 500,
                "timeout_seconds": self.timeout_seconds
            }
        }
    
    def clear_cache(self) -> None:
        """Clear classification cache"""
        self._clear_cache()
        self.logger.info("Classification cache cleared manually")