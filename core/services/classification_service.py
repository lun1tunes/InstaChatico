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
    
    async def _get_session_with_media_context(self, conversation_id: str, media_context: Optional[Dict[str, Any]] = None) -> SQLiteSession:
        """
        Get or create a SQLiteSession with media context for the given conversation ID

        Args:
            conversation_id: Unique identifier for the conversation (first question comment ID)
            media_context: Media information to inject into session context

        Returns:
            SQLiteSession instance with media context
        """
        logger.debug(f"Creating/retrieving SQLiteSession with media context for conversation_id: {conversation_id}")
        logger.debug(f"Session database path: {self.db_path}")
        session = SQLiteSession(conversation_id, self.db_path)

        # Inject media context into session if available
        if media_context:
            await self._inject_media_context_to_session(session, media_context)
        
        logger.debug(f"SQLiteSession with media context created successfully for conversation: {conversation_id}")
        return session
    
    async def _inject_media_context_to_session(self, session: SQLiteSession, media_context: Dict[str, Any]) -> None:
        """
        Inject media context into the session for AI agents

        Args:
            session: SQLiteSession instance
            media_context: Media information dictionary
        """
        try:
            # Create a comprehensive media description
            media_description = self._create_media_description(media_context)

            # Add media context as a system message to the session
            # This will be available to the AI agent throughout the conversation
            await session.add_items([{
                "role": "system",
                "content": f"MEDIA CONTEXT: {media_description}"
            }])

            logger.debug(f"Injected media context into session: {media_description[:100]}...")

        except Exception as e:
            logger.warning(f"Failed to inject media context into session: {e}")
    
    def _create_media_description(self, media_context: Dict[str, Any]) -> str:
        """
        Create a comprehensive media description from context
        
        Args:
            media_context: Media information dictionary
            
        Returns:
            Formatted media description string
        """
        description_parts = []
        
        # Basic media info
        if media_context.get('media_type'):
            description_parts.append(f"Post Type: {media_context['media_type']}")
        
        if media_context.get('username'):
            description_parts.append(f"Author: @{media_context['username']}")
        
        # Post content
        if media_context.get('caption'):
            caption = media_context['caption']
            # Truncate long captions but keep important info
            if len(caption) > 500:
                caption = caption[:500] + "..."
            description_parts.append(f"Post Caption: {caption}")
        
        if media_context.get('media_url'):
            description_parts.append(f"Media URL: {media_context['media_url']}")
        
        # Engagement metrics
        engagement_parts = []
        if media_context.get('comments_count') is not None:
            engagement_parts.append(f"{media_context['comments_count']} comments")
        if media_context.get('like_count') is not None:
            engagement_parts.append(f"{media_context['like_count']} likes")
        
        if engagement_parts:
            description_parts.append(f"Engagement: {', '.join(engagement_parts)}")
        
        # Additional context
        if media_context.get('is_comment_enabled') is not None:
            status = "enabled" if media_context['is_comment_enabled'] else "disabled"
            description_parts.append(f"Comments: {status}")
        
        if media_context.get('permalink'):
            description_parts.append(f"Post URL: {media_context['permalink']}")
        
        return "\n".join(description_parts)
    
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
    
    async def classify_comment(self, comment_text: str, conversation_id: Optional[str] = None, media_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Asynchronous comment classification using OpenAI Agents SDK"""
        try:
            # Format input with conversation and media context
            formatted_input = self._format_input_with_context(comment_text, conversation_id, media_context)
            
            if len(formatted_input) > 2000:  # Increased limit for context
                formatted_input = formatted_input[:2000] + "..."
                logger.warning(f"Input truncated to 2000 characters: {comment_text[:50]}...")
            
            logger.info(f"Classifying comment with context: {formatted_input[:200]}...")
            
            # Use session if conversation_id is provided
            if conversation_id:
                logger.debug(f"Starting classification with persistent session for conversation_id: {conversation_id}")
                # Use SQLiteSession with media context for persistent conversation
                session = await self._get_session_with_media_context(conversation_id, media_context)
                result = await Runner.run(
                    self.classification_agent,
                    input=formatted_input,
                    session=session
                )
                logger.info(f"Classification completed using SQLiteSession with media context for conversation: {conversation_id}")
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
    
    def _format_input_with_context(self, comment_text: str, conversation_id: Optional[str] = None, media_context: Optional[Dict[str, Any]] = None) -> str:
        """
        Format the input text with conversation and media context
        
        Args:
            comment_text: The comment text to classify
            conversation_id: Optional conversation ID for context
            media_context: Optional media information for richer context
            
        Returns:
            Formatted text with context information
        """
        sanitized_text = self._sanitize_input(comment_text)
        
        # Build context information
        context_parts = []
        
        # Add media context if available
        if media_context:
            media_info = []
            if media_context.get('caption'):
                media_info.append(f"Post caption: {media_context['caption'][:200]}...")
            if media_context.get('media_type'):
                media_info.append(f"Post type: {media_context['media_type']}")
            if media_context.get('username'):
                media_info.append(f"Post author: @{media_context['username']}")
            if media_context.get('comments_count') is not None:
                media_info.append(f"Post has {media_context['comments_count']} comments")
            if media_context.get('like_count') is not None:
                media_info.append(f"Post has {media_context['like_count']} likes")
            
            if media_info:
                context_parts.append("Media context:")
                context_parts.extend(media_info)
        
        # Add conversation context if available
        if conversation_id:
            context_parts.append(f"Conversation ID: {conversation_id}")
        
        # Combine all context
        if context_parts:
            context_text = "\n".join(context_parts)
            formatted_input = f"{context_text}\n\nComment to classify: {sanitized_text}"
            logger.debug(f"Formatted input with context: {formatted_input[:200]}...")
            return formatted_input
        
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