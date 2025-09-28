import logging
from typing import Any, Dict, Optional

from agents import Runner, SQLiteSession

from ..agents import comment_classification_agent
from ..config import settings

logger = logging.getLogger(__name__)

class CommentClassificationService:
    def __init__(self, api_key: str = None, db_path: str = "conversations/conversations.db"):
        self.api_key = api_key or settings.openai.api_key
        self.db_path = db_path
        
        # Use the singleton agent instance from the agents module
        # This ensures we reuse the same agent instance across all service instances
        self.classification_agent = comment_classification_agent
    
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
    
    def _generate_conversation_id(self, comment_id: str, parent_id: Optional[str] = None) -> str:
        """
        Generate conversation ID based on comment hierarchy
        
        Args:
            comment_id: Current comment ID
            parent_id: Parent comment ID if this is a reply
            
        Returns:
            Conversation ID in format first_question_comment_{id}
        """
        if parent_id:
            # If this is a reply, use the parent's conversation ID
            return f"first_question_comment_{parent_id}"
        else:
            # If this is a top-level comment, use its own ID
            return f"first_question_comment_{comment_id}"
    
    async def classify_comment(self, comment_text: str, conversation_id: Optional[str] = None) -> Dict[str, Any]:
        """Asynchronous comment classification using OpenAI Agents SDK"""
        try:
            # Format input with conversation context
            formatted_input = self._format_input_with_context(comment_text, conversation_id)
            
            if len(formatted_input) > 2000:  # Increased limit for context
                formatted_input = formatted_input[:2000] + "..."
                logger.warning(f"Input truncated to 2000 characters: {comment_text[:50]}...")
            
            logger.info(f"Classifying comment with context: {formatted_input[:200]}...")
            
            # Use session if conversation_id is provided
            if conversation_id:
                logger.debug(f"Starting classification with persistent session for conversation_id: {conversation_id}")
                # Use SQLiteSession for persistent conversation
                session = self._get_session(conversation_id)
                result = await Runner.run(
                    self.classification_agent, 
                    input=formatted_input,
                    session=session
                )
                logger.info(f"Classification completed using SQLiteSession for conversation: {conversation_id}")
            else:
                logger.debug("Starting classification without session (stateless mode)")
                # Use regular Runner without session
                result = await Runner.run(
                    self.classification_agent, 
                    input=formatted_input
                )
                logger.info("Classification completed without session")
            
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
                "context_used": classification_result.context_used,
                "conversation_continuity": classification_result.conversation_continuity,
                "llm_raw_response": str(classification_result),
                "conversation_id": conversation_id,
                "session_used": conversation_id is not None,
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
    
    def _format_input_with_context(self, comment_text: str, conversation_id: Optional[str] = None) -> str:
        """
        Format the input text with conversation context if available
        
        Args:
            comment_text: The comment text to classify
            conversation_id: Optional conversation ID for context
            
        Returns:
            Formatted input string with context
        """
        sanitized_text = self._sanitize_input(comment_text)
        
        if conversation_id:
            try:
                # Get conversation history
                session = self._get_session(conversation_id)
                history = self.get_conversation_history(conversation_id)
                
                if history:
                    # Format context for the agent
                    context_lines = []
                    context_lines.append("CONVERSATION CONTEXT:")
                    context_lines.append("Previous messages in this conversation:")
                    
                    for i, message in enumerate(history[-5:], 1):  # Last 5 messages
                        context_lines.append(f"{i}. {message}")
                    
                    context_lines.append("")
                    context_lines.append("CURRENT COMMENT TO CLASSIFY:")
                    context_lines.append(sanitized_text)
                    
                    formatted_input = "\n".join(context_lines)
                    logger.debug(f"Formatted input with context for conversation {conversation_id}")
                    return formatted_input
                else:
                    logger.debug(f"No conversation history found for {conversation_id}")
            except Exception as e:
                logger.warning(f"Failed to get conversation context for {conversation_id}: {e}")
        
        # Return sanitized text without context
        return sanitized_text
    
    def _create_error_response(self, error_message: str) -> Dict[str, Any]:
        """Create error response with fallback classification"""
        return {
            "classification": "spam / irrelevant",  # Safe fallback
            "confidence": 0,
            "contains_question": False,
            "sentiment_score": 0,
            "toxicity_score": 0,
            "reasoning": f"Classification failed: {error_message}",
            "context_used": False,
            "conversation_continuity": False,
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
    
    def get_conversation_history(self, conversation_id: str) -> list:
        """
        Get the conversation history for a given conversation ID
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            List of conversation messages
        """
        try:
            logger.info(f"Retrieving conversation history for conversation_id: {conversation_id}")
            session = self._get_session(conversation_id)
            # SQLiteSession should provide access to conversation history
            # This depends on the specific implementation of SQLiteSession
            if hasattr(session, 'get_messages'):
                history = session.get_messages()
                logger.info(f"Retrieved {len(history)} messages from conversation: {conversation_id}")
                return history
            elif hasattr(session, 'messages'):
                history = session.messages
                logger.info(f"Retrieved {len(history)} messages from conversation: {conversation_id}")
                return history
            else:
                logger.warning(f"SQLiteSession does not have get_messages or messages attribute for conversation: {conversation_id}")
                return []
        except Exception as e:
            logger.error(f"Error getting conversation history for {conversation_id}: {e}")
            return []
    
    def clear_conversation(self, conversation_id: str) -> bool:
        """
        Clear the conversation history for a given conversation ID
        
        Args:
            conversation_id: The conversation ID to clear
            
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info(f"Clearing conversation history for conversation_id: {conversation_id}")
            session = self._get_session(conversation_id)
            if hasattr(session, 'clear'):
                session.clear()
                logger.info(f"Successfully cleared conversation: {conversation_id}")
                return True
            else:
                logger.warning(f"SQLiteSession does not have clear method for conversation: {conversation_id}")
                return False
        except Exception as e:
            logger.error(f"Error clearing conversation {conversation_id}: {e}")
            return False
    
    def get_session_info(self, conversation_id: str) -> Dict[str, Any]:
        """
        Get information about a session
        
        Args:
            conversation_id: The conversation ID
            
        Returns:
            Dictionary with session information
        """
        try:
            logger.info(f"Getting session information for conversation_id: {conversation_id}")
            session = self._get_session(conversation_id)
            history_count = len(self.get_conversation_history(conversation_id))
            session_info = {
                'conversation_id': conversation_id,
                'db_path': self.db_path,
                'session_exists': True,
                'history_count': history_count
            }
            logger.info(f"Session info retrieved for conversation: {conversation_id} (history: {history_count} messages)")
            return session_info
        except Exception as e:
            logger.error(f"Error getting session info for {conversation_id}: {e}")
            return {
                'conversation_id': conversation_id,
                'db_path': self.db_path,
                'session_exists': False,
                'error': str(e)
            }