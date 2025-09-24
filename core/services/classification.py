"""
Simplified and enhanced comment classification service using Pydantic v2.
"""

import asyncio
import time
import json
from typing import Dict, Any, Optional, List
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage
from pydantic import BaseModel, Field, ConfigDict

from ..config import settings
from ..exceptions import ClassificationError, ClassificationServiceError, handle_llm_error
from .enhanced_base import EnhancedService


class ClassificationResult(BaseModel):
    """Pydantic v2 model for classification results"""
    
    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra='forbid'
    )
    
    classification: str = Field(
        description="Classification category",
        pattern="^(positive feedback|critical feedback|urgent issue / complaint|question / inquiry|spam / irrelevant)$"
    )
    confidence: int = Field(ge=0, le=100, description="Confidence score 0-100")
    reasoning: str = Field(min_length=1, description="Brief explanation")
    contains_question: bool = Field(description="Whether comment contains a question")
    sentiment_score: int = Field(ge=-100, le=100, description="Sentiment score -100 to 100")
    toxicity_score: int = Field(ge=0, le=100, description="Toxicity score 0-100")


class CommentClassificationService(EnhancedService):
    """Simplified comment classification service"""
    
    def __init__(self, api_key: Optional[str] = None):
        super().__init__("classification", max_retries=2, cache_ttl=3600)
        
        self.api_key = api_key or settings.openai.api_key
        if not self.api_key:
            raise ClassificationServiceError("OpenAI API key is required")
        
        self.llm = ChatOpenAI(
            openai_api_key=self.api_key,
            model=settings.openai.model,
            temperature=0.1,
            max_tokens=500,
            request_timeout=30
        )
        
        self.prompt = PromptTemplate(
            input_variables=["comment_text"],
            template="""
            Classify this Instagram comment into exactly one category:

            Categories:
            1. positive feedback - Praise, thanks, recommendations
            2. critical feedback - Constructive criticism without urgency  
            3. urgent issue / complaint - Problems requiring immediate attention
            4. question / inquiry - Business-related questions only
            5. spam / irrelevant - Off-topic, promotional, or irrelevant content

            Comment: {comment_text}

            Respond with valid JSON:
            {{
                "classification": "category name",
                "confidence": 85,
                "reasoning": "Brief explanation in same language as comment",
                "contains_question": true/false,
                "sentiment_score": -50 to 100,
                "toxicity_score": 0 to 100
            }}
            """
        )
    
    async def classify_comment(self, comment_text: str, use_cache: bool = True) -> Dict[str, Any]:
        """Classify a comment with caching and retry logic"""
        if not comment_text or not comment_text.strip():
            raise ClassificationError("Comment text cannot be empty")
        
        # Check cache first
        cache_key = f"classify_{hash(comment_text.strip())}"
        if use_cache:
            cached = self._get_from_cache(cache_key)
            if cached:
                return cached
        
        # Execute with retry
        result = await self.execute_with_retry(
            "classify_comment",
            self._perform_classification,
            comment_text
        )
        
        # Cache result
        if use_cache and not result.get("error"):
            self._set_cache(cache_key, result)
        
        return result
    
    async def _perform_classification(self, comment_text: str) -> Dict[str, Any]:
        """Core classification logic"""
        start_time = time.time()
        
        try:
            # Sanitize and truncate input
            sanitized_text = self._sanitize_input(comment_text)
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
            
            # Generate prompt and call LLM
            prompt = self.prompt.format(comment_text=sanitized_text)
            
            response = await asyncio.wait_for(
                self.llm.agenerate([[HumanMessage(content=prompt)]]),
                timeout=30
            )
            
            result_text = response.generations[0][0].text.strip()
            processing_time = int((time.time() - start_time) * 1000)
            
            # Parse and validate result
            return await self._parse_result(result_text, sanitized_text, processing_time)
            
        except asyncio.TimeoutError:
            raise ClassificationServiceError("Classification timed out")
        except Exception as e:
            processing_time = int((time.time() - start_time) * 1000)
            self.logger.error("Classification failed", extra_fields={"error": str(e)})
            return self._create_error_response(str(e), processing_time)
    
    async def _parse_result(self, result_text: str, original_text: str, processing_time: int) -> Dict[str, Any]:
        """Parse and validate LLM result"""
        try:
            # Try JSON parsing first
            json_result = json.loads(result_text)
            classification_result = ClassificationResult(**json_result)
            
            return {
                "classification": classification_result.classification,
                "confidence": classification_result.confidence,
                "contains_question": classification_result.contains_question,
                "sentiment_score": classification_result.sentiment_score,
                "toxicity_score": classification_result.toxicity_score,
                "reasoning": classification_result.reasoning,
                "processing_time_ms": processing_time,
                "error": None
            }
            
        except (json.JSONDecodeError, ValueError) as e:
            self.logger.warning("JSON parsing failed, using fallback", extra_fields={"error": str(e)})
            return self._fallback_parse(result_text, original_text, processing_time)
    
    def _fallback_parse(self, result: str, original_text: str, processing_time: int) -> Dict[str, Any]:
        """Fallback parsing for non-JSON results"""
        # Simple fallback logic
        classification = "spam / irrelevant"  # Safe default
        confidence = 30
        
        # Basic keyword matching
        text_lower = result.lower()
        if "positive" in text_lower:
            classification = "positive feedback"
            confidence = 70
        elif "question" in text_lower:
            classification = "question / inquiry"
            confidence = 70
        elif "critical" in text_lower:
            classification = "critical feedback"
            confidence = 70
        elif "urgent" in text_lower or "complaint" in text_lower:
            classification = "urgent issue / complaint"
            confidence = 70
        
        return {
            "classification": classification,
            "confidence": confidence,
            "contains_question": self._detect_question(original_text),
            "sentiment_score": self._estimate_sentiment(classification),
            "toxicity_score": self._estimate_toxicity(classification),
            "reasoning": f"Fallback parsing: {classification}",
            "processing_time_ms": processing_time,
            "error": None
        }
    
    def _create_error_response(self, error_message: str, processing_time: int = 0) -> Dict[str, Any]:
        """Create error response"""
        return {
            "classification": "spam / irrelevant",  # Safe default
            "confidence": 0,
            "contains_question": False,
            "sentiment_score": 0,
            "toxicity_score": 0,
            "reasoning": f"Error: {error_message}",
            "processing_time_ms": processing_time,
            "error": error_message
        }
    
    def _sanitize_input(self, text: str) -> str:
        """Basic input sanitization"""
        import html
        sanitized = html.escape(text)
        return ' '.join(sanitized.split())
    
    def _detect_question(self, text: str) -> bool:
        """Simple question detection"""
        indicators = ['?', 'how', 'what', 'where', 'when', 'why', 'who', 'как', 'что', 'где']
        return any(indicator in text.lower() for indicator in indicators)
    
    def _estimate_sentiment(self, classification: str) -> int:
        """Estimate sentiment from classification"""
        sentiment_map = {
            'positive feedback': 80,
            'critical feedback': -40,
            'urgent issue / complaint': -70,
            'question / inquiry': 0,
            'spam / irrelevant': -20
        }
        return sentiment_map.get(classification, 0)
    
    def _estimate_toxicity(self, classification: str) -> int:
        """Estimate toxicity from classification"""
        if classification in ['critical feedback', 'urgent issue / complaint']:
            return 40
        elif classification == 'spam / irrelevant':
            return 60
        return 10
    
    async def _perform_health_check(self) -> Dict[str, Any]:
        """Health check implementation"""
        try:
            test_result = await self._perform_classification("Test comment")
            return {
                "api_accessible": True,
                "test_classification": test_result.get("classification"),
                "cache_size": len(self._cache)
            }
        except Exception as e:
            return {"api_accessible": False, "error": str(e)}
    
    async def batch_classify(self, comments: List[str], max_concurrent: int = 5) -> List[Dict[str, Any]]:
        """Classify multiple comments concurrently"""
        if not comments:
            return []
        
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def classify_one(text: str) -> Dict[str, Any]:
            async with semaphore:
                try:
                    return await self.classify_comment(text)
                except Exception as e:
                    return self._create_error_response(str(e))
        
        results = await asyncio.gather(*[classify_one(comment) for comment in comments])
        
        successful = sum(1 for r in results if not r.get("error"))
        self.logger.info(f"Batch classification: {successful}/{len(comments)} successful")
        
        return results
