"""End-to-end tests through the FastAPI app.

The HTTP layer, DB, memory filesystem, and worker task are wired together with
offline doubles (SQLite, in-memory object store, FakeLLM, in-process queue) so
the whole ingest -> ls/cat/grep flow is exercised without external services.
"""

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_job_queue, get_memory_fs
from app.config import Settings
from app.db.session import get_db
from app.llm.client import FakeLLM
from app.main import app
from app.storage.memory_fs import MemoryFS
from app.worker.tasks import process_job
from tests.conftest import FakeQueue, InMemoryObjectStore

pytestmark = pytest.mark.e2e

TRANSCRIPT = (
    "Sara: Did you finish the Q3 revenue report?\n"
    "John: Almost, I'll send it Friday. I'm joining the payments team next month.\n"
    "Sara: Great, congrats!"
)


@pytest.fixture
def client(sqlite_sessionmaker):
    store = InMemoryObjectStore()
    fs = MemoryFS(store=store, settings=Settings(memory_prefix="memories"))
    queue = FakeQueue()

    def _get_db():
        db = sqlite_sessionmaker()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[get_memory_fs] = lambda: fs
    app.dependency_overrides[get_job_queue] = lambda: queue

    test_client = TestClient(app)
    # Expose the doubles so the test can drain the queue.
    test_client.fs = fs
    test_client.queue = queue
    test_client.sessionmaker = sqlite_sessionmaker
    yield test_client
    app.dependency_overrides.clear()


def _drain(client):
    """Process all enqueued jobs synchronously, like the worker would."""
    llm = FakeLLM()
    while client.queue.jobs:
        job_id = client.queue.jobs.pop(0)
        with client.sessionmaker() as db:
            process_job(job_id, db=db, fs=client.fs, llm=llm, settings=Settings())


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_ingest_then_browse(client):
    resp = client.post("/transcripts", json={"content": TRANSCRIPT, "title": "Standup"})
    assert resp.status_code == 201
    body = resp.json()
    tid = body["id"]
    assert body["status"] == "pending"

    _drain(client)

    status = client.get(f"/transcripts/{tid}").json()
    assert status["ingestion"]["status"] == "done"

    # ls
    root = client.get("/memory/ls", params={"path": "/"}).json()
    assert "people" in {e["name"] for e in root["entries"]}

    people = client.get("/memory/ls", params={"path": "/people"}).json()
    names = {e["name"] for e in people["entries"]}
    assert "john.md" in names and "sara.md" in names

    # cat
    john = client.get("/memory/cat", params={"path": "/people/john.md"}).json()
    assert "payments" in john["content"].lower()
    assert john["metadata"]["source_transcripts"] == [tid]

    # grep
    grep = client.get("/memory/grep", params={"q": "report", "ignore_case": True}).json()
    assert grep["match_count"] >= 1


def test_duplicate_ingest_is_idempotent(client):
    first = client.post("/transcripts", json={"content": TRANSCRIPT}).json()
    second = client.post("/transcripts", json={"content": TRANSCRIPT}).json()
    assert second["duplicate"] is True
    assert second["id"] == first["id"]


def test_get_unknown_transcript_404(client):
    assert client.get("/transcripts/does-not-exist").status_code == 404


def test_cat_unknown_file_404(client):
    assert client.get("/memory/cat", params={"path": "/people/ghost.md"}).status_code == 404


def test_path_traversal_rejected(client):
    assert client.get("/memory/ls", params={"path": "../../etc"}).status_code == 400


def test_empty_transcript_rejected(client):
    assert client.post("/transcripts", json={"content": ""}).status_code == 422


def _force_failed(client, job_id):
    from app.db.models import IngestionJob, JobStatus

    with client.sessionmaker() as db:
        job = db.get(IngestionJob, job_id)
        job.status = JobStatus.failed
        job.attempts = 5
        job.error = "429 rate limited"
        db.commit()


def test_duplicate_ingest_requeues_failed_job(client):
    posted = client.post("/transcripts", json={"content": TRANSCRIPT}).json()
    job_id = posted["job_id"]
    client.queue.jobs.clear()  # pretend the worker already pulled and failed it
    _force_failed(client, job_id)

    again = client.post("/transcripts", json={"content": TRANSCRIPT}).json()
    assert again["duplicate"] is True
    assert again["job_id"] == job_id
    # The failed job was put back on the queue for another attempt.
    assert job_id in client.queue.jobs

    _drain(client)
    status = client.get(f"/transcripts/{posted['id']}").json()["ingestion"]
    assert status["status"] == "done"
    assert status["attempts"] == 1  # counter was reset on requeue


def test_reprocess_endpoint(client):
    posted = client.post("/transcripts", json={"content": TRANSCRIPT}).json()
    _drain(client)
    assert client.get(f"/transcripts/{posted['id']}").json()["ingestion"]["status"] == "done"

    resp = client.post(f"/transcripts/{posted['id']}/reprocess")
    assert resp.status_code == 200
    assert resp.json()["status"] == "pending"
    assert posted["job_id"] in client.queue.jobs

    _drain(client)
    assert client.get(f"/transcripts/{posted['id']}").json()["ingestion"]["status"] == "done"


def test_reprocess_unknown_transcript_404(client):
    assert client.post("/transcripts/nope/reprocess").status_code == 404
