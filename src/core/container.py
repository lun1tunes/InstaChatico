"""
Dependency Injection Container.

Centralizes all dependency configuration following the Dependency Inversion Principle.
This makes the application more testable and maintainable.
"""

from dependency_injector import containers, providers

# Services
from .services.classification_service import CommentClassificationService
from .services.answer_service import QuestionAnswerService
from .services.instagram_service import InstagramGraphAPIService
from .services.media_service import MediaService
from .services.media_analysis_service import MediaAnalysisService
from .services.embedding_service import EmbeddingService
from .services.telegram_alert_service import TelegramAlertService
from .services.s3_service import S3Service
from .services.document_processing_service import DocumentProcessingService
from .services.document_context_service import DocumentContextService

# Infrastructure
from .infrastructure.task_queue import CeleryTaskQueue
from .celery_app import celery_app

# Use cases
from .use_cases.classify_comment import ClassifyCommentUseCase
from .use_cases.generate_answer import GenerateAnswerUseCase
from .use_cases.send_reply import SendReplyUseCase
from .use_cases.hide_comment import HideCommentUseCase
from .use_cases.process_webhook_comment import ProcessWebhookCommentUseCase
from .use_cases.send_telegram_notification import SendTelegramNotificationUseCase
from .use_cases.process_media import ProcessMediaUseCase, AnalyzeMediaUseCase
from .use_cases.process_document import ProcessDocumentUseCase
from .use_cases.test_comment_processing import TestCommentProcessingUseCase


class Container(containers.DeclarativeContainer):
    """
    Application DI container.

    Provides centralized configuration for all dependencies.
    Services are created as singletons or factories as appropriate.
    """

    # Configuration
    config = providers.Configuration()

    # Infrastructure - Singleton
    task_queue = providers.Singleton(
        CeleryTaskQueue,
        celery_app=celery_app,
    )

    # Services - Factory (new instance each time, allows different configs)
    classification_service = providers.Factory(
        CommentClassificationService,
    )

    answer_service = providers.Factory(
        QuestionAnswerService,
    )

    instagram_service = providers.Factory(
        InstagramGraphAPIService,
    )

    media_service = providers.Factory(
        MediaService,
        instagram_service=instagram_service,
        task_queue=task_queue,
    )

    embedding_service = providers.Factory(
        EmbeddingService,
    )

    telegram_service = providers.Factory(
        TelegramAlertService,
    )

    media_analysis_service = providers.Factory(
        MediaAnalysisService,
    )

    s3_service = providers.Singleton(
        S3Service,
    )

    document_processing_service = providers.Singleton(
        DocumentProcessingService,
    )

    document_context_service = providers.Singleton(
        DocumentContextService,
    )

    # Use Cases - Factory (new instance per request)
    # Note: session is provided at call time via Depends()

    classify_comment_use_case = providers.Factory(
        ClassifyCommentUseCase,
        # session is injected at runtime
        classification_service=classification_service,
        media_service=media_service,
    )

    generate_answer_use_case = providers.Factory(
        GenerateAnswerUseCase,
        # session is injected at runtime
        qa_service=answer_service,
    )

    send_reply_use_case = providers.Factory(
        SendReplyUseCase,
        # session is injected at runtime
        instagram_service=instagram_service,
    )

    hide_comment_use_case = providers.Factory(
        HideCommentUseCase,
        # session is injected at runtime
        instagram_service=instagram_service,
    )

    process_webhook_comment_use_case = providers.Factory(
        ProcessWebhookCommentUseCase,
        # session is injected at runtime
        media_service=media_service,
        task_queue=task_queue,
    )

    send_telegram_notification_use_case = providers.Factory(
        SendTelegramNotificationUseCase,
        # session is injected at runtime
        telegram_service=telegram_service,
    )

    process_media_use_case = providers.Factory(
        ProcessMediaUseCase,
        # session is injected at runtime
        media_service=media_service,
        analysis_service=media_analysis_service,
    )

    analyze_media_use_case = providers.Factory(
        AnalyzeMediaUseCase,
        # session is injected at runtime
        analysis_service=media_analysis_service,
    )

    process_document_use_case = providers.Factory(
        ProcessDocumentUseCase,
        # session is injected at runtime
        s3_service=s3_service,
        doc_processing_service=document_processing_service,
    )

    test_comment_processing_use_case = providers.Factory(
        TestCommentProcessingUseCase,
        # session is injected at runtime
        # Optional use cases will use container if not provided
    )


# Global container instance
container = Container()


def get_container() -> Container:
    """
    Get the global container instance.

    Used as a FastAPI dependency:
        container: Container = Depends(get_container)
    """
    return container


def reset_container():
    """
    Reset container for testing.

    Clears all singletons and allows fresh initialization.
    """
    container.reset_singletons()
