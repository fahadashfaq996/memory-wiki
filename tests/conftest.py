"""Shared test fixtures.

The fixtures here let the unit and e2e tests run fully offline:
- ``InMemoryObjectStore`` duck-types ``ObjectStore`` for the memory filesystem.
- A SQLite engine stands in for Postgres.
- A ``FakeQueue`` collects job ids so the test can drain them synchronously.
"""

from __future__ import annotations

import datetime

import pytest

from app.storage.object_store import ObjectNotFound, StoredObject


class InMemoryObjectStore:
    """A dict-backed stand-in for the S3 object store."""

    def __init__(self) -> None:
        self._data: dict[str, tuple[bytes, datetime.datetime]] = {}

    def ensure_bucket(self) -> None:  # pragma: no cover - no-op
        pass

    def put(self, key: str, body: str, metadata: dict | None = None) -> None:
        self._data[key] = (body.encode("utf-8"), datetime.datetime.now(datetime.timezone.utc))

    def get(self, key: str) -> str:
        if key not in self._data:
            raise ObjectNotFound(key)
        return self._data[key][0].decode("utf-8")

    def exists(self, key: str) -> bool:
        return key in self._data

    def delete(self, key: str) -> None:
        self._data.pop(key, None)

    def list(self, prefix: str, delimiter: str | None = None):
        common: set[str] = set()
        objects: list[StoredObject] = []
        for key, (body, lm) in self._data.items():
            if not key.startswith(prefix):
                continue
            rest = key[len(prefix):]
            if delimiter and delimiter in rest:
                head = rest.split(delimiter, 1)[0]
                common.add(prefix + head + delimiter)
            else:
                objects.append(StoredObject(key=key, size=len(body), last_modified=lm))
        return sorted(common), objects


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.jobs.append(job_id)

    def dequeue(self, timeout: int | None = None):  # pragma: no cover
        return self.jobs.pop(0) if self.jobs else None

    def ping(self) -> bool:  # pragma: no cover
        return True


@pytest.fixture
def object_store() -> InMemoryObjectStore:
    return InMemoryObjectStore()


@pytest.fixture
def memory_fs(object_store):
    from app.config import Settings
    from app.storage.memory_fs import MemoryFS

    return MemoryFS(store=object_store, settings=Settings(memory_prefix="memories"))


@pytest.fixture
def fake_llm():
    from app.llm.client import FakeLLM

    return FakeLLM()


@pytest.fixture
def sqlite_sessionmaker():
    """A SQLite-backed sessionmaker with all tables created (stands in for Postgres)."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.db.session import Base
    import app.db.models  # noqa: F401  (register tables)

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)
