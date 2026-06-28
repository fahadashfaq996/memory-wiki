"""Worker entrypoint: a blocking loop that drains the job queue.

Run with: ``python -m app.worker.main``
"""

from __future__ import annotations

import logging
import signal
import threading

from sqlalchemy import select

from app.config import get_settings
from app.db.models import IngestionJob, JobStatus
from app.db.session import SessionLocal, init_db
from app.llm.client import get_memory_llm
from app.storage.memory_fs import MemoryFS
from app.storage.object_store import ObjectStore
from app.worker.queue import JobQueue
from app.worker.tasks import process_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("memory.worker")

_running = True


def _stop(*_args) -> None:
    global _running
    _running = False
    logger.info("shutdown signal received, finishing current job...")


def recover_jobs(queue: JobQueue) -> int:
    """Re-enqueue jobs left ``pending`` or stale ``processing`` from a crash."""
    requeued = 0
    with SessionLocal() as db:
        rows = db.execute(
            select(IngestionJob).where(
                IngestionJob.status.in_([JobStatus.pending, JobStatus.processing])
            )
        ).scalars()
        for job in rows:
            queue.enqueue(job.id)
            requeued += 1
    if requeued:
        logger.info("recovered %d unfinished job(s)", requeued)
    return requeued


def run() -> None:
    settings = get_settings()
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    init_db()
    store = ObjectStore(settings)
    store.ensure_bucket()
    fs = MemoryFS(store, settings)
    llm = get_memory_llm(settings)
    queue = JobQueue(settings)

    logger.info("worker started (llm_provider=%s)", settings.llm_provider)
    recover_jobs(queue)

    timers: set[threading.Timer] = set()
    while _running:
        job_id = queue.dequeue()
        if job_id is None:
            continue
        with SessionLocal() as db:
            result = process_job(job_id, db=db, fs=fs, llm=llm, settings=settings)
        if result.should_retry:
            # Re-enqueue after the delay on a background timer so a single
            # rate-limited job doesn't block other queued work.
            logger.info("re-queueing job %s in %.1fs", job_id, result.retry_delay)
            timer = threading.Timer(result.retry_delay, queue.enqueue, args=[job_id])
            timer.daemon = True
            timer.start()
            timers = {t for t in timers if t.is_alive()}
            timers.add(timer)


if __name__ == "__main__":
    run()
