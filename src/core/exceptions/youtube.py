"""YouTube-related domain exceptions."""

from __future__ import annotations


class MissingYouTubeAuth(Exception):
    """Raised when no valid YouTube OAuth tokens are available."""


class QuotaExceeded(Exception):
    """Raised when YouTube Data API quota is exhausted."""

