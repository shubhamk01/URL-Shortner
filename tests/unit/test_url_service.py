import pytest

from agentic_engineer.url_shortener.models import (
    CodeGenerationError,
    CodeGoneError,
    CodeNotFoundError,
    InvalidURLError,
)
from agentic_engineer.url_shortener.repository import URLRepository
from agentic_engineer.url_shortener.service import URLShortenerService


@pytest.fixture()
def service(tmp_path):
    repo = URLRepository(str(tmp_path / "svc.db"))
    return URLShortenerService(repo, allowed_schemes=("http", "https"))


def test_validate_url_rejects_disallowed_scheme(service):
    with pytest.raises(InvalidURLError):
        service.validate_url("javascript:alert(1)")


def test_validate_url_rejects_missing_host(service):
    with pytest.raises(InvalidURLError):
        service.validate_url("https://")


def test_validate_url_accepts_http_and_https(service):
    assert service.validate_url("https://example.com/path") == "https://example.com/path"
    assert service.validate_url("http://example.com") == "http://example.com"


def test_create_and_resolve_short_url(service):
    record = service.create_short_url("https://example.com/page")
    resolved = service.resolve_target(record.code)
    assert resolved.original_url == "https://example.com/page"


def test_resolve_target_unknown_code_raises(service):
    with pytest.raises(CodeNotFoundError):
        service.resolve_target("doesnotexist")


def test_resolve_target_expired_raises_gone(service):
    from datetime import datetime, timedelta, timezone

    past = datetime.now(timezone.utc) - timedelta(days=1)
    record = service.create_short_url("https://example.com/expired", expires_at=past)
    with pytest.raises(CodeGoneError):
        service.resolve_target(record.code)


def test_record_click_failure_does_not_raise(service, monkeypatch):
    record = service.create_short_url("https://example.com/click")

    def boom(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(service._repo, "record_click", boom)
    result = service.record_click(record.code, referrer=None, user_agent=None)
    assert result is None  # degrades gracefully, never raises


def test_create_short_url_collision_generation_error(service, monkeypatch):
    monkeypatch.setattr(service._repo, "code_exists", lambda code: True)
    with pytest.raises(CodeGenerationError):
        service.create_short_url("https://example.com/collide")


def test_get_analytics_counts_clicks(service):
    record = service.create_short_url("https://example.com/analytics")
    service.record_click(record.code, referrer="https://ref.com", user_agent="ua")
    data = service.get_analytics(record.code)
    assert data["click_count"] == 1
    assert data["code"] == record.code
