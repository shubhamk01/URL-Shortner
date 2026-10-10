import pytest
from fastapi.testclient import TestClient

from agentic_engineer.api.app import create_app
from agentic_engineer.url_shortener.repository import URLRepository
from agentic_engineer.url_shortener.service import URLShortenerService


@pytest.fixture()
def client(tmp_path):
    repo = URLRepository(str(tmp_path / "api.db"))
    service = URLShortenerService(repo, allowed_schemes=("http", "https"))
    app = create_app(service=service)
    return TestClient(app)


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_url(client):
    resp = client.post("/api/urls", json={"original_url": "https://example.com/a"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["original_url"] == "https://example.com/a"
    assert len(body["code"]) == 7


def test_create_url_rejects_bad_scheme(client):
    resp = client.post("/api/urls", json={"original_url": "javascript:alert(1)"})
    assert resp.status_code == 400


def test_get_metadata_unknown_code_404(client):
    resp = client.get("/api/urls/doesnotexist")
    assert resp.status_code == 404


def test_redirect_follows_to_original_url(client):
    created = client.post("/api/urls", json={"original_url": "https://example.com/target"}).json()
    resp = client.get(f"/r/{created['code']}", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example.com/target"


def test_redirect_unknown_code_404(client):
    resp = client.get("/r/missing1", follow_redirects=False)
    assert resp.status_code == 404


def test_analytics_counts_after_redirect(client):
    created = client.post("/api/urls", json={"original_url": "https://example.com/analytics"}).json()
    client.get(f"/r/{created['code']}", follow_redirects=False)
    client.get(f"/r/{created['code']}", follow_redirects=False)
    analytics = client.get(f"/api/urls/{created['code']}/analytics").json()
    assert analytics["click_count"] == 2
