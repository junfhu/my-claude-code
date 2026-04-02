"""Background job management.

Provides a lightweight job scheduler for background tasks that need
to run alongside the main agent conversation — file indexing,
MCP server health checks, plugin auto-updates, etc.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from enum import Enum
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Job:
    """A background job with lifecycle tracking."""

    def __init__(
        self,
        name: str,
        coro_fn: Callable[..., Coroutine[Any, Any, Any]],
        *,
        job_id: Optional[str] = None,
        args: tuple[Any, ...] = (),
        kwargs: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        retry_count: int = 0,
        retry_delay: float = 1.0,
    ) -> None:
        self.id = job_id or str(uuid.uuid4())
        self.name = name
        self.coro_fn = coro_fn
        self.args = args
        self.kwargs = kwargs or {}
        self.timeout = timeout
        self.retry_count = retry_count
        self.retry_delay = retry_delay

        self.status = JobStatus.PENDING
        self.result: Any = None
        self.error: Optional[Exception] = None
        self.created_at = time.monotonic()
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self._task: Optional[asyncio.Task[Any]] = None
        self._attempts = 0

    @property
    def duration(self) -> Optional[float]:
        if self.started_at is None:
            return None
        end = self.completed_at or time.monotonic()
        return end - self.started_at


class JobManager:
    """Manages background jobs with concurrency limits.

    Usage::

        mgr = JobManager(max_concurrent=4)
        job = mgr.submit("index_files", index_coro, args=(workspace,))
        await mgr.wait_for(job.id)
    """

    def __init__(self, max_concurrent: int = 8) -> None:
        self._max_concurrent = max_concurrent
        self._jobs: dict[str, Job] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._running = True

    def submit(
        self,
        name: str,
        coro_fn: Callable[..., Coroutine[Any, Any, Any]],
        *,
        args: tuple[Any, ...] = (),
        kwargs: Optional[dict[str, Any]] = None,
        timeout: Optional[float] = None,
        retry_count: int = 0,
        retry_delay: float = 1.0,
    ) -> Job:
        """Submit a new background job."""
        job = Job(
            name,
            coro_fn,
            args=args,
            kwargs=kwargs,
            timeout=timeout,
            retry_count=retry_count,
            retry_delay=retry_delay,
        )
        self._jobs[job.id] = job
        job._task = asyncio.create_task(self._run_job(job))
        logger.debug("Job submitted: %s (%s)", job.name, job.id)
        return job

    async def _run_job(self, job: Job) -> None:
        """Execute a job with concurrency control, timeout, and retry."""
        async with self._semaphore:
            for attempt in range(job.retry_count + 1):
                if not self._running:
                    job.status = JobStatus.CANCELLED
                    return

                job._attempts = attempt + 1
                job.status = JobStatus.RUNNING
                job.started_at = time.monotonic()

                try:
                    if job.timeout:
                        job.result = await asyncio.wait_for(
                            job.coro_fn(*job.args, **job.kwargs),
                            timeout=job.timeout,
                        )
                    else:
                        job.result = await job.coro_fn(*job.args, **job.kwargs)

                    job.status = JobStatus.COMPLETED
                    job.completed_at = time.monotonic()
                    logger.debug(
                        "Job completed: %s (%.1fms)",
                        job.name,
                        (job.duration or 0) * 1000,
                    )
                    return

                except asyncio.CancelledError:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = time.monotonic()
                    return

                except Exception as exc:
                    job.error = exc
                    if attempt < job.retry_count:
                        logger.debug(
                            "Job %s attempt %d failed, retrying: %s",
                            job.name,
                            attempt + 1,
                            exc,
                        )
                        await asyncio.sleep(job.retry_delay * (2 ** attempt))
                    else:
                        job.status = JobStatus.FAILED
                        job.completed_at = time.monotonic()
                        logger.error("Job failed: %s — %s", job.name, exc)

    async def wait_for(self, job_id: str, *, timeout: Optional[float] = None) -> Job:
        """Wait for a specific job to complete."""
        job = self._jobs.get(job_id)
        if not job:
            raise KeyError(f"Unknown job: {job_id}")
        if job._task:
            await asyncio.wait_for(job._task, timeout=timeout)
        return job

    async def wait_all(self, *, timeout: Optional[float] = None) -> list[Job]:
        """Wait for all pending/running jobs to complete."""
        tasks = [j._task for j in self._jobs.values() if j._task and not j._task.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=timeout)
        return list(self._jobs.values())

    def cancel(self, job_id: str) -> bool:
        """Cancel a running job."""
        job = self._jobs.get(job_id)
        if not job or not job._task:
            return False
        job._task.cancel()
        return True

    def cancel_all(self) -> int:
        """Cancel all running jobs. Returns count of cancelled jobs."""
        count = 0
        for job in self._jobs.values():
            if job._task and not job._task.done():
                job._task.cancel()
                count += 1
        return count

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list_jobs(self, *, status: Optional[JobStatus] = None) -> list[Job]:
        """List jobs, optionally filtered by status."""
        jobs = list(self._jobs.values())
        if status:
            jobs = [j for j in jobs if j.status == status]
        return jobs

    def cleanup(self, *, max_age: float = 3600.0) -> int:
        """Remove completed/failed/cancelled jobs older than max_age seconds."""
        now = time.monotonic()
        to_remove = [
            jid
            for jid, j in self._jobs.items()
            if j.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)
            and j.completed_at
            and (now - j.completed_at) > max_age
        ]
        for jid in to_remove:
            del self._jobs[jid]
        return len(to_remove)

    async def shutdown(self) -> None:
        """Gracefully shut down the job manager."""
        self._running = False
        self.cancel_all()
        try:
            await asyncio.wait_for(self.wait_all(), timeout=5.0)
        except (asyncio.TimeoutError, Exception):
            pass

    @property
    def active_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == JobStatus.RUNNING)

    @property
    def pending_count(self) -> int:
        return sum(1 for j in self._jobs.values() if j.status == JobStatus.PENDING)
