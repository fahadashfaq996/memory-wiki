from __future__ import annotations

import dataclasses
import logging
import random

from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.models import IngestionJob, JobStatus, Transcript
from app.llm.client import MemoryLLM
from app.llm.errors import classify_error
from app.llm.extractor import extract_memories
from app.llm.merger import merge_into_tree
from app.storage.memory_fs import MemoryFS

logger = logging.getLogger("memory.worker")


@dataclasses.dataclass
class JobResult:
    job_id: str
    status: JobStatus
    should_retry: bool = False
    retry_delay: float = 0.0
    written: list[str] = dataclasses.field(default_factory=list)


def compute_retry_delay(attempt: int, retry_after: float | None, settings: Settings) -> float:
    if retry_after is not None and retry_after > 0:
        base = retry_after
    else:
        base = settings.retry_backoff_seconds * (2 ** max(0, attempt - 1))
    base += random.uniform(0, settings.retry_jitter_seconds)
    return min(base, settings.max_retry_delay_seconds)


def process_job(
    job_id: str,
    *,
    db: Session,
    fs: MemoryFS,
    llm: MemoryLLM,
    settings: Settings | None = None,
) -> JobResult:
    settings = settings or get_settings()
    job = db.get(IngestionJob, job_id)
    if job is None:
        logger.warning("job %s not found", job_id)
        return JobResult(job_id, JobStatus.failed)

    if job.status == JobStatus.done:
        return JobResult(job_id, JobStatus.done)  # idempotent

    job.status = JobStatus.processing
    job.attempts += 1
    db.commit()

    transcript = db.get(Transcript, job.transcript_id)
    if transcript is None:
        job.status = JobStatus.failed
        job.error = "transcript missing"
        db.commit()
        return JobResult(job_id, JobStatus.failed)

    try:
        extraction = extract_memories(llm, transcript.content)
        written = merge_into_tree(fs, llm, extraction, transcript.id)
    except Exception as exc:
        decision = classify_error(exc)
        can_retry = decision.retryable and job.attempts < settings.max_attempts
        logger.warning(
            "job %s failed on attempt %s (retryable=%s, retry_after=%s)",
            job_id, job.attempts, decision.retryable, decision.retry_after,
        )
        if can_retry:
            delay = compute_retry_delay(job.attempts, decision.retry_after, settings)
            job.status = JobStatus.pending
            job.error = f"retrying in {delay:.0f}s (attempt {job.attempts}): {exc}"
            db.commit()
            return JobResult(job_id, JobStatus.pending, should_retry=True, retry_delay=delay)
        job.status = JobStatus.failed
        job.error = str(exc)
        db.commit()
        return JobResult(job_id, JobStatus.failed)

    job.status = JobStatus.done
    job.error = None
    db.commit()
    logger.info("job %s done, wrote %d memory file(s)", job_id, len(written))
    return JobResult(job_id, JobStatus.done, written=written)
