"""Pydantic request/response schemas and the FastAPI application for the URL shortener."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ..config import get_settings
from ..url_shortener.models import CodeGenerationError, CodeGoneError, CodeNotFoundError, InvalidURLError
from ..url_shortener.repository import URLRepository
from ..url_shortener.service import URLShortenerService


class CreateURLRequest(BaseModel):
    original_url: str = Field(..., min_length=1, max_length=4096)
    expires_at: Optional[datetime] = None


class ShortURLResponse(BaseModel):
    code: str
    original_url: str
    created_at: datetime
    expires_at: Optional[datetime]
    is_active: bool
    short_link: str


class AnalyticsResponse(BaseModel):
    code: str
    click_count: int
    recent_clicks: list[dict]


def _to_response(record, request: Request) -> ShortURLResponse:
    base = str(request.base_url).rstrip("/")
    return ShortURLResponse(
        code=record.code,
        original_url=record.original_url,
        created_at=record.created_at,
        expires_at=record.expires_at,
        is_active=record.is_active,
        short_link=f"{base}/r/{record.code}",
    )


def create_app(service: Optional[URLShortenerService] = None) -> FastAPI:
    settings = get_settings()
    if service is None:
        repo = URLRepository(settings.database_path)
        service = URLShortenerService(
            repository=repo,
            allowed_schemes=settings.allowed_url_schemes,
            code_length=settings.short_code_length,
            max_collision_attempts=settings.short_code_max_collision_attempts,
        )

    app = FastAPI(title="Agentic URL Shortener", version="0.1.0")
    app.state.service = service

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/urls", response_model=ShortURLResponse, status_code=201)
    def create_url(payload: CreateURLRequest, request: Request) -> ShortURLResponse:
        try:
            record = service.create_short_url(payload.original_url, expires_at=payload.expires_at)
        except InvalidURLError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except CodeGenerationError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        return _to_response(record, request)

    @app.get("/api/urls/{code}", response_model=ShortURLResponse)
    def get_url(code: str, request: Request) -> ShortURLResponse:
        try:
            record = service.get_short_url(code)
        except CodeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _to_response(record, request)

    @app.get("/api/urls/{code}/analytics", response_model=AnalyticsResponse)
    def get_analytics(code: str) -> AnalyticsResponse:
        try:
            data = service.get_analytics(code)
        except CodeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return AnalyticsResponse(**data)

    @app.get("/r/{code}")
    def redirect(code: str, request: Request, user_agent: Optional[str] = Header(default=None)):
        try:
            record = service.resolve_target(code)
        except CodeNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except CodeGoneError as exc:
            raise HTTPException(status_code=410, detail=str(exc)) from exc
        # Analytics failures must never break the redirect itself.
        service.record_click(code, referrer=request.headers.get("referer"), user_agent=user_agent)
        return RedirectResponse(url=record.original_url, status_code=307)

    return app


app = create_app()
