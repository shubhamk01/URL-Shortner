"""Domain models for the URL shortener."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ShortURL:
    id: int
    code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    is_active: bool = True

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        if self.expires_at is None:
            return False
        return (now or utcnow()) >= self.expires_at


@dataclass
class ClickEvent:
    id: int
    code: str
    clicked_at: datetime
    referrer: Optional[str] = None
    user_agent: Optional[str] = None


class URLShortenerError(Exception):
    """Base class for domain errors raised by the URL shortener service."""


class InvalidURLError(URLShortenerError):
    """Raised when the destination URL is malformed or uses a disallowed scheme."""


class CodeNotFoundError(URLShortenerError):
    """Raised when a short code does not exist."""


class CodeGoneError(URLShortenerError):
    """Raised when a short code exists but is inactive or expired."""


class CodeGenerationError(URLShortenerError):
    """Raised when a unique short code could not be generated within the attempt budget."""
