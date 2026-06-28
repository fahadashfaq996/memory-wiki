from __future__ import annotations

import datetime

from pydantic import BaseModel, Field


class TranscriptCreate(BaseModel):
    content: str = Field(min_length=1, description="Raw conversation transcript text.")
    title: str | None = Field(default=None, max_length=512)


class TranscriptCreateResponse(BaseModel):
    id: str
    job_id: str
    status: str
    duplicate: bool = False


class IngestionStatus(BaseModel):
    job_id: str
    status: str
    attempts: int
    error: str | None = None


class TranscriptOut(BaseModel):
    id: str
    title: str | None
    content: str
    created_at: datetime.datetime
    ingestion: IngestionStatus | None = None
