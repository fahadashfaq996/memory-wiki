from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class RetryDecision:
    retryable: bool
    retry_after: float | None = None


def _coerce_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _retry_after_from_headers(exc) -> float | None:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("retry-after") or headers.get("Retry-After")
    except AttributeError:
        return None
    return _coerce_float(raw)


def _find_key(obj, key: str):
    """Recursively search nested dicts/lists for the first value of ``key``."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, key)
            if found is not None:
                return found
    return None


def _retry_after_from_body(exc) -> float | None:
    body = getattr(exc, "body", None)
    if body is None:
        return None
    return _coerce_float(_find_key(body, "retry_after_seconds"))


def extract_retry_after(exc) -> float | None:
    """Pull a Retry-After hint from headers first, then the error body."""
    return _retry_after_from_headers(exc) or _retry_after_from_body(exc)


def classify_error(exc: Exception) -> RetryDecision:
    status = getattr(exc, "status_code", None)
    retry_after = extract_retry_after(exc)

    if status == 429:
        return RetryDecision(retryable=True, retry_after=retry_after)
    if isinstance(status, int) and 400 <= status < 500:
        return RetryDecision(retryable=False)
    if isinstance(status, int) and 500 <= status < 600:
        return RetryDecision(retryable=True, retry_after=retry_after)

    return RetryDecision(retryable=True, retry_after=retry_after)
