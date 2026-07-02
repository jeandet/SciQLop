"""JobsBackend: submit/status/list/cancel for detached background jobs that
survive SciQLop closing or crashing (like `nohup ... &`), plus reconciliation
of job records from disk and Qt signals for a future UI to subscribe to."""
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List

from PySide6.QtCore import QObject, Signal

from .job_record import Job, compute_status

_LOG_TAIL_LINES = 20


def _jobs_dir(workspace_dir: str) -> Path:
    d = Path(workspace_dir) / ".sciqlop-jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _log_tail(log_path: str) -> str:
    p = Path(log_path)
    if not p.exists():
        return ""
    lines = p.read_text(errors="replace").splitlines()
    return "\n".join(lines[-_LOG_TAIL_LINES:])


class JobsBackend(QObject):
    job_added = Signal(str)
    job_status_changed = Signal(str, str)

    def __init__(self, workspace_dir_getter: Callable[[], str], parent=None):
        super().__init__(parent)
        self._workspace_dir_getter = workspace_dir_getter
        self._jobs: Dict[str, Job] = {}
        self._last_status: Dict[str, str] = {}
        self._reconcile()

    def _reconcile(self) -> None:
        try:
            workspace_dir = self._workspace_dir_getter()
        except RuntimeError:
            return
        d = _jobs_dir(workspace_dir)
        for toml_path in sorted(d.glob("*.toml")):
            try:
                job = Job.load(toml_path)
            except Exception:
                continue
            self._jobs[job.id] = job

    def submit_job(self, command: str, name: str) -> str:
        d = _jobs_dir(self._workspace_dir_getter())
        job_id = uuid.uuid4().hex[:12]
        log_path = d / f"{job_id}.log"
        marker_path = d / f"{job_id}.exit"
        wrapper = f"{{ {command} ; }} > {shlex.quote(str(log_path))} 2>&1 ; echo $? > {shlex.quote(str(marker_path))}"
        proc = subprocess.Popen(["/bin/sh", "-c", wrapper],
                                start_new_session=True, stdin=subprocess.DEVNULL)
        job = Job(id=job_id, name=name or command, command=command, pid=proc.pid,
                  log_path=str(log_path), marker_path=str(marker_path),
                  submitted_at=datetime.now().isoformat())
        job.save(d / f"{job_id}.toml")
        self._jobs[job_id] = job
        self._last_status[job_id] = "running"
        self.job_added.emit(job_id)
        return job_id

    def _status_dict(self, job: Job) -> dict:
        st = compute_status(job.marker_path, job.pid)
        previous = self._last_status.get(job.id)
        if previous is not None and previous != st["status"]:
            self.job_status_changed.emit(job.id, st["status"])
        self._last_status[job.id] = st["status"]
        return {
            "id": job.id, "name": job.name, "command": job.command,
            "submitted_at": job.submitted_at, "status": st["status"],
            "exit_code": st["exit_code"], "finished_at": st["finished_at"],
            "log_tail": _log_tail(job.log_path),
        }

    def job_status(self, job_id: str) -> dict:
        job = self._jobs[job_id]
        return self._status_dict(job)

    def list_jobs(self) -> List[dict]:
        return [self._status_dict(job) for job in self._jobs.values()]

    def cancel_job(self, job_id: str) -> None:
        job = self._jobs[job_id]
        try:
            os.kill(job.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def _construct_jobs_backend(app):
    from SciQLop.components.workspaces import workspaces_manager_instance
    from SciQLop.user_api.threading import on_main_thread

    @on_main_thread
    def _build():
        return JobsBackend(
            workspace_dir_getter=lambda: workspaces_manager_instance().workspace.workspace_dir,
            parent=app)
    return _build()


def jobs_backend_instance() -> JobsBackend:
    from SciQLop.core.sciqlop_application import sciqlop_app

    app = sciqlop_app()
    if not hasattr(app, "jobs_backend"):
        app.jobs_backend = _construct_jobs_backend(app)
    return app.jobs_backend
