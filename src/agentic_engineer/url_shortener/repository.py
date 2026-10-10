"""SQLite-backed repository for the URL shortener.

A narrow repository interface is used so the storage engine can be swapped
(e.g. for Postgres) without touching the service layer.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

from .models import ClickEvent, ShortURL

_SCHEMA = """
CREATE TABLE IF NOT EXISTS short_urls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    original_url TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS click_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL,
    clicked_at TEXT NOT NULL,
    referrer TEXT,
    user_agent TEXT,
    FOREIGN KEY (code) REFERENCES short_urls(code)
);

CREATE INDEX IF NOT EXISTS idx_click_events_code ON click_events(code);
"""


def _to_iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if dt else None


def _from_iso(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


class URLRepository:
    """Thin, parameterized-query-only data access layer. No string-built SQL."""

    def __init__(self, database_path: str):
        self._database_path = database_path
        path = Path(database_path)
        if path.parent and str(path.parent) not in (".", ""):
            path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._database_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _cursor(self) -> Iterator[sqlite3.Cursor]:
        conn = self._connect()
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._cursor() as cur:
            cur.executescript(_SCHEMA)

    def code_exists(self, code: str) -> bool:
        with self._cursor() as cur:
            cur.execute("SELECT 1 FROM short_urls WHERE code = ?", (code,))
            return cur.fetchone() is not None

    def insert(self, code: str, original_url: str, expires_at: Optional[datetime]) -> ShortURL:
        created_at = datetime.now(timezone.utc)
        with self._cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO short_urls (code, original_url, created_at, expires_at, is_active) "
                    "VALUES (?, ?, ?, ?, 1)",
                    (code, original_url, _to_iso(created_at), _to_iso(expires_at)),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"code already exists: {code}") from exc
            row_id = cur.lastrowid
        return ShortURL(
            id=row_id,
            code=code,
            original_url=original_url,
            created_at=created_at,
            expires_at=expires_at,
            is_active=True,
        )

    def get_by_code(self, code: str) -> Optional[ShortURL]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, code, original_url, created_at, expires_at, is_active "
                "FROM short_urls WHERE code = ?",
                (code,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        return ShortURL(
            id=row["id"],
            code=row["code"],
            original_url=row["original_url"],
            created_at=_from_iso(row["created_at"]),
            expires_at=_from_iso(row["expires_at"]),
            is_active=bool(row["is_active"]),
        )

    def record_click(self, code: str, referrer: Optional[str], user_agent: Optional[str]) -> ClickEvent:
        clicked_at = datetime.now(timezone.utc)
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO click_events (code, clicked_at, referrer, user_agent) VALUES (?, ?, ?, ?)",
                (code, _to_iso(clicked_at), referrer, user_agent),
            )
            row_id = cur.lastrowid
        return ClickEvent(id=row_id, code=code, clicked_at=clicked_at, referrer=referrer, user_agent=user_agent)

    def count_clicks(self, code: str) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM click_events WHERE code = ?", (code,))
            return int(cur.fetchone()["n"])

    def recent_clicks(self, code: str, limit: int = 20) -> list[ClickEvent]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, code, clicked_at, referrer, user_agent FROM click_events "
                "WHERE code = ? ORDER BY clicked_at DESC LIMIT ?",
                (code, limit),
            )
            rows = cur.fetchall()
        return [
            ClickEvent(
                id=row["id"],
                code=row["code"],
                clicked_at=_from_iso(row["clicked_at"]),
                referrer=row["referrer"],
                user_agent=row["user_agent"],
            )
            for row in rows
        ]
