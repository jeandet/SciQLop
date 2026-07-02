"""Submit and track background jobs that survive SciQLop closing (detached
OS processes, like `nohup ... &`) -- see
SciQLop.components.jobs.backend.jobs_backend.JobsBackend.
"""
from __future__ import annotations

from SciQLop.components.jobs.backend.jobs_backend import jobs_backend_instance


def submit_job(command: str, name: str = "") -> str:
    """Run `command` as a detached background process; returns the job id."""
    return jobs_backend_instance().submit_job(command, name or command)


def job_status(job_id: str) -> dict:
    """Return this job's current status: id, name, command, submitted_at,
    status ('running'|'done'|'crashed'), exit_code, finished_at, log_tail."""
    return jobs_backend_instance().job_status(job_id)


def list_jobs() -> list[dict]:
    """Return job_status() for every known job (including ones from a prior
    SciQLop session, reconciled from disk on startup)."""
    return jobs_backend_instance().list_jobs()


def cancel_job(job_id: str) -> None:
    """Send SIGTERM to a running job's process."""
    jobs_backend_instance().cancel_job(job_id)
