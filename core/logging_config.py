"""
Centralized logging configuration for InstaChatico application.
Provides structured logging with consistent formatting across all modules.
"""

import logging
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
import json
from enum import Enum


class LogLevel(str, Enum):
    """Enumeration for log levels"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class StructuredFormatter(logging.Formatter):
    """Custom formatter for structured logging with JSON output"""
    
    def format(self, record: logging.LogRecord) -> str:
        # Create base log entry
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields if present
        if hasattr(record, 'extra_fields'):
            log_entry.update(record.extra_fields)
        
        # Add component-specific fields
        if hasattr(record, 'component'):
            log_entry["component"] = record.component
            
        if hasattr(record, 'operation'):
            log_entry["operation"] = record.operation
            
        if hasattr(record, 'comment_id'):
            log_entry["comment_id"] = record.comment_id
            
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
            
        if hasattr(record, 'processing_time_ms'):
            log_entry["processing_time_ms"] = record.processing_time_ms
        
        return json.dumps(log_entry, ensure_ascii=False)


class InstaChaticLogger:
    """Centralized logger factory for InstaChatico application"""
    
    _loggers: Dict[str, logging.Logger] = {}
    _configured = False
    
    @classmethod
    def configure(
        cls,
        log_level: str = "INFO",
        log_format: str = "structured",
        log_file: Optional[str] = None
    ) -> None:
        """Configure global logging settings"""
        if cls._configured:
            return
            
        # Set up root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, log_level.upper()))
        
        # Clear existing handlers
        root_logger.handlers.clear()
        
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper()))
        
        if log_format == "structured":
            formatter = StructuredFormatter()
        else:
            formatter = logging.Formatter(
                fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # Add file handler if specified
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(getattr(logging, log_level.upper()))
            file_handler.setFormatter(formatter)
            root_logger.addHandler(file_handler)
        
        # Configure third-party loggers
        logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
        logging.getLogger("celery").setLevel(logging.INFO)
        logging.getLogger("aiohttp").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        
        cls._configured = True
    
    @classmethod
    def get_logger(
        cls,
        name: str,
        component: Optional[str] = None
    ) -> "ComponentLogger":
        """Get a logger instance for a specific component"""
        if name in cls._loggers:
            logger = cls._loggers[name]
        else:
            logger = logging.getLogger(name)
            cls._loggers[name] = logger
        
        return ComponentLogger(logger, component or name)


class ComponentLogger:
    """Enhanced logger with component-specific context"""
    
    def __init__(self, logger: logging.Logger, component: str):
        self._logger = logger
        self.component = component
    
    def _log(
        self,
        level: int,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Internal logging method with structured data"""
        extra = {
            'component': self.component,
            'extra_fields': extra_fields or {}
        }
        
        # Add common context fields
        for key, value in kwargs.items():
            extra[key] = value
        
        self._logger.log(level, message, extra=extra)
    
    def debug(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Log debug message"""
        self._log(logging.DEBUG, message, extra_fields, **kwargs)
    
    def info(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Log info message"""
        self._log(logging.INFO, message, extra_fields, **kwargs)
    
    def warning(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Log warning message"""
        self._log(logging.WARNING, message, extra_fields, **kwargs)
    
    def error(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Log error message"""
        self._log(logging.ERROR, message, extra_fields, **kwargs)
    
    def critical(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Log critical message"""
        self._log(logging.CRITICAL, message, extra_fields, **kwargs)
    
    def exception(
        self,
        message: str,
        extra_fields: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> None:
        """Log exception with traceback"""
        extra = {
            'component': self.component,
            'extra_fields': extra_fields or {}
        }
        
        for key, value in kwargs.items():
            extra[key] = value
            
        self._logger.exception(message, extra=extra)
    
    # Context-specific logging methods
    def log_webhook_received(
        self,
        comment_id: str,
        user_id: str,
        media_id: str,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log webhook reception"""
        self.info(
            f"Webhook received for comment {comment_id}",
            extra_fields=extra_fields,
            comment_id=comment_id,
            user_id=user_id,
            media_id=media_id,
            operation="webhook_received"
        )
    
    def log_classification_started(
        self,
        comment_id: str,
        comment_text: str,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log classification start"""
        self.info(
            f"Starting classification for comment {comment_id}",
            extra_fields=extra_fields,
            comment_id=comment_id,
            comment_length=len(comment_text),
            operation="classification_started"
        )
    
    def log_classification_completed(
        self,
        comment_id: str,
        classification: str,
        confidence: int,
        processing_time_ms: int,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log classification completion"""
        self.info(
            f"Classification completed for comment {comment_id}: {classification} ({confidence}%)",
            extra_fields=extra_fields,
            comment_id=comment_id,
            classification=classification,
            confidence=confidence,
            processing_time_ms=processing_time_ms,
            operation="classification_completed"
        )
    
    def log_answer_generation_started(
        self,
        comment_id: str,
        question_text: str,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log answer generation start"""
        self.info(
            f"Starting answer generation for comment {comment_id}",
            extra_fields=extra_fields,
            comment_id=comment_id,
            question_length=len(question_text),
            operation="answer_generation_started"
        )
    
    def log_answer_generation_completed(
        self,
        comment_id: str,
        answer_length: int,
        confidence: int,
        processing_time_ms: int,
        tokens_used: int,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log answer generation completion"""
        self.info(
            f"Answer generated for comment {comment_id}: {answer_length} chars, {confidence}% confidence",
            extra_fields=extra_fields,
            comment_id=comment_id,
            answer_length=answer_length,
            confidence=confidence,
            processing_time_ms=processing_time_ms,
            tokens_used=tokens_used,
            operation="answer_generation_completed"
        )
    
    def log_instagram_reply_sent(
        self,
        comment_id: str,
        reply_id: str,
        processing_time_ms: int,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log Instagram reply sent"""
        self.info(
            f"Instagram reply sent for comment {comment_id}, reply_id: {reply_id}",
            extra_fields=extra_fields,
            comment_id=comment_id,
            reply_id=reply_id,
            processing_time_ms=processing_time_ms,
            operation="instagram_reply_sent"
        )
    
    def log_processing_error(
        self,
        comment_id: str,
        operation: str,
        error_message: str,
        retry_count: int = 0,
        extra_fields: Optional[Dict[str, Any]] = None
    ) -> None:
        """Log processing error"""
        self.error(
            f"Error in {operation} for comment {comment_id}: {error_message}",
            extra_fields=extra_fields,
            comment_id=comment_id,
            operation=operation,
            error_message=error_message,
            retry_count=retry_count
        )


# Global logger instances for easy access
def get_logger(name: str, component: Optional[str] = None) -> ComponentLogger:
    """Get a logger instance - convenience function"""
    return InstaChaticLogger.get_logger(name, component)


# Initialize logging configuration
def setup_logging(
    log_level: str = "INFO",
    log_format: str = "structured",
    log_file: Optional[str] = None
) -> None:
    """Setup logging configuration - call this at application startup"""
    InstaChaticLogger.configure(log_level, log_format, log_file)
