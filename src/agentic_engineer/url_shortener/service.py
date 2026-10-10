"""Business logic for the URL shortener, independent of the web framework."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

from .codegen import generate_code
from .models import (
    ClickEvent,
    CodeGenerationError,
    CodeGoneError,
    CodeNotFoundError,
    InvalidURLError,
    ShortURL,
)
from .repository import URLRepository

logger = logging.getLogger(__name__)


class URLShortenerService:
    def __init__(
        self,
        repository: URLRepository,
        allowed_schemes: tuple[str, ...] = ("http", "https"),
        code_length: int = 7,
        max_collision_attempts: int = 5,
    ):
        self._repo = repository
        self._allowed_schemes = {s.lower() for s in allowed_schemes}
        self._code_length = code_length
        self._max_collision_attempts = max_collision_attempts

    def validate_url(self, url: str) -> str:
        """Rejects malformed URLs and disallowed schemes (open-redirect guardrail)."""
        if not url or not url.strip():
            raise InvalidURLError("original_url must not be empty")
        parsed = urlparse(url.strip())
        if parsed.scheme.lower() not in self._allowed_schemes:
            raise InvalidURLError(
                f"scheme '{parsed.scheme or '<none>'}' is not allowed; "
                f"allowed schemes: {sorted(self._allowed_schemes)}"
            )
        if not parsed.netloc:
            raise InvalidURLError("original_url must include a network location (host)")
        return url.strip()

    def create_short_url(self, original_url: str, expires_at: Optional[datetime] = None) -> ShortURL:
        validated = self.validate_url(original_url)
        for _ in range(self._max_collision_attempts):
            code = generate_code(self._code_length)
            if self._repo.code_exists(code):
                continue  # collision: draw again rather than failing the request
            return self._repo.insert(code=code, original_url=validated, expires_at=expires_at)
        raise CodeGenerationError(
            f"could not generate a unique code after {self._max_collision_attempts} attempts"
        )

    def get_short_url(self, code: str) -> ShortURL:
        record = self._repo.get_by_code(code)
        if record is None:
            raise CodeNotFoundError(f"unknown code: {code}")
        return record

    def resolve_target(self, code: str) -> ShortURL:
        """Returns the record to redirect to, enforcing active/expiry rules."""
        record = self.get_short_url(code)
        if not record.is_active or record.is_expired():
            raise CodeGoneError(f"code is no longer active: {code}")
        return record

    def record_click(self, code: str, referrer: Optional[str], user_agent: Optional[str]) -> Optional[ClickEvent]:
        """Best-effort analytics write: failures here must never corrupt redirect/URL data."""
        try:
            return self._repo.record_click(code=code, referrer=referrer, user_agent=user_agent)
        except Exception:  # noqa: BLE001 - analytics must degrade gracefully
            logger.exception("failed to record click event for code=%s", code)
            return None

    def get_analytics(self, code: str) -> dict:
        self.get_short_url(code)  # raises CodeNotFoundError if unknown
        return {
            "code": code,
            "click_count": self._repo.count_clicks(code),
            "recent_clicks": [
                {
                    "clicked_at": event.clicked_at.isoformat(),
                    "referrer": event.referrer,
                }
                for event in self._repo.recent_clicks(code)
            ],
        }
