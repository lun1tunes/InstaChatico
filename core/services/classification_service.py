import logging
from typing import Any, Dict

from agents import Runner

from ..agents import comment_classification_agent
from ..config import settings

logger = logging.getLogger(__name__)

class CommentClassificationService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.openai.api_key
        
        # Use the singleton agent instance from the agents module
        # This ensures we reuse the same agent instance across all service instances
        self.classification_agent = comment_classification_agent
    
    async def classify_comment(self, comment_text: str) -> Dict[str, Any]:
        """Asynchronous comment classification using OpenAI Agents SDK"""
        try:
            # Input sanitization
            sanitized_text = self._sanitize_input(comment_text)
            
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
                logger.warning(f"Comment truncated to 1000 characters: {comment_text[:50]}...")
            
            logger.info(f"Classifying comment: {sanitized_text[:100]}...")
            
            # Use Runner.run() for async execution
            result = await Runner.run(
                self.classification_agent, 
                input=sanitized_text
            )
            
            # Extract the final output from the result
            classification_result = result.final_output
            
            logger.info(f"Classification result: {classification_result.classification} (confidence: {classification_result.confidence})")
            
            return {
                "classification": classification_result.classification,
                "confidence": classification_result.confidence,
                "contains_question": classification_result.contains_question,
                "sentiment_score": classification_result.sentiment_score,
                "toxicity_score": classification_result.toxicity_score,
                "reasoning": classification_result.reasoning,
                "llm_raw_response": str(classification_result),
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Classification error: {e}")
            import traceback
            logger.error(f"Traceback: {traceback.format_exc()}")
            return self._create_error_response(str(e))
    
    def _sanitize_input(self, text: str) -> str:
        """Enhanced text sanitization"""
        import html
        import re

        # Basic HTML escaping
        sanitized = html.escape(text)
        
        # Remove excessive whitespace
        sanitized = ' '.join(sanitized.split())
        
        # Remove excessive punctuation (more than 3 consecutive)
        sanitized = re.sub(r'([!?.]){3,}', r'\1\1\1', sanitized)
        
        # Remove excessive emojis (more than 5 consecutive)
        emoji_pattern = r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251]+'
        emojis = re.findall(emoji_pattern, sanitized)
        if len(emojis) > 5:
            sanitized = re.sub(emoji_pattern, lambda m: m.group()[:5], sanitized)
        
        return sanitized
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response with fallback classification"""
        return {
            "classification": "spam / irrelevant",  # Safe fallback
            "confidence": 0,
            "contains_question": False,
            "sentiment_score": 0,
            "toxicity_score": 0,
            "reasoning": f"Classification failed: {error_message}",
            "llm_raw_response": None,
            "error": error_message
        }
    
    def _detect_question(self, text: str) -> bool:
        """Enhanced question detection for multiple languages"""
        question_indicators = [
            # English
            '?', 'what', 'how', 'when', 'where', 'why', 'who', 'which', 'can', 'could', 'would', 'should',
            # Russian
            'как', 'что', 'где', 'когда', 'почему', 'зачем', 'кто', 'какой', 'можете', 'можно',
            # Spanish
            'qué', 'cómo', 'cuándo', 'dónde', 'por qué', 'quién', 'cuál', 'puede', 'puedo',
            # French
            'quoi', 'comment', 'quand', 'où', 'pourquoi', 'qui', 'peut', 'peux',
            # German
            'was', 'wie', 'wann', 'wo', 'warum', 'wer', 'kann', 'können'
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in question_indicators)
    
    def _estimate_sentiment(self, classification: str, confidence: int) -> int:
        """Enhanced sentiment estimation based on classification"""
        sentiment_map = {
            'positive feedback': confidence,
            'critical feedback': -confidence,
            'urgent issue / complaint': -confidence - 20,  # More negative for urgent issues
            'question / inquiry': 0,  # Neutral for questions
            'spam / irrelevant': -50,
            'unknown': 0
        }
        return max(-100, min(100, sentiment_map.get(classification, 0)))
    
    def _estimate_toxicity(self, classification: str, confidence: int) -> int:
        """Enhanced toxicity estimation"""
        if classification in ['critical feedback', 'urgent issue / complaint']:
            return min(100, confidence + 20)
        elif classification == 'spam / irrelevant':
            return 60
        elif classification == 'positive feedback':
            return 0
        return 10  # Low toxicity for questions