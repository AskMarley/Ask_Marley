import secrets
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

from flask import abort, request, session

_RATE_LIMIT_BUCKETS = defaultdict(deque)
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def get_csrf_token():
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
        session.modified = True
    return token


def validate_csrf():
    if request.method in SAFE_METHODS:
        return

    session_token = session.get("csrf_token")
    request_token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not session_token or not request_token or session_token != request_token:
        abort(400, description="Missing or invalid CSRF token.")


def enforce_form_limits(max_field_length=300, max_fields=30):
    if request.method in SAFE_METHODS:
        return

    if len(request.form) > max_fields:
        abort(413, description="Too many form fields.")

    for value in request.form.values():
        if len(value) > max_field_length:
            abort(413, description="Submitted value is too large.")


def enforce_rate_limit(limit=120, window_seconds=60):
    remote_addr = request.headers.get("X-Forwarded-For", request.remote_addr or "local")
    endpoint = request.endpoint or "unknown"
    cache_key = f"{remote_addr}:{endpoint}"
    now = time.time()
    window = _RATE_LIMIT_BUCKETS[cache_key]

    while window and now - window[0] > window_seconds:
        window.popleft()

    if len(window) >= limit:
        abort(429, description="Rate limit exceeded. Please slow down.")

    window.append(now)


def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data:; "
        "script-src 'self';"
    )
    return response


def utc_now():
    return datetime.now(UTC)


def cache_is_fresh(timestamp, ttl_seconds):
    return utc_now() - timestamp < timedelta(seconds=ttl_seconds)
