import types

import pytest

from app.config import Settings
from app.llm.errors import RetryDecision, classify_error, extract_retry_after
from app.worker.tasks import compute_retry_delay

pytestmark = pytest.mark.unit


def _exc(status=None, headers=None, body=None):
    e = RuntimeError("boom")
    if status is not None:
        e.status_code = status
    if headers is not None:
        e.response = types.SimpleNamespace(headers=headers)
    if body is not None:
        e.body = body
    return e


def test_rate_limit_is_retryable_with_header_retry_after():
    d = classify_error(_exc(status=429, headers={"Retry-After": "28"}))
    assert d == RetryDecision(retryable=True, retry_after=28.0)


def test_rate_limit_retry_after_from_body_metadata():
    body = {"message": "rate limited", "code": 429, "metadata": {"retry_after_seconds": 27.5}}
    assert extract_retry_after(_exc(status=429, body=body)) == 27.5


@pytest.mark.parametrize("status", [400, 401, 402, 403, 404, 422])
def test_client_errors_are_permanent(status):
    assert classify_error(_exc(status=status)).retryable is False


def test_server_error_is_retryable():
    assert classify_error(_exc(status=503)).retryable is True


def test_unknown_error_defaults_retryable():
    d = classify_error(_exc())
    assert d.retryable is True and d.retry_after is None


def test_compute_retry_delay_honors_retry_after():
    s = Settings(retry_jitter_seconds=0, max_retry_delay_seconds=120)
    assert compute_retry_delay(attempt=1, retry_after=28, settings=s) == 28


def test_compute_retry_delay_exponential_backoff():
    s = Settings(retry_backoff_seconds=2, retry_jitter_seconds=0, max_retry_delay_seconds=120)
    assert compute_retry_delay(attempt=1, retry_after=None, settings=s) == 2
    assert compute_retry_delay(attempt=3, retry_after=None, settings=s) == 8


def test_compute_retry_delay_is_capped():
    s = Settings(retry_jitter_seconds=0, max_retry_delay_seconds=60)
    assert compute_retry_delay(attempt=1, retry_after=9999, settings=s) == 60
