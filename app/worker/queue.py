from __future__ import annotations

import redis

from app.config import Settings, get_settings


class JobQueue:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._redis = redis.from_url(self.settings.redis_url)
        self.key = self.settings.job_queue_key

    def enqueue(self, job_id: str) -> None:
        self._redis.lpush(self.key, job_id)

    def dequeue(self, timeout: int | None = None) -> str | None:
        timeout = self.settings.queue_poll_timeout if timeout is None else timeout
        try:
            result = self._redis.brpop(self.key, timeout=timeout)
        except (redis.exceptions.TimeoutError, redis.exceptions.ConnectionError):
            return None
        if result is None:
            return None
        _, value = result
        return value.decode("utf-8")

    def ping(self) -> bool:
        try:
            return bool(self._redis.ping())
        except redis.RedisError:
            return False
