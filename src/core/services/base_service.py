"""Base service class with common functionality."""

import html
import logging
import re
import sqlite3
from pathlib import Path

from agents import SQLiteSession

logger = logging.getLogger(__name__)


class BaseService:
    """Base class providing common service functionality."""

    def __init__(self, db_path: str = "conversations/conversations.db"):
        self.db_path = db_path
        self._ensure_db_directory()

    def _ensure_db_directory(self):
        """Create database directory if needed."""
        db_dir = Path(self.db_path).parent
        db_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sanitize_input(text: str) -> str:
        """Sanitize text: escape HTML, normalize whitespace, limit punctuation."""
        sanitized = html.escape(text)
        sanitized = " ".join(sanitized.split())
        sanitized = re.sub(r"([!?.]){3,}", r"\1\1\1", sanitized)
        return sanitized

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """Estimate token count (~4 chars per token)."""
        return len(text) // 4

    def _get_session(self, conversation_id: str) -> SQLiteSession:
        """Retrieve session with conversation history."""
        logger.debug(f"Retrieving session for conversation: {conversation_id}")
        return SQLiteSession(conversation_id, self.db_path)

    async def _session_has_messages(self, conversation_id: str) -> bool:
        """Check if session has existing messages in database."""
        try:
            db_path = Path(self.db_path)
            if not db_path.exists():
                return False

            with sqlite3.connect(str(db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT COUNT(*) FROM agent_messages WHERE session_id = ?",
                    (conversation_id,),
                )
                count = cursor.fetchone()[0]
                return count > 0

        except Exception as e:
            logger.warning(f"Error checking session: {e}")
            return False
