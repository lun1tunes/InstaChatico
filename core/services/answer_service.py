import asyncio
import time
from typing import Dict, Any, Optional
from langchain.prompts import PromptTemplate
from langchain_community.chat_models import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
import logging
from ..config import settings

logger = logging.getLogger(__name__)

class QuestionAnswerService:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or settings.openai.api_key
        self.llm = ChatOpenAI(
            openai_api_key=self.api_key,
            model=settings.openai.model,
            temperature=0.3,  # Slightly higher for more creative answers
            max_tokens=500,   # Longer responses for answers
            streaming=False
        )
        
        self.system_prompt = """I am an AI agent that helps business customers answer questions in Instagram post comments about their business. 

My role is to:
- Provide helpful, accurate, and professional answers to customer questions
- Be friendly and engaging while maintaining professionalism
- Address specific concerns about products, services, pricing, availability, etc.
- Offer solutions and next steps when appropriate
- Keep responses concise but informative

Guidelines:
- Always be helpful and solution-oriented
- If I don't have specific information, I'll suggest how the customer can get it
- I'll maintain a positive, professional tone
- I'll avoid making promises I can't keep
- I'll focus on being genuinely helpful rather than just promotional"""

        self.answer_prompt = PromptTemplate(
            input_variables=["question_text"],
            template="""
Based on the customer's question below, provide a helpful and professional answer that a business owner would give to their Instagram followers.

Question: {question_text}

Please provide:
1. A direct answer to their question
2. Any relevant additional information that might be helpful
3. Clear next steps if applicable

Keep your response conversational but professional, as if responding directly to a customer on Instagram.
"""
        )
    
    async def generate_answer(self, question_text: str) -> Dict[str, Any]:
        """Generate an answer for a customer question"""
        start_time = time.time()
        
        try:
            # Sanitize input
            sanitized_text = self._sanitize_input(question_text)
            
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
            
            # Create messages
            system_message = SystemMessage(content=self.system_prompt)
            prompt = self.answer_prompt.format(question_text=sanitized_text)
            human_message = HumanMessage(content=prompt)
            
            # Generate answer
            response = await self.llm.agenerate([[system_message, human_message]])
            answer_text = response.generations[0][0].text.strip()
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # Calculate confidence and quality scores
            confidence_score = self._calculate_confidence_score(answer_text, question_text)
            quality_score = self._calculate_quality_score(answer_text, question_text)
            
            return {
                'answer': answer_text,
                'confidence': confidence_score,
                'quality_score': quality_score,
                'tokens_used': self._estimate_tokens(prompt + answer_text),
                'processing_time_ms': processing_time_ms,
                'meta_data': {
                    'question_length': len(question_text),
                    'answer_length': len(answer_text),
                    'model_used': settings.openai.model,
                    'temperature': 0.3
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
    
    def _calculate_confidence_score(self, answer: str, question: str) -> float:
        """Calculate confidence score based on answer quality indicators"""
        score = 0.5  # Base score
        
        # Length indicators
        if 50 <= len(answer) <= 300:
            score += 0.1  # Good length
        elif len(answer) < 20:
            score -= 0.2  # Too short
        elif len(answer) > 500:
            score -= 0.1  # Too long
        
        # Content indicators
        if any(word in answer.lower() for word in ['please', 'thank you', 'help', 'assist']):
            score += 0.1  # Professional tone
        
        if any(word in answer.lower() for word in ['contact', 'email', 'phone', 'visit', 'website']):
            score += 0.1  # Provides contact info
        
        if any(word in answer.lower() for word in ['sorry', 'unfortunately', 'cannot', 'unable']):
            score -= 0.1  # Negative indicators
        
        # Question-answer relevance (simple keyword matching)
        question_words = set(question.lower().split())
        answer_words = set(answer.lower().split())
        overlap = len(question_words.intersection(answer_words))
        if overlap > 0:
            score += min(0.2, overlap * 0.05)
        
        return max(0.0, min(1.0, score))
    
    def _calculate_quality_score(self, answer: str, question: str) -> int:
        """Calculate quality score (0-100) based on various factors"""
        score = 50  # Base score
        
        # Length appropriateness
        if 50 <= len(answer) <= 300:
            score += 20
        elif 20 <= len(answer) < 50:
            score += 10
        elif len(answer) > 500:
            score -= 10
        
        # Professional indicators
        professional_words = ['please', 'thank you', 'help', 'assist', 'welcome', 'glad']
        if any(word in answer.lower() for word in professional_words):
            score += 15
        
        # Action-oriented indicators
        action_words = ['contact', 'visit', 'call', 'email', 'check', 'available']
        if any(word in answer.lower() for word in action_words):
            score += 10
        
        # Avoid negative indicators
        negative_words = ['sorry', 'unfortunately', 'cannot', 'unable', 'no']
        negative_count = sum(1 for word in negative_words if word in answer.lower())
        score -= negative_count * 5
        
        # Completeness indicators
        if '?' in answer:  # Answer contains questions (might indicate uncertainty)
            score -= 5
        
        return max(0, min(100, score))
    
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
