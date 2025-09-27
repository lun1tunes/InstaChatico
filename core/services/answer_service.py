import time
from typing import Any, Dict
import logging  
from agents import Runner
from ..config import settings
from ..agents import comment_response_agent, get_comment_response_agent
comment_response_agent = get_comment_response_agent()
logger = logging.getLogger(__name__)

class QuestionAnswerService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.openai.api_key
        self.response_agent = comment_response_agent
    
    async def generate_answer(self, question_text: str) -> Dict[str, Any]:
        """Generate an answer for a customer question"""
        start_time = time.time()
        
        try:
            # Sanitize input
            sanitized_text = self._sanitize_input(question_text)
            
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
            
            # Use the Agents SDK to generate the answer
            result = await Runner.run(self.response_agent, input=sanitized_text)
            answer_result = result.final_output
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                'answer': answer_result.answer,
                'confidence': answer_result.confidence,
                'quality_score': answer_result.quality_score,
                'tokens_used': self._estimate_tokens(sanitized_text + answer_result.answer),
                'processing_time_ms': processing_time_ms,
                'llm_raw_response': str(result),  # Convert result to string since raw_output might not exist
                'meta_data': {
                    'question_length': len(question_text),
                    'answer_length': len(answer_result.answer),
                    'model_used': settings.openai.model_comment_response,
                    'reasoning': answer_result.reasoning,
                    'is_helpful': answer_result.is_helpful,
                    'contains_contact_info': answer_result.contains_contact_info,
                    'tone': answer_result.tone
                }
            }
            
        except Exception as e:
            logger.error(f"Answer generation error: {e}")
            return self._create_error_response(str(e))
    
    def _sanitize_input(self, text: str) -> str:
        """Sanitize input text"""
        import html
        sanitized = html.escape(text)
        sanitized = ' '.join(sanitized.split())
        return sanitized
    
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of token count (4 chars ≈ 1 token)"""
        return len(text) // 4
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response"""
        return {
            'answer': None,
            'confidence': 0.0,
            'quality_score': 0,
            'tokens_used': 0,
            'processing_time_ms': 0,
            'error': error_message,
            'meta_data': {'error': True}
        }
