# API Reference — URL Shortener

Base URL when run locally: `http://127.0.0.1:8000`

## `GET /health`
Health check. Returns `{"status": "ok"}`.

## `POST /api/urls`
Create a short URL.

Request body:
```json
{ "original_url": "https://example.com/some/page", "expires_at": null }
```

Responses:
- `201 Created` — `{ "code", "original_url", "created_at", "expires_at", "is_active", "short_link" }`
- `400 Bad Request` — malformed URL or disallowed scheme (only `http`/`https` are permitted by default).
- `503 Service Unavailable` — a unique short code could not be generated within the configured collision-retry budget.

## `GET /r/{code}`
Redirects (HTTP 307) to the destination URL stored for `code`, and records a best-effort click event (referrer + user agent). Analytics failures never break the redirect.

- `404 Not Found` — unknown code.
- `410 Gone` — the code exists but is inactive or expired.

## `GET /api/urls/{code}`
Returns the same metadata shape as the create response.

- `404 Not Found` — unknown code.

## `GET /api/urls/{code}/analytics`
```json
{ "code": "abc1234", "click_count": 3, "recent_clicks": [{"clicked_at": "...", "referrer": "..."}] }
```
- `404 Not Found` — unknown code.

## Security notes
- Only `http`/`https` destination schemes are accepted (configurable via `ALLOWED_URL_SCHEMES`), which blocks `javascript:`/`data:`-style open-redirect/XSS vectors.
- All database access is parameterized (no string-built SQL).
- Click analytics are recorded via a separate, exception-isolated write path so a storage hiccup there can never corrupt or block the redirect.
