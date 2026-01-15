from __future__ import annotations

import logging
from typing import Callable, Iterable, Optional

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import (
    CommentClassification,
    FollowersDynamic,
    InstagramComment,
    InstrumentTokenUsage,
    Media,
    ModerationStatsReport,
    OAuthToken,
    QuestionAnswer,
    StatsReport,
)
from ..repositories.oauth_token import OAuthTokenRepository

logger = logging.getLogger(__name__)


def _normalize_ids(values: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    seen = set()
    for value in values:
        if not value:
            continue
        candidate = value.strip()
        if not candidate or candidate in seen:
            continue
        cleaned.append(candidate)
        seen.add(candidate)
    return cleaned


def _rowcount(result) -> int:
    count = result.rowcount
    if count is None or count < 0:
        return 0
    return int(count)


class DeleteAccountDataUseCase:
    """Delete all stored Instagram data for given account IDs or instagram_user_id."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        oauth_token_repository_factory: Callable[..., OAuthTokenRepository],
    ):
        self.session = session
        self.oauth_repo = oauth_token_repository_factory(session=session)

    async def execute(
        self,
        *,
        provider: str,
        account_ids: list[str],
        instagram_user_id: Optional[str],
    ) -> dict:
        normalized_accounts = set(_normalize_ids(account_ids))
        user_id = (instagram_user_id or "").strip() or None
        usernames: set[str] = set()

        if user_id:
            tokens = await self.oauth_repo.list_by_provider_instagram_user_id(provider, user_id)
            for token in tokens:
                if token.account_id:
                    normalized_accounts.add(token.account_id)
                if token.username:
                    usernames.add(token.username)

        if normalized_accounts:
            tokens = await self.oauth_repo.list_by_provider_accounts(provider, list(normalized_accounts))
            for token in tokens:
                if token.username:
                    usernames.add(token.username)

        deleted = {
            "oauth_tokens": 0,
            "instrument_token_usage": 0,
            "question_answers": 0,
            "comment_classifications": 0,
            "comments": 0,
            "media": 0,
            "followers_dynamic": 0,
            "stats_reports": 0,
            "moderation_stats_reports": 0,
        }

        try:
            token_filters = [OAuthToken.provider == provider]
            token_subfilters = []
            if normalized_accounts:
                token_subfilters.append(OAuthToken.account_id.in_(list(normalized_accounts)))
            if user_id:
                token_subfilters.append(OAuthToken.instagram_user_id == user_id)
            if token_subfilters:
                token_filters.append(or_(*token_subfilters))
                result = await self.session.execute(delete(OAuthToken).where(*token_filters))
                deleted["oauth_tokens"] = _rowcount(result)

            media_filters = [Media.platform == "instagram"]
            media_owner_filters = []
            if normalized_accounts:
                media_owner_filters.append(Media.owner.in_(list(normalized_accounts)))
            if usernames:
                media_owner_filters.append(Media.username.in_(list(usernames)))
            if media_owner_filters:
                media_filters.append(or_(*media_owner_filters))
                media_ids = select(Media.id).where(*media_filters)
                comment_ids = select(InstagramComment.id).where(
                    InstagramComment.platform == "instagram",
                    InstagramComment.media_id.in_(media_ids),
                )

                result = await self.session.execute(
                    delete(InstrumentTokenUsage).where(InstrumentTokenUsage.comment_id.in_(comment_ids))
                )
                deleted["instrument_token_usage"] = _rowcount(result)

                result = await self.session.execute(
                    delete(QuestionAnswer).where(QuestionAnswer.comment_id.in_(comment_ids))
                )
                deleted["question_answers"] = _rowcount(result)

                result = await self.session.execute(
                    delete(CommentClassification).where(CommentClassification.comment_id.in_(comment_ids))
                )
                deleted["comment_classifications"] = _rowcount(result)

                result = await self.session.execute(
                    delete(InstagramComment).where(
                        InstagramComment.platform == "instagram",
                        InstagramComment.media_id.in_(media_ids),
                    )
                )
                deleted["comments"] = _rowcount(result)

                result = await self.session.execute(delete(Media).where(Media.id.in_(media_ids)))
                deleted["media"] = _rowcount(result)

            if usernames:
                result = await self.session.execute(
                    delete(FollowersDynamic).where(FollowersDynamic.username.in_(list(usernames)))
                )
                deleted["followers_dynamic"] = _rowcount(result)
            elif normalized_accounts or user_id:
                # Followers stats are not account-scoped; clear all to honor deletion requests.
                result = await self.session.execute(delete(FollowersDynamic))
                deleted["followers_dynamic"] = _rowcount(result)

            if normalized_accounts or user_id:
                # Reports are not scoped per account; remove all Instagram aggregates.
                result = await self.session.execute(delete(StatsReport))
                deleted["stats_reports"] = _rowcount(result)
                result = await self.session.execute(delete(ModerationStatsReport))
                deleted["moderation_stats_reports"] = _rowcount(result)

            await self.session.commit()
        except Exception:
            await self.session.rollback()
            logger.exception(
                "Failed to delete account data | provider=%s | account_ids=%s | instagram_user_id=%s",
                provider,
                list(normalized_accounts),
                user_id,
            )
            raise

        return {
            "resolved_account_ids": sorted(normalized_accounts),
            "resolved_usernames": sorted(usernames),
            "deleted": deleted,
        }
