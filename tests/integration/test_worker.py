import pytest

from app.config import Settings
from app.db.models import IngestionJob, JobStatus, Transcript
from app.storage.memory_fs import MemoryFS
from app.worker.tasks import process_job

pytestmark = pytest.mark.integration

TRANSCRIPT = "Sara: Did you send the Q3 report?\nJohn: I'll send it Friday."


def _make_job(session):
    t = Transcript(content=TRANSCRIPT, content_hash="hash-1")
    session.add(t)
    session.flush()
    job = IngestionJob(transcript_id=t.id, content_hash="hash-1")
    session.add(job)
    session.commit()
    return job.id


def test_process_job_success(sqlite_sessionmaker, object_store, fake_llm):
    fs = MemoryFS(store=object_store, settings=Settings(memory_prefix="memories"))
    with sqlite_sessionmaker() as session:
        job_id = _make_job(session)
        result = process_job(job_id, db=session, fs=fs, llm=fake_llm, settings=Settings())
        assert result.status == JobStatus.done
        assert any("/people/" in p for p in result.written)
        assert session.get(IngestionJob, job_id).status == JobStatus.done


def test_process_job_idempotent_when_done(sqlite_sessionmaker, object_store, fake_llm):
    fs = MemoryFS(store=object_store, settings=Settings(memory_prefix="memories"))
    with sqlite_sessionmaker() as session:
        job_id = _make_job(session)
        process_job(job_id, db=session, fs=fs, llm=fake_llm, settings=Settings())
        result = process_job(job_id, db=session, fs=fs, llm=fake_llm, settings=Settings())
        assert result.status == JobStatus.done
        assert session.get(IngestionJob, job_id).attempts == 1  # not re-incremented


class _ExplodingLLM:
    def extract(self, transcript):
        raise RuntimeError("boom")

    def merge(self, **kwargs):  # pragma: no cover
        raise RuntimeError("boom")


def test_process_job_retries_then_fails(sqlite_sessionmaker, object_store):
    fs = MemoryFS(store=object_store, settings=Settings(memory_prefix="memories"))
    settings = Settings(max_attempts=2)
    with sqlite_sessionmaker() as session:
        job_id = _make_job(session)

        r1 = process_job(job_id, db=session, fs=fs, llm=_ExplodingLLM(), settings=settings)
        assert r1.status == JobStatus.pending and r1.should_retry is True

        r2 = process_job(job_id, db=session, fs=fs, llm=_ExplodingLLM(), settings=settings)
        assert r2.status == JobStatus.failed and r2.should_retry is False
        job = session.get(IngestionJob, job_id)
        assert job.attempts == 2
        assert "boom" in (job.error or "")
