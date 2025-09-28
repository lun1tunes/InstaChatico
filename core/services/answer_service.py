import time
import os
import logging
from typing import Any, Dict, Optional
from pathlib import Path

from agents import Runner, SQLiteSession
from ..config import settings
from ..agents import comment_response_agent, get_comment_response_agent

comment_response_agent = get_comment_response_agent()
logger = logging.getLogger(__name__)

class QuestionAnswerService:
    def __init__(self, api_key: str = None, db_path: str = "conversations/conversations.db"):
        self.api_key = api_key or settings.openai.api_key
        self.response_agent = comment_response_agent
        self.db_path = db_path
        self._ensure_db_directory()
    
    def _ensure_db_directory(self):
        """Ensure the directory for the conversations database exists"""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Conversations database will be stored at: {self.db_path}")
    
    def _get_session(self, conversation_id: str) -> SQLiteSession:
        """
        Get or create a SQLiteSession for the given conversation ID
        
        Args:
            conversation_id: Unique identifier for the conversation (first question comment ID)
            
        Returns:
            SQLiteSession instance for the conversation
        """
        logger.debug(f"Creating/retrieving SQLiteSession for conversation_id: {conversation_id}")
        logger.debug(f"Session database path: {self.db_path}")
        session = SQLiteSession(conversation_id, self.db_path)
        logger.debug(f"SQLiteSession created successfully for conversation: {conversation_id}")
        return session
    
    async def generate_answer(self, question_text: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Generate an answer for a customer question"""
        start_time = time.time()
        
        try:
            # Sanitize input
            sanitized_text = self._sanitize_input(question_text)
            
            if len(sanitized_text) > 1000:
                sanitized_text = sanitized_text[:1000] + "..."
            
            # Use session if conversation_id is provided
            if conversation_id:
                logger.debug(f"Starting answer generation with persistent session for conversation_id: {conversation_id}")
                # Use SQLiteSession for persistent conversation
                session = self._get_session(conversation_id)
                result = await Runner.run(self.response_agent, input=sanitized_text, session=session)
                logger.info(f"Answer generated successfully using SQLiteSession for conversation: {conversation_id}")
            else:
                logger.debug("Starting answer generation without session (stateless mode)")
                # Use regular Runner without session
                result = await Runner.run(self.response_agent, input=sanitized_text)
                logger.info("Answer generated successfully without session")
            answer_result = result.final_output
            
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            return {
                'answer': answer_result.answer,
                'confidence': answer_result.confidence,
                'quality_score': answer_result.quality_score,
                'tokens_used': self._estimate_tokens(sanitized_text + answer_result.answer),
                'processing_time_ms': processing_time_ms,
                'llm_raw_response': str(result),  # Convert result to string since raw_output might not exist
                'conversation_id': conversation_id,
                'session_used': conversation_id is not None,
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
    
    def get_conversation_history(self, conversation_id: str) -> list:
        """
        Get the conversation history for a given conversation ID
        
        Note: SQLiteSession from OpenAI Agents SDK doesn't expose conversation history directly.
        The session is used internally by the agent for context, but we can't access the history.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            Empty list (conversation history is handled internally by the agent)
        """
        # SQLiteSession from OpenAI Agents SDK doesn't expose conversation history
        # The session is used internally by the agent for context management
        logger.debug(f"Conversation history is managed internally by SQLiteSession for: {conversation_id}")
        return []
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """
        Clear the conversation history for a given conversation ID
        
        Note: SQLiteSession from OpenAI Agents SDK manages conversation history internally.
        We cannot directly clear the history, but the session will be recreated for new conversations.
        
        Args:
            conversation_id: The conversation ID to clear
            
        Returns:
            True (session management is handled internally by the agent)
        """
        # SQLiteSession from OpenAI Agents SDK manages conversation history internally
        # We cannot directly clear the history, but the session will be recreated for new conversations
        logger.debug(f"Conversation history is managed internally by SQLiteSession for: {conversation_id}")
        return True
    
    def get_session_info(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get information about a session
        
        Note: SQLiteSession from OpenAI Agents SDK manages conversation history internally.
        We can only provide basic session information.
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            Dictionary with session information
        """
        try:
            logger.debug(f"Getting session information for conversation_id: {conversation_id}")
            session = self._get_session(conversation_id)
            
            # SQLiteSession from OpenAI Agents SDK manages conversation history internally
            # We can only provide basic session information
            session_info = {
                'conversation_id': conversation_id,
                'db_path': self.db_path,
                'session_exists': True,
                'history_count': 0,  # Cannot access history count directly
                'note': 'Conversation history is managed internally by SQLiteSession'
            }
            logger.debug(f"Session info retrieved for conversation: {conversation_id}")
            return session_info
        except Exception as e:
            logger.error(f"Error getting session info for {conversation_id}: {e}")
            return {
                'conversation_id': conversation_id,
                'db_path': self.db_path,
                'session_exists': False,
                'error': str(e)
            }
