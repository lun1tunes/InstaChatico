from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.instagram_comment import InstagramComment
from ..models.comment_classification import CommentClassification, ProcessingStatus


COMPLAINT_LABEL = "urgent issue / complaint"


class ModerationStatsRepository:
    """Repository responsible for aggregating moderation metrics."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def gather_metrics(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        summary = await self._build_summary(range_start, range_end)
        violations = await self._build_violation_breakdown(range_start, range_end)
        ai_moderator = await self._build_ai_moderator_stats(range_start, range_end)
        return {
            "summary": summary,
            "violations": violations,
            "ai_moderator": ai_moderator,
        }

    async def _build_summary(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        total_verified = await self._count_verified(range_start, range_end)
        complaints_total = await self._count_complaints(range_start, range_end, processed_only=False)
        complaints_processed = await self._count_complaints(range_start, range_end, processed_only=True)
        reaction_time = await self._average_reaction_time(range_start, range_end)

        return {
            "total_verified_content": total_verified,
            "complaints_total": complaints_total,
            "complaints_processed": complaints_processed,
            "average_reaction_time_seconds": reaction_time,
        }

    async def _build_violation_breakdown(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        stmt = (
            select(CommentClassification.type, func.count().label("count"))
            .join(InstagramComment, InstagramComment.id == CommentClassification.comment_id)
            .where(
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                CommentClassification.processing_completed_at.isnot(None),
                CommentClassification.processing_completed_at >= range_start,
                CommentClassification.processing_completed_at < range_end,
            )
            .group_by(CommentClassification.type)
        )
        result = await self.session.execute(stmt)
        category_counts = defaultdict(int)
        other_examples: list[str] = []

        for label, count in result.all():
            normalized_label = (label or "").strip().lower()
            if normalized_label == COMPLAINT_LABEL:
                continue
            category = _categorize_violation(label)
            category_counts[category] += count or 0
            if category == "other" and label:
                normalized = label.strip()
                if normalized and normalized not in other_examples:
                    other_examples.append(normalized)

        return {
            "spam_advertising": category_counts["spam_advertising"],
            "adult_content": category_counts["adult_content"],
            "insults_toxicity": category_counts["insults_toxicity"],
            "other": {
                "count": category_counts["other"],
                "examples": other_examples[:3],
            },
        }

    async def _build_ai_moderator_stats(self, range_start: datetime, range_end: datetime) -> dict[str, Any]:
        deleted_stmt = select(func.count()).where(
            InstagramComment.deleted_at.isnot(None),
            InstagramComment.deleted_at >= range_start,
            InstagramComment.deleted_at < range_end,
        )
        hidden_stmt = select(func.count()).where(
            InstagramComment.hidden_at.isnot(None),
            InstagramComment.hidden_at >= range_start,
            InstagramComment.hidden_at < range_end,
        )

        deleted_count = (await self.session.execute(deleted_stmt)).scalar() or 0
        hidden_count = (await self.session.execute(hidden_stmt)).scalar() or 0

        return {
            "deleted_content": deleted_count,
            "hidden_comments": hidden_count,
        }

    async def _count_verified(self, range_start: datetime, range_end: datetime) -> int:
        stmt = select(func.count()).where(
            CommentClassification.processing_status == ProcessingStatus.COMPLETED,
            CommentClassification.processing_completed_at.isnot(None),
            CommentClassification.processing_completed_at >= range_start,
            CommentClassification.processing_completed_at < range_end,
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _count_complaints(self, range_start: datetime, range_end: datetime, *, processed_only: bool) -> int:
        stmt = (
            select(func.count())
            .select_from(CommentClassification)
            .join(InstagramComment, InstagramComment.id == CommentClassification.comment_id)
            .where(
                CommentClassification.type.isnot(None),
                func.lower(CommentClassification.type) == COMPLAINT_LABEL,
            )
        )

        if processed_only:
            stmt = stmt.where(
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                CommentClassification.processing_completed_at.isnot(None),
                CommentClassification.processing_completed_at >= range_start,
                CommentClassification.processing_completed_at < range_end,
            )
        else:
            stmt = stmt.where(
                InstagramComment.created_at >= range_start,
                InstagramComment.created_at < range_end,
            )

        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def _average_reaction_time(self, range_start: datetime, range_end: datetime) -> float | None:
        stmt = (
            select(
                CommentClassification.processing_completed_at,
                InstagramComment.created_at,
            )
            .join(InstagramComment, InstagramComment.id == CommentClassification.comment_id)
            .where(
                CommentClassification.processing_status == ProcessingStatus.COMPLETED,
                CommentClassification.processing_completed_at.isnot(None),
                CommentClassification.processing_completed_at >= range_start,
                CommentClassification.processing_completed_at < range_end,
            )
        )
        rows = await self.session.execute(stmt)
        durations = []
        for completed_at, created_at in rows.all():
            if completed_at and created_at:
                durations.append((completed_at - created_at).total_seconds())
        if not durations:
            return None
        return sum(durations) / len(durations)


def _categorize_violation(label: str | None) -> str:
    normalized = (label or "").strip().lower()
    if not normalized:
        return "other"
    if "spam" in normalized or "advert" in normalized:
        return "spam_advertising"
    if "18" in normalized or "adult" in normalized or "nsfw" in normalized:
        return "adult_content"
    if "toxic" in normalized or "abusive" in normalized or "insult" in normalized or "harass" in normalized:
        return "insults_toxicity"
    return "other"
