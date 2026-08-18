"""Background execution: one asyncio task per job.

This module is the reason ``explain_codebase`` can return in milliseconds while
the work it started takes minutes. It owns three things the tools must not:

* the ``asyncio.Task`` per job, so shutdown can cancel in-flight work;
* a semaphore bounding concurrent pipelines, so two hosts asking at once cannot
  start two Remotion renders on the same laptop;
* the translation from an exception inside a node into a *failed job record*
  rather than an unhandled task exception that vanishes into the event loop.

That last one matters more than it looks. A bare ``asyncio.create_task`` whose
coroutine raises logs "Task exception was never retrieved" at garbage-collection
time and leaves the job stuck at ``running`` forever. Every path through
:meth:`JobRunner._execute` therefore ends in a terminal store update.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from code_explain_video_mcp.errors import CodeExplainVideoError, PipelineError
from code_explain_video_mcp.jobs.models import JobRecord
from code_explain_video_mcp.logging_conf import (
    attach_job_log_handler,
    detach_job_log_handler,
    get_logger,
)

if TYPE_CHECKING:
    from code_explain_video_mcp.config import Settings
    from code_explain_video_mcp.jobs.store import JobStore
    from code_explain_video_mcp.jobs.workspace import WorkspaceManager

logger = get_logger("jobs.runner")


class JobRunner:
    """Starts, tracks, and cancels the background task behind each job."""

    def __init__(
        self,
        *,
        settings: "Settings",
        store: "JobStore",
        workspaces: "WorkspaceManager",
        pipeline: Any,
        recursion_limit: int = 50,
    ) -> None:
        self._settings = settings
        self._store = store
        self._workspaces = workspaces
        self._pipeline = pipeline
        self._recursion_limit = recursion_limit
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._semaphore = asyncio.Semaphore(settings.jobs.max_concurrent_jobs)

    @property
    def active_job_ids(self) -> set[str]:
        """Jobs whose task has not finished — used to protect workspaces from the reaper."""
        return {job_id for job_id, task in self._tasks.items() if not task.done()}

    def start(self, record: JobRecord) -> None:
        """Schedule ``record``'s pipeline and return immediately.

        Deliberately not ``async``: the tool that calls this must not be able to
        accidentally await the pipeline.
        """
        job_id = record.job_id
        if job_id in self._tasks:
            raise ValueError(f"Job {job_id!r} is already running")
        task = asyncio.create_task(self._execute(record), name=f"pipeline-{job_id}")
        self._tasks[job_id] = task
        # Capture the id, not ``record``: the callback outlives the job and
        # would otherwise pin the whole record (storyboard included) in memory.
        task.add_done_callback(lambda _: self._tasks.pop(job_id, None))
        logger.debug("scheduled pipeline task", extra={"job_id": job_id})

    async def _execute(self, record: JobRecord) -> None:
        """Drive one job from queued to a terminal status. Never raises."""
        # Imported here, not at module scope: ``graph.state`` annotates the
        # pipeline state with ``jobs.models.JobStage``, so a top-level import
        # would close the loop jobs -> graph -> jobs. The dependency direction
        # is jobs -> graph, and deferring this one call site is what keeps it
        # one-way.
        from code_explain_video_mcp.graph.state import initial_state

        job_id = record.job_id
        workspace = self._workspaces.create(job_id)
        await self._store.update(job_id, workspace=workspace.root)
        handler = attach_job_log_handler(job_id, workspace.root)

        try:
            async with self._semaphore:
                logger.info(
                    "pipeline start (dry_run=%s)",
                    self._settings.dry_run,
                    extra={"job_id": job_id},
                )
                state = initial_state(
                    job_id=job_id,
                    root=record.root,
                    goal=record.goal,
                    requested_scope=record.requested_scope,
                    workspace=workspace,
                    notes=record.notes,
                )
                final = await self._pipeline.ainvoke(
                    state, config={"recursion_limit": self._recursion_limit}
                )
                await self._finalize(job_id, final)

        except asyncio.CancelledError:
            await self._store.finish(
                job_id, "cancelled", error="Job was cancelled (server shutting down)."
            )
            logger.warning("pipeline cancelled", extra={"job_id": job_id})
            raise

        except PipelineError as exc:
            message = f"Failed during {exc.stage}: {exc}"
            await self._store.finish(job_id, "failed", error=message)
            logger.error("pipeline failed | %s", message, extra={"job_id": job_id})

        except CodeExplainVideoError as exc:
            await self._store.finish(job_id, "failed", error=str(exc))
            logger.error("pipeline failed | %s", exc, extra={"job_id": job_id})

        except Exception as exc:  # noqa: BLE001 - a stuck job is worse than a broad catch
            await self._store.finish(
                job_id, "failed", error=f"Unexpected {type(exc).__name__}: {exc}"
            )
            logger.exception("pipeline crashed", extra={"job_id": job_id})

        finally:
            detach_job_log_handler(handler)

    async def _finalize(self, job_id: str, final: dict[str, Any]) -> None:
        """Translate the graph's final state into a terminal job record."""
        notes = list(final.get("notes") or [])
        if notes:
            await self._store.update(job_id, notes=notes)

        for line in final.get("stage_log") or []:
            logger.debug("trace | %s", line, extra={"job_id": job_id})

        error = final.get("error")
        if error:
            await self._store.finish(job_id, "failed", error=str(error))
            return

        await self._store.finish(
            job_id,
            "succeeded",
            message=(
                "Dry run complete — all stages executed, no video rendered."
                if self._settings.dry_run
                else "Video rendered."
            ),
        )
        logger.info("pipeline complete", extra={"job_id": job_id})

    async def shutdown(self, *, timeout: float = 10.0) -> None:
        """Cancel every in-flight job and wait briefly for the tasks to unwind.

        Called from the server lifespan. Without it, a host disconnecting
        mid-render leaves an orphaned Remotion subprocess behind.
        """
        tasks = [t for t in self._tasks.values() if not t.done()]
        if not tasks:
            return
        logger.info("cancelling %d in-flight job(s)", len(tasks))
        for task in tasks:
            task.cancel()
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=timeout
            )
