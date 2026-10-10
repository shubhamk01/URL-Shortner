import pytest

from agentic_engineer.url_shortener.repository import URLRepository


@pytest.fixture()
def repo(tmp_path):
    return URLRepository(str(tmp_path / "test.db"))


def test_insert_and_get_by_code(repo):
    record = repo.insert("abc1234", "https://example.com", expires_at=None)
    fetched = repo.get_by_code("abc1234")
    assert fetched is not None
    assert fetched.original_url == "https://example.com"
    assert fetched.is_active is True
    assert fetched.id == record.id


def test_get_by_code_unknown_returns_none(repo):
    assert repo.get_by_code("missing") is None


def test_insert_duplicate_code_raises(repo):
    repo.insert("dupe123", "https://example.com", expires_at=None)
    with pytest.raises(ValueError):
        repo.insert("dupe123", "https://other.com", expires_at=None)


def test_record_click_and_count(repo):
    repo.insert("clk1234", "https://example.com", expires_at=None)
    repo.record_click("clk1234", referrer="https://ref.com", user_agent="pytest-agent")
    repo.record_click("clk1234", referrer=None, user_agent=None)
    assert repo.count_clicks("clk1234") == 2
    recent = repo.recent_clicks("clk1234")
    assert len(recent) == 2
