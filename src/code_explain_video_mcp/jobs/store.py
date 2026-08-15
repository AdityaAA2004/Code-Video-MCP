"""The job store: the only shared mutable state in the server.

``explain_codebase`` writes a record and returns in milliseconds;
``get_render_status`` reads it repeatedly while a pipeline mutates it from a
background task. That is three concurrent accessors on one object, so every
read and write goes through an :class:`asyncio.Lock` and readers get a snapshot
copy rather than a live reference.

Only the in-memory backend exists today, which is what the architecture doc
calls for in v1. :class:`JobStore` is a Protocol so a SQLite-backed store can be
dropped in later without touching the tools.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from code_explain_video_mcp.errors import JobNotFoundError
from code_explain_video_mcp.jobs.models import JobRecord, JobStage, JobStatus
from code_explain_video_mcp.logging_conf import get_logger

logger = get_logger("jobs.store")


def new_job_id() -> str:
    """Generate a short, collision-safe, human-quotable job id.

    Short matters: the id is read aloud by the host's model back to the user and
    typed into ``get_render_status``. 12 hex chars is 48 bits — ample when the
    store holds tens of jobs, and far easier to relay than a full UUID.
    """
    return f"job_{uuid.uuid4().hex[:12]}"


@runtime_checkable
class JobStore(Protocol):
    """The contract the tools and the runner depend on."""

    async def create(self, record: JobRecord) -> JobRecord: ...

    async def get(self, job_id: str) -> JobRecord: ...

    async def update(self, job_id: str, **fields: object) -> JobRecord: ...

    async def enter_stage(
        self, job_id: str, stage: JobStage, message: str | None = None
    ) -> JobRecord: ...

    async def finish(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        message: str | None = None,
    ) -> JobRecord: ...

    async def list_ids(self) -> list[str]: ...

    async def reap(self, ttl_seconds: float) -> list[str]: ...


class InMemoryJobStore:
    """Dict-backed store. Jobs do not survive a server restart, by design.

    A restart also kills the background tasks driving those jobs, so persisting
    records without persisting progress would just hand the host stale
    ``running`` jobs that never advance.
    """

    def __init__(self) -> None:
        self._records: dict[str, JobRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, record: JobRecord) -> JobRecord:
        """Insert a new record and return its snapshot."""
        async with self._lock:
            if record.job_id in self._records:
                raise ValueError(f"Duplicate job id {record.job_id!r}")
            self._records[record.job_id] = record
            logger.info(
                "job created (scope=%s goal=%s)",
                record.scope_summary,
                (record.goal or "<none>")[:80],
                extra={"job_id": record.job_id},
            )
            return record.snapshot()

    async def get(self, job_id: str) -> JobRecord:
        """Return a snapshot of ``job_id``.

        Raises:
            JobNotFoundError: Unknown id, or the record was reaped by TTL.
        """
        async with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise JobNotFoundError(job_id)
            return record.snapshot()

    async def update(self, job_id: str, **fields: object) -> JobRecord:
        """Set arbitrary fields on a record under the lock."""
        async with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise JobNotFoundError(job_id)
            for name, value in fields.items():
                if not hasattr(record, name):
                    raise AttributeError(f"JobRecord has no field {name!r}")
                setattr(record, name, value)
            record.touch()
            return record.snapshot()

    async def enter_stage(
        self, job_id: str, stage: JobStage, message: str | None = None
    ) -> JobRecord:
        """Advance a job to ``stage`` and log the transition."""
        async with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise JobNotFoundError(job_id)
            record.enter_stage(stage, message)
            logger.info(
                "stage -> %-24s %s",
                stage,
                record.message or "",
                extra={"job_id": job_id},
            )
            return record.snapshot()

    async def finish(
        self,
        job_id: str,
        status: JobStatus,
        *,
        error: str | None = None,
        message: str | None = None,
    ) -> JobRecord:
        """Move a job into a terminal status.

        Idempotent: finishing an already-terminal job is a no-op, so a cancel
        racing a natural completion cannot rewrite the outcome.
        """
        async with self._lock:
            record = self._records.get(job_id)
            if record is None:
                raise JobNotFoundError(job_id)
            if record.is_terminal:
                return record.snapshot()
            record.status = status
            record.error = error
            if message is not None:
                record.message = message
            if status == "succeeded":
                record.stage = "complete"
            record.finished_at = time.time()
            record.touch()
            logger.info(
                "job %s (%s)",
                status,
                error or record.message or "",
                extra={"job_id": job_id},
            )
            return record.snapshot()

    async def list_ids(self) -> list[str]:
        """Return every known job id, newest first."""
        async with self._lock:
            return [
                r.job_id
                for r in sorted(
                    self._records.values(), key=lambda r: r.created_at, reverse=True
                )
            ]

    async def reap(self, ttl_seconds: float) -> list[str]:
        """Drop terminal records older than ``ttl_seconds``; return their ids.

        Running jobs are never reaped regardless of age — a slow render must not
        vanish out from under a polling host.
        """
        cutoff = time.time() - ttl_seconds
        async with self._lock:
            expired = [
                job_id
                for job_id, record in self._records.items()
                if record.is_terminal
                and record.finished_at is not None
                and record.finished_at < cutoff
            ]
            for job_id in expired:
                del self._records[job_id]
        if expired:
            logger.info("reaped %d expired job record(s)", len(expired))
        return expired


def build_job_record(
    *,
    goal: str | None,
    requested_scope: str | None,
    root: Path,
    scope_mode: str,
    scope_summary: str,
    notes: list[str] | None = None,
) -> JobRecord:
    """Construct a fresh queued ``JobRecord`` with a new id."""
    return JobRecord(
        job_id=new_job_id(),
        goal=goal,
        requested_scope=requested_scope,
        root=root,
        scope_mode=scope_mode,
        scope_summary=scope_summary,
        notes=list(notes or []),
    )
