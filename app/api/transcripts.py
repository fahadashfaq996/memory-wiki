from __future__ import annotations

import hashlib

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_job_queue
from app.db.models import IngestionJob, JobStatus, Transcript
from app.db.session import get_db
from app.schemas.transcript import (
    IngestionStatus,
    TranscriptCreate,
    TranscriptCreateResponse,
    TranscriptOut,
)
from app.worker.queue import JobQueue

router = APIRouter(prefix="/transcripts", tags=["transcripts"])


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.strip().encode("utf-8")).hexdigest()


def _latest_job(db: Session, transcript_id: str) -> IngestionJob | None:
    return db.execute(
        select(IngestionJob)
        .where(IngestionJob.transcript_id == transcript_id)
        .order_by(IngestionJob.created_at.desc())
    ).scalars().first()


def _requeue(db: Session, queue: JobQueue, job: IngestionJob) -> None:
    """Reset a job to a clean pending state and put it back on the queue."""
    job.status = JobStatus.pending
    job.attempts = 0
    job.error = None
    db.commit()
    queue.enqueue(job.id)


@router.post("", response_model=TranscriptCreateResponse, status_code=201)
def create_transcript(
    payload: TranscriptCreate,
    db: Session = Depends(get_db),
    queue: JobQueue = Depends(get_job_queue),
) -> TranscriptCreateResponse:
    content_hash = _content_hash(payload.content)

    existing = db.execute(
        select(IngestionJob).where(IngestionJob.content_hash == content_hash)
    ).scalars().first()
    if existing is not None:
        if existing.status == JobStatus.failed:
            _requeue(db, queue, existing)
        return TranscriptCreateResponse(
            id=existing.transcript_id,
            job_id=existing.id,
            status=existing.status.value,
            duplicate=True,
        )

    transcript = Transcript(content=payload.content, title=payload.title, content_hash=content_hash)
    db.add(transcript)
    db.flush()

    job = IngestionJob(transcript_id=transcript.id, content_hash=content_hash)
    db.add(job)
    db.commit()

    queue.enqueue(job.id)
    return TranscriptCreateResponse(id=transcript.id, job_id=job.id, status=job.status.value)


@router.get("/{transcript_id}", response_model=TranscriptOut)
def get_transcript(transcript_id: str, db: Session = Depends(get_db)) -> TranscriptOut:
    transcript = db.get(Transcript, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="transcript not found")

    job = _latest_job(db, transcript_id)
    ingestion = (
        IngestionStatus(job_id=job.id, status=job.status.value, attempts=job.attempts, error=job.error)
        if job
        else None
    )
    return TranscriptOut(
        id=transcript.id,
        title=transcript.title,
        content=transcript.content,
        created_at=transcript.created_at,
        ingestion=ingestion,
    )


@router.post("/{transcript_id}/reprocess", response_model=IngestionStatus)
def reprocess_transcript(
    transcript_id: str,
    db: Session = Depends(get_db),
    queue: JobQueue = Depends(get_job_queue),
) -> IngestionStatus:
    """Re-run memory generation for a transcript.

    Useful to recover a ``failed`` job once a transient issue clears. Safe to
    call on a ``done`` transcript too: the merge step is idempotent per
    transcript, so already-incorporated memories are skipped.
    """
    transcript = db.get(Transcript, transcript_id)
    if transcript is None:
        raise HTTPException(status_code=404, detail="transcript not found")

    job = _latest_job(db, transcript_id)
    if job is None:
        job = IngestionJob(transcript_id=transcript.id, content_hash=transcript.content_hash)
        db.add(job)
        db.commit()
        queue.enqueue(job.id)
    elif job.status in (JobStatus.pending, JobStatus.processing):
        raise HTTPException(status_code=409, detail=f"job already {job.status.value}")
    else:
        _requeue(db, queue, job)

    return IngestionStatus(job_id=job.id, status=job.status.value, attempts=job.attempts, error=job.error)
