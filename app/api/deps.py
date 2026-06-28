"""Shared FastAPI dependencies.

Singletons (object store, queue) are created lazily and cached so each request
reuses connections instead of rebuilding clients.
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings
from app.storage.memory_fs import MemoryFS
from app.storage.object_store import ObjectStore
from app.worker.queue import JobQueue


@lru_cache
def get_object_store() -> ObjectStore:
    return ObjectStore(get_settings())


@lru_cache
def get_memory_fs() -> MemoryFS:
    return MemoryFS(get_object_store(), get_settings())


@lru_cache
def get_job_queue() -> JobQueue:
    return JobQueue(get_settings())
