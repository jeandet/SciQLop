# Background job runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `Jobs` component (`components/jobs/`) that runs detached, restart-surviving background processes (closing GH #25), exposed through `user_api.jobs` and four agent tools, plus a close-time warning when jobs are still running.

**Architecture:** Three layers, each independently usable. `components/jobs/backend/job_record.py` is a pure TOML dataclass (mirrors `WorkspaceManifest`) plus a status-computation function. `components/jobs/backend/jobs_backend.py` is a `QObject` singleton (mirrors `WorkspaceManager`/`workspaces_manager_instance()`) that launches jobs as genuinely detached OS processes (`setsid`, survive SciQLop closing/crashing), reconciles job records from disk on construction, and exposes signals for a future UI. `user_api/jobs.py` is a thin wrapper (mirrors `user_api/packages.py`). Agent tools are thin factories added directly to `_builder.py` (mirrors `_install_package_tool` — no separate `tools/jobs.py` file, since there's no tool-specific logic to isolate, all of it lives in `user_api.jobs`/`JobsBackend`). `mainwindow.py` gets a minimal, testable-in-isolation close-time check.

**Tech Stack:** Python stdlib (`subprocess`, `os`, `tomllib`/`tomli_w`, `uuid`), PySide6 (`QObject`, `Signal`, `QMessageBox`), pytest + pytest-qt.

## Global Constraints

- All commands run with `uv run`; canonical run `uv run pytest --no-xvfb <path> -q`.
- **Job payload is a shell command** (a string run via `/bin/sh -c`), not arbitrary Python — the agent builds the actual work with existing tools (`exec_python`, notebook cells, a script on disk) and hands the *command that runs it* to the job runner purely to detach + track it.
- **Detachment = genuine OS-level, like `nohup`:** `subprocess.Popen([...], start_new_session=True, stdin=subprocess.DEVNULL)` — never a thread, never a plain child subprocess (both die with SciQLop). The launched command is wrapped so it redirects its own stdout+stderr to a log file and writes its exit code to a marker file on completion — SciQLop is not around to `wait()` on it after it detaches.
- **Status is computed, never persisted:** marker file present → `done` (exit code = its contents, `finished_at` = its mtime); marker absent + pid alive (`os.kill(pid, 0)` succeeds) → `running`; marker absent + pid dead → `crashed`.
- **Persistence layout:** one TOML file per job under `<workspace_dir>/.sciqlop-jobs/<job_id>.toml`, following `WorkspaceManifest`'s exact dataclass + `classmethod load()` / instance `save()` shape (`tomllib.load`/`tomli_w.dump`). Job id: `uuid.uuid4().hex[:12]`.
- **Singleton pattern** (mirrors `workspaces_manager_instance()` in `components/workspaces/backend/workspaces_manager.py:231-235`): `sciqlop_app()` from `SciQLop.core.sciqlop_application`, lazily attach `app.jobs_backend`.
- **Active workspace access:** `workspaces_manager_instance().workspace.workspace_dir` (property on `Workspace`, `components/workspaces/backend/workspace.py:32-34`); `workspaces_manager_instance().has_workspace` guards "no active workspace." `JobsBackend` takes the workspace-dir lookup as an injected callable (default `lambda: workspaces_manager_instance().workspace.workspace_dir`) so tests can point it at a temp dir without a real workspace.
- **No-workspace behavior:** `JobsBackend` methods raise `RuntimeError("no active workspace")` when `not workspaces_manager_instance().has_workspace` (via the injected getter) — `user_api/jobs.py` does NOT catch this (thin wrapper, propagates); the agent tool layer's existing generic `except Exception` in `_text_tool` (`_builder.py:87-99`) turns it into a clean error message automatically, exactly like every other tool in this codebase.
- **Agent tools:** `sciqlop_submit_job`/`sciqlop_cancel_job` are **gated** (spawn/signal a process — go in `_write_tools`'s returned list); `sciqlop_job_status`/`sciqlop_list_jobs` are **read-only** (go in the top `tools = [...]` list in `build_sciqlop_tools`, next to `_show_figure_tool()`/`_describe_tool()`). All four `thread=True` (subprocess/file I/O). Tools return `{"content": [{"type": "text", ...}]}`.
- Every test importing from `SciQLop.components.agents.tools.*` takes pytest-qt's `qtbot` fixture and imports inside the test function (the agents package `__init__` → `chat_dock` → `_builder` → `ProductsModel` needs a `QApplication`). Do NOT edit `tests/conftest.py` or `tools/__init__.py`.
- `SciQLop/core/ui/mainwindow.py`'s existing `closeEvent` (line 475-483) has a deferred-close idiom (`_schedule_async_close()` → `event.ignore(); return`) for async plugin teardown — the jobs warning reuses this pattern but is checked *before* it, as a separate, independently testable guard.

---

### Task 1: `components/jobs/backend/job_record.py` — pure TOML record + status computation

**Files:**
- Create: `SciQLop/components/jobs/backend/__init__.py` (empty)
- Create: `SciQLop/components/jobs/__init__.py` (empty)
- Create: `SciQLop/components/jobs/backend/job_record.py`
- Test: `tests/test_job_record.py`

**Interfaces:**
- Produces:
  - `Job` dataclass: `id: str, name: str, command: str, pid: int, log_path: str, marker_path: str, submitted_at: str`.
  - `Job.load(path) -> Job` (classmethod), `Job.save(self, path) -> None` (instance method) — TOML round-trip, mirrors `WorkspaceManifest`.
  - `compute_status(marker_path: str, pid: int, pid_alive: Callable[[int], bool] = _pid_alive) -> dict` — returns `{"status": "done"|"running"|"crashed", "exit_code": int|None, "finished_at": str|None}`.
  - `_pid_alive(pid: int) -> bool` — the real `os.kill(pid, 0)` check (default for `compute_status`); tests inject a fake instead.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_job_record.py
import os
from pathlib import Path


def test_job_round_trips_through_toml(tmp_path):
    from SciQLop.components.jobs.backend.job_record import Job
    j = Job(id="abc123", name="11-year build", command="python build.py",
           pid=4242, log_path=str(tmp_path / "abc123.log"),
           marker_path=str(tmp_path / "abc123.exit"), submitted_at="2026-07-02T10:00:00")
    path = tmp_path / "abc123.toml"
    j.save(path)
    loaded = Job.load(path)
    assert loaded == j


def test_compute_status_done_reads_exit_code_and_mtime(tmp_path):
    from SciQLop.components.jobs.backend.job_record import compute_status
    marker = tmp_path / "j.exit"
    marker.write_text("3\n")
    result = compute_status(str(marker), pid=999, pid_alive=lambda p: True)
    assert result["status"] == "done"
    assert result["exit_code"] == 3
    assert result["finished_at"]  # non-empty isoformat string


def test_compute_status_running_when_marker_absent_and_pid_alive(tmp_path):
    from SciQLop.components.jobs.backend.job_record import compute_status
    marker = tmp_path / "nope.exit"
    result = compute_status(str(marker), pid=999, pid_alive=lambda p: True)
    assert result == {"status": "running", "exit_code": None, "finished_at": None}


def test_compute_status_crashed_when_marker_absent_and_pid_dead(tmp_path):
    from SciQLop.components.jobs.backend.job_record import compute_status
    marker = tmp_path / "nope.exit"
    result = compute_status(str(marker), pid=999, pid_alive=lambda p: False)
    assert result == {"status": "crashed", "exit_code": None, "finished_at": None}


def test_pid_alive_uses_real_os_kill():
    from SciQLop.components.jobs.backend.job_record import _pid_alive
    assert _pid_alive(os.getpid()) is True
    assert _pid_alive(2**30) is False  # astronomically unlikely to be a real pid
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_job_record.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'SciQLop.components.jobs'`.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/jobs/__init__.py
```
(empty file)

```python
# SciQLop/components/jobs/backend/__init__.py
```
(empty file)

```python
# SciQLop/components/jobs/backend/job_record.py
"""Reader/writer for background-job records (TOML format), one file per job
under <workspace>/.sciqlop-jobs/<id>.toml.

Job format::

    [job]
    id = "a1b2c3d4e5f6"
    name = "11-year MMS build"
    command = "python build_survey.py"
    pid = 12345
    log_path = "/path/to/.sciqlop-jobs/a1b2c3d4e5f6.log"
    marker_path = "/path/to/.sciqlop-jobs/a1b2c3d4e5f6.exit"
    submitted_at = "2026-07-02T10:00:00"
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional


@dataclass
class Job:
    id: str
    name: str
    command: str
    pid: int
    log_path: str
    marker_path: str
    submitted_at: str

    @classmethod
    def load(cls, path: Path | str) -> "Job":
        path = Path(path)
        with open(path, "rb") as f:
            data = tomllib.load(f)
        j = data["job"]
        return cls(id=j["id"], name=j["name"], command=j["command"], pid=j["pid"],
                   log_path=j["log_path"], marker_path=j["marker_path"],
                   submitted_at=j["submitted_at"])

    def save(self, path: Path | str) -> None:
        import tomli_w
        data = {"job": {
            "id": self.id, "name": self.name, "command": self.command,
            "pid": self.pid, "log_path": self.log_path,
            "marker_path": self.marker_path, "submitted_at": self.submitted_at,
        }}
        with open(path, "wb") as f:
            tomli_w.dump(data, f)


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def compute_status(marker_path: str, pid: int,
                   pid_alive: Callable[[int], bool] = _pid_alive) -> dict:
    marker = Path(marker_path)
    if marker.exists():
        try:
            exit_code: Optional[int] = int(marker.read_text().strip())
        except ValueError:
            exit_code = None
        finished_at = datetime.fromtimestamp(marker.stat().st_mtime).isoformat()
        return {"status": "done", "exit_code": exit_code, "finished_at": finished_at}
    if pid_alive(pid):
        return {"status": "running", "exit_code": None, "finished_at": None}
    return {"status": "crashed", "exit_code": None, "finished_at": None}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_job_record.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/jobs/__init__.py SciQLop/components/jobs/backend/__init__.py SciQLop/components/jobs/backend/job_record.py tests/test_job_record.py
git commit -m "feat(jobs): Job TOML record + status computation (done/running/crashed)"
```

---

### Task 2: `components/jobs/backend/jobs_backend.py` — `JobsBackend`, detached launch, reconciliation, signals

**Files:**
- Create: `SciQLop/components/jobs/backend/jobs_backend.py`
- Test: `tests/test_jobs_backend.py`

**Interfaces:**
- Consumes: `Job`, `compute_status` (Task 1).
- Produces:
  - `JobsBackend(QObject)` — constructor `__init__(self, workspace_dir_getter: Callable[[], str], parent=None)`. Signals: `job_added = Signal(str)`, `job_status_changed = Signal(str, str)` (job id, new status).
  - Methods: `submit_job(command: str, name: str) -> str` (returns job id), `job_status(job_id: str) -> dict`, `list_jobs() -> list[dict]`, `cancel_job(job_id: str) -> None`.
  - `jobs_backend_instance() -> JobsBackend` — module-level singleton accessor using the real `workspaces_manager_instance` getter.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_jobs_backend.py
"""JobsBackend needs a QApplication (QObject/Signal), so tests take qtbot."""
import os
import time
from pathlib import Path
from unittest.mock import MagicMock


def _backend(qtbot, tmp_path):
    from SciQLop.components.jobs.backend.jobs_backend import JobsBackend
    return JobsBackend(workspace_dir_getter=lambda: str(tmp_path))


def test_submit_job_launches_detached_and_persists_record(qtbot, tmp_path, monkeypatch):
    backend = _backend(qtbot, tmp_path)
    captured = {}

    class _FakeProc:
        pid = 4242

    def _fake_popen(argv, start_new_session=None, stdin=None):
        captured["argv"] = argv
        captured["start_new_session"] = start_new_session
        captured["stdin"] = stdin
        return _FakeProc()

    monkeypatch.setattr("subprocess.Popen", _fake_popen)
    job_id = backend.submit_job("python build.py", "11-year build")

    assert captured["start_new_session"] is True
    assert captured["stdin"] is not None  # DEVNULL, not inherited
    assert argv_is_sh_c_wrapping(captured["argv"], "python build.py")

    record_path = tmp_path / ".sciqlop-jobs" / f"{job_id}.toml"
    assert record_path.exists()

    from SciQLop.components.jobs.backend.job_record import Job
    loaded = Job.load(record_path)
    assert loaded.pid == 4242
    assert loaded.name == "11-year build"
    assert loaded.command == "python build.py"


def argv_is_sh_c_wrapping(argv, command):
    return argv[0] == "/bin/sh" and argv[1] == "-c" and command in argv[2]


def test_submit_job_emits_job_added(qtbot, tmp_path, monkeypatch):
    backend = _backend(qtbot, tmp_path)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: MagicMock(pid=1))
    with qtbot.waitSignal(backend.job_added, timeout=1000) as blocker:
        job_id = backend.submit_job("echo hi", "greet")
    assert blocker.args == [job_id]


def test_job_status_reports_running_then_done(qtbot, tmp_path, monkeypatch):
    backend = _backend(qtbot, tmp_path)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: MagicMock(pid=os.getpid()))
    job_id = backend.submit_job("echo hi", "greet")

    status = backend.job_status(job_id)
    assert status["status"] == "running"
    assert status["id"] == job_id
    assert status["name"] == "greet"

    jobs_dir = tmp_path / ".sciqlop-jobs"
    (jobs_dir / f"{job_id}.exit").write_text("0")
    status2 = backend.job_status(job_id)
    assert status2["status"] == "done"
    assert status2["exit_code"] == 0


def test_job_status_emits_job_status_changed_on_transition(qtbot, tmp_path, monkeypatch):
    backend = _backend(qtbot, tmp_path)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: MagicMock(pid=os.getpid()))
    job_id = backend.submit_job("echo hi", "greet")
    backend.job_status(job_id)  # first call establishes "running" baseline

    jobs_dir = tmp_path / ".sciqlop-jobs"
    (jobs_dir / f"{job_id}.exit").write_text("0")
    with qtbot.waitSignal(backend.job_status_changed, timeout=1000) as blocker:
        backend.job_status(job_id)
    assert blocker.args == [job_id, "done"]


def test_list_jobs_returns_every_known_job(qtbot, tmp_path, monkeypatch):
    backend = _backend(qtbot, tmp_path)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: MagicMock(pid=os.getpid()))
    id_a = backend.submit_job("echo a", "job-a")
    id_b = backend.submit_job("echo b", "job-b")
    ids = {j["id"] for j in backend.list_jobs()}
    assert ids == {id_a, id_b}


def test_cancel_job_sends_sigterm(qtbot, tmp_path, monkeypatch):
    backend = _backend(qtbot, tmp_path)
    monkeypatch.setattr("subprocess.Popen", lambda *a, **k: MagicMock(pid=4242))
    job_id = backend.submit_job("sleep 100", "long job")
    calls = []
    monkeypatch.setattr("os.kill", lambda pid, sig: calls.append((pid, sig)))
    backend.cancel_job(job_id)
    import signal
    assert calls == [(4242, signal.SIGTERM)]


def test_reconciliation_loads_existing_records_on_construction(qtbot, tmp_path, monkeypatch):
    from SciQLop.components.jobs.backend.job_record import Job
    jobs_dir = tmp_path / ".sciqlop-jobs"
    jobs_dir.mkdir()
    j = Job(id="existing1", name="prior session job", command="echo x", pid=os.getpid(),
           log_path=str(jobs_dir / "existing1.log"),
           marker_path=str(jobs_dir / "existing1.exit"), submitted_at="2026-07-01T00:00:00")
    j.save(jobs_dir / "existing1.toml")

    backend = _backend(qtbot, tmp_path)
    ids = {job["id"] for job in backend.list_jobs()}
    assert "existing1" in ids


def test_no_workspace_raises_runtime_error(qtbot):
    from SciQLop.components.jobs.backend.jobs_backend import JobsBackend

    def _no_workspace():
        raise RuntimeError("no active workspace")

    backend = JobsBackend(workspace_dir_getter=_no_workspace)
    import pytest
    with pytest.raises(RuntimeError, match="no active workspace"):
        backend.submit_job("echo hi", "x")


def test_real_detached_subprocess_writes_marker_and_log(qtbot, tmp_path):
    """The one test touching a real OS process: confirms the wrapper script
    actually detaches, writes the log, and writes the exit-code marker."""
    backend = _backend(qtbot, tmp_path)
    job_id = backend.submit_job("sh -c 'echo hello; exit 3'", "real job")

    deadline = time.monotonic() + 5.0
    status = backend.job_status(job_id)
    while status["status"] != "done" and time.monotonic() < deadline:
        time.sleep(0.1)
        status = backend.job_status(job_id)

    assert status["status"] == "done"
    assert status["exit_code"] == 3
    log_path = Path(tmp_path / ".sciqlop-jobs" / f"{job_id}.log")
    assert "hello" in log_path.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_jobs_backend.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named ...jobs_backend`.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/components/jobs/backend/jobs_backend.py
"""JobsBackend: submit/status/list/cancel for detached background jobs that
survive SciQLop closing or crashing (like `nohup ... &`), plus reconciliation
of job records from disk and Qt signals for a future UI to subscribe to."""
from __future__ import annotations

import os
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
        d = _jobs_dir(self._workspace_dir_getter())
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
        wrapper = f"{{ {command} ; }} > {log_path} 2>&1 ; echo $? > {marker_path}"
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


def jobs_backend_instance() -> JobsBackend:
    from SciQLop.core.sciqlop_application import sciqlop_app
    from SciQLop.components.workspaces import workspaces_manager_instance

    app = sciqlop_app()
    if not hasattr(app, "jobs_backend"):
        app.jobs_backend = JobsBackend(
            workspace_dir_getter=lambda: workspaces_manager_instance().workspace.workspace_dir,
            parent=app)
    return app.jobs_backend
```

Note: `submit_job` and `cancel_job` (and `_reconcile`/`_jobs_dir` via `job_status`/`list_jobs`) call `self._workspace_dir_getter()`, which for the real singleton is `lambda: workspaces_manager_instance().workspace.workspace_dir` — if there is no active workspace, `workspaces_manager_instance().workspace` raises (per its existing `@property` guard, `workspaces_manager.py:202-206`), which propagates as the `RuntimeError`-shaped failure `test_no_workspace_raises_runtime_error` expects (that test injects a getter that raises `RuntimeError("no active workspace")` directly, matching what the real property does — no special-casing needed in `JobsBackend` itself).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_jobs_backend.py -q`
Expected: PASS (9 tests, including the one real-subprocess test — may take up to a few seconds).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/jobs/backend/jobs_backend.py tests/test_jobs_backend.py
git commit -m "feat(jobs): JobsBackend — detached launch, reconciliation, signals"
```

---

### Task 3: `user_api/jobs.py` — thin wrapper

**Files:**
- Create: `SciQLop/user_api/jobs.py`
- Test: `tests/test_user_api_jobs.py`

**Interfaces:**
- Consumes: `jobs_backend_instance` (Task 2).
- Produces: `submit_job(command: str, name: str = "") -> str`, `job_status(job_id: str) -> dict`, `list_jobs() -> list[dict]`, `cancel_job(job_id: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_user_api_jobs.py
"""Thin-wrapper delegation tests for user_api.jobs -> JobsBackend."""
from unittest.mock import MagicMock


def test_submit_job_delegates(monkeypatch):
    import SciQLop.user_api.jobs as jobs_api
    backend = MagicMock()
    backend.submit_job.return_value = "job123"
    monkeypatch.setattr(jobs_api, "jobs_backend_instance", lambda: backend)
    result = jobs_api.submit_job("python build.py", "my build")
    assert result == "job123"
    backend.submit_job.assert_called_once_with("python build.py", "my build")


def test_submit_job_defaults_name_to_command(monkeypatch):
    import SciQLop.user_api.jobs as jobs_api
    backend = MagicMock()
    monkeypatch.setattr(jobs_api, "jobs_backend_instance", lambda: backend)
    jobs_api.submit_job("python build.py")
    backend.submit_job.assert_called_once_with("python build.py", "python build.py")


def test_job_status_delegates(monkeypatch):
    import SciQLop.user_api.jobs as jobs_api
    backend = MagicMock()
    backend.job_status.return_value = {"id": "job123", "status": "running"}
    monkeypatch.setattr(jobs_api, "jobs_backend_instance", lambda: backend)
    assert jobs_api.job_status("job123") == {"id": "job123", "status": "running"}
    backend.job_status.assert_called_once_with("job123")


def test_list_jobs_delegates(monkeypatch):
    import SciQLop.user_api.jobs as jobs_api
    backend = MagicMock()
    backend.list_jobs.return_value = [{"id": "a"}, {"id": "b"}]
    monkeypatch.setattr(jobs_api, "jobs_backend_instance", lambda: backend)
    assert jobs_api.list_jobs() == [{"id": "a"}, {"id": "b"}]


def test_cancel_job_delegates(monkeypatch):
    import SciQLop.user_api.jobs as jobs_api
    backend = MagicMock()
    monkeypatch.setattr(jobs_api, "jobs_backend_instance", lambda: backend)
    jobs_api.cancel_job("job123")
    backend.cancel_job.assert_called_once_with("job123")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_user_api_jobs.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'SciQLop.user_api.jobs'`.

- [ ] **Step 3: Write minimal implementation**

```python
# SciQLop/user_api/jobs.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_user_api_jobs.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/user_api/jobs.py tests/test_user_api_jobs.py
git commit -m "feat(jobs): user_api.jobs — thin wrapper over JobsBackend"
```

---

### Task 4: agent tools — `sciqlop_submit_job` / `job_status` / `list_jobs` / `cancel_job`

**Files:**
- Modify: `SciQLop/components/agents/tools/_builder.py`
- Test: `tests/test_jobs_tools_registration.py`

**Interfaces:**
- Consumes: `user_api.jobs.{submit_job,job_status,list_jobs,cancel_job}` (Task 3).
- Produces: 4 tool factories in `_builder.py`: `_submit_job_tool()`, `_job_status_tool()`, `_list_jobs_tool()`, `_cancel_job_tool()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_jobs_tools_registration.py
"""sciqlop_submit_job / job_status / list_jobs / cancel_job registration
(needs QApplication -> qtbot)."""
import asyncio
from unittest.mock import MagicMock


def _tool(qtbot, name):
    import SciQLop.components.agents.tools._builder as builder
    return next(t for t in builder.build_sciqlop_tools(MagicMock()) if t["name"] == name)


def test_submit_and_cancel_are_gated(qtbot):
    assert _tool(qtbot, "sciqlop_submit_job").get("gated", False) is True
    assert _tool(qtbot, "sciqlop_cancel_job").get("gated", False) is True


def test_status_and_list_are_ungated(qtbot):
    assert _tool(qtbot, "sciqlop_job_status").get("gated", False) is False
    assert _tool(qtbot, "sciqlop_list_jobs").get("gated", False) is False


def test_submit_job_schema(qtbot):
    schema = _tool(qtbot, "sciqlop_submit_job")["input_schema"]
    assert schema["properties"]["command"]["type"] == "string"
    assert schema["required"] == ["command"]


def test_submit_job_handler_delegates(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder.user_api_jobs, "submit_job", lambda command, name="": "job123")
    out = asyncio.run(_tool(qtbot, "sciqlop_submit_job")["handler"](
        {"command": "python build.py", "name": "my build"}))
    assert "job123" in out["content"][0]["text"]


def test_job_status_handler_delegates(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder.user_api_jobs, "job_status",
                        lambda job_id: {"id": job_id, "status": "running"})
    out = asyncio.run(_tool(qtbot, "sciqlop_job_status")["handler"]({"job_id": "job123"}))
    assert "running" in out["content"][0]["text"]


def test_list_jobs_handler_delegates(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    monkeypatch.setattr(builder.user_api_jobs, "list_jobs",
                        lambda: [{"id": "a", "status": "done"}])
    out = asyncio.run(_tool(qtbot, "sciqlop_list_jobs")["handler"]({}))
    assert "\"a\"" in out["content"][0]["text"] or "'a'" in out["content"][0]["text"]


def test_cancel_job_handler_delegates(qtbot, monkeypatch):
    import SciQLop.components.agents.tools._builder as builder
    calls = []
    monkeypatch.setattr(builder.user_api_jobs, "cancel_job", lambda job_id: calls.append(job_id))
    out = asyncio.run(_tool(qtbot, "sciqlop_cancel_job")["handler"]({"job_id": "job123"}))
    assert calls == ["job123"]
    assert "job123" in out["content"][0]["text"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest --no-xvfb tests/test_jobs_tools_registration.py -q`
Expected: FAIL — `StopIteration` (no such tool registered).

- [ ] **Step 3: Write minimal implementation**

In `_builder.py`, add a module import near the top with the other lazy-friendly imports (right after the existing `from . import context` line):

```python
from SciQLop.user_api import jobs as user_api_jobs
```

Add the four tool factories (place them near `_install_package_tool`, e.g. right before `_write_tools`):

```python
def _submit_job_tool() -> Dict[str, Any]:
    def _run(payload: Dict[str, Any]) -> Any:
        job_id = user_api_jobs.submit_job(str(payload["command"]), str(payload.get("name", "")))
        return f"submitted job `{job_id}`"

    return _text_tool(
        "sciqlop_submit_job",
        (
            "Run a shell command as a DETACHED background job that survives "
            "SciQLop closing or crashing (like `nohup ... &`) — use for long "
            "builds, surveys, or downloads. Build the actual work first with "
            "sciqlop_exec_python or a workspace script, then pass the command "
            "that runs it here. Returns a job id — check progress later with "
            "sciqlop_job_status or sciqlop_list_jobs, even in a future session."
        ),
        {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["command"],
        },
        _run,
        gated=True,
        thread=True,
    )


def _job_status_tool() -> Dict[str, Any]:
    return _text_tool(
        "sciqlop_job_status",
        (
            "Check a background job's status: 'running', 'done', or 'crashed', "
            "plus exit code and a tail of its output log. Works across SciQLop "
            "restarts — the job keeps running (or its result stays available) "
            "even if SciQLop was closed since it was submitted."
        ),
        {"type": "object", "properties": {"job_id": {"type": "string"}},
         "required": ["job_id"]},
        lambda p: str(user_api_jobs.job_status(str(p["job_id"]))),
        thread=True,
    )


def _list_jobs_tool() -> Dict[str, Any]:
    return _text_tool(
        "sciqlop_list_jobs",
        (
            "List every known background job (including ones submitted in a "
            "prior SciQLop session) with its current status. Use this to "
            "rediscover work you don't remember the job id for."
        ),
        {"type": "object", "properties": {}, "required": []},
        lambda _p: str(user_api_jobs.list_jobs()),
        thread=True,
    )


def _cancel_job_tool() -> Dict[str, Any]:
    def _run(payload: Dict[str, Any]) -> Any:
        user_api_jobs.cancel_job(str(payload["job_id"]))
        return f"sent SIGTERM to job `{payload['job_id']}`"

    return _text_tool(
        "sciqlop_cancel_job",
        "Cancel a running background job (sends SIGTERM to its process).",
        {"type": "object", "properties": {"job_id": {"type": "string"}},
         "required": ["job_id"]},
        _run,
        gated=True,
        thread=True,
    )
```

Register the two read-only tools in `build_sciqlop_tools`'s top `tools = [...]` list, right after `_show_figure_tool(),`:

```python
        _show_figure_tool(),
        _job_status_tool(),
        _list_jobs_tool(),
    ]
```

Register the two gated tools in `_write_tools`'s returned list, right after `_fetch_tool(),`:

```python
    return [set_time_range, _create_panel_tool(main_window), _exec_python_tool(),
            _fetch_tool(), _submit_job_tool(), _cancel_job_tool(), _install_package_tool()] + _notebook_write_tools() + [_run_notebook_cell_tool(), _interrupt_kernel_tool()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_jobs_tools_registration.py -q`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/_builder.py tests/test_jobs_tools_registration.py
git commit -m "feat(agents): register sciqlop_submit_job/job_status/list_jobs/cancel_job"
```

---

### Task 5: close-time warning for running jobs

**Files:**
- Modify: `SciQLop/core/ui/mainwindow.py`
- Test: `tests/test_mainwindow_close.py`

**Interfaces:**
- Produces: module-level `_confirm_close_with_running_jobs(parent, event, jobs: list[dict]) -> bool` (returns `True` if the close was cancelled — `event.ignore()` already called); `SciQLopMainWindow._warn_if_jobs_running(self, event) -> bool` (wires `self` + `jobs_backend_instance().list_jobs()` into the free function).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_mainwindow_close.py` (it already has `from .fixtures import *`):

```python
from unittest.mock import MagicMock


def test_confirm_close_no_running_jobs_proceeds(qapp):
    from SciQLop.core.ui.mainwindow import _confirm_close_with_running_jobs
    event = MagicMock()
    cancelled = _confirm_close_with_running_jobs(None, event, [{"name": "x", "status": "done"}])
    assert cancelled is False
    event.ignore.assert_not_called()


def test_confirm_close_running_job_user_says_no_cancels(qapp, monkeypatch):
    from SciQLop.core.ui.mainwindow import _confirm_close_with_running_jobs
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.No)
    event = MagicMock()
    cancelled = _confirm_close_with_running_jobs(
        None, event, [{"name": "11-year build", "status": "running"}])
    assert cancelled is True
    event.ignore.assert_called_once()


def test_confirm_close_running_job_user_says_yes_proceeds(qapp, monkeypatch):
    from SciQLop.core.ui.mainwindow import _confirm_close_with_running_jobs
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.Yes)
    event = MagicMock()
    cancelled = _confirm_close_with_running_jobs(
        None, event, [{"name": "11-year build", "status": "running"}])
    assert cancelled is False
    event.ignore.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest --no-xvfb tests/test_mainwindow_close.py -k confirm_close -q`
Expected: FAIL — `ImportError: cannot import name '_confirm_close_with_running_jobs'`.

- [ ] **Step 3: Write minimal implementation**

In `SciQLop/core/ui/mainwindow.py`, add the module-level function (near the top, after imports — needs `QMessageBox` imported from `PySide6.QtWidgets`, add it to the existing `PySide6.QtWidgets` import line if not already present):

```python
def _confirm_close_with_running_jobs(parent, event, jobs: list) -> bool:
    """Warn if any job is still running. Returns True if the close was
    cancelled (event.ignore() already called)."""
    from PySide6.QtWidgets import QMessageBox
    running = [j for j in jobs if j.get("status") == "running"]
    if not running:
        return False
    names = ", ".join(j["name"] for j in running)
    reply = QMessageBox.question(
        parent, "Jobs still running",
        f"{len(running)} job(s) are still running and will continue in the "
        f"background: {names}. Close anyway?",
        QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
    if reply == QMessageBox.No:
        event.ignore()
        return True
    return False
```

Modify `SciQLopMainWindow.closeEvent` (currently at line 475-483) to check jobs first, and add the small wiring method:

```python
    def closeEvent(self, event: QCloseEvent):
        if not getattr(self, '_closing', False) and self._warn_if_jobs_running(event):
            return
        if not getattr(self, '_closing', False):
            self._closing = True
            if self._schedule_async_close():
                event.ignore()
                return
            self._close_plugins_sync()
        workspaces_manager_instance().quit()
        super().closeEvent(event)

    def _warn_if_jobs_running(self, event: QCloseEvent) -> bool:
        from SciQLop.components.jobs.backend.jobs_backend import jobs_backend_instance
        return _confirm_close_with_running_jobs(self, event, jobs_backend_instance().list_jobs())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_mainwindow_close.py -q`
Expected: PASS (5 tests: 2 pre-existing `_usable_event_loop` tests + 3 new).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/core/ui/mainwindow.py tests/test_mainwindow_close.py
git commit -m "feat(jobs): warn before closing SciQLop with jobs still running"
```

---

### Task 6: suite sanity + full registration check

**Files:** Test only (no source change unless a regression surfaces).

- [ ] **Step 1: Run every new/touched test file together**

Run: `uv run pytest --no-xvfb tests/test_job_record.py tests/test_jobs_backend.py tests/test_user_api_jobs.py tests/test_jobs_tools_registration.py tests/test_mainwindow_close.py -q`
Expected: PASS (all — 5 + 9 + 5 + 7 + 5 = 31 tests).

- [ ] **Step 2: Confirm the four new tools enumerate with correct gating**

Run:
```bash
QT_QPA_PLATFORM=offscreen uv run python - <<'PY'
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication
app = QApplication.instance() or QApplication([])
import SciQLop.components.agents.tools._builder as b
tools = {t["name"]: t.get("gated", False) for t in b.build_sciqlop_tools(MagicMock())}
assert tools.get("sciqlop_submit_job") is True, tools
assert tools.get("sciqlop_cancel_job") is True, tools
assert tools.get("sciqlop_job_status") is False, tools
assert tools.get("sciqlop_list_jobs") is False, tools
print("OK:", {k: tools[k] for k in ("sciqlop_submit_job", "sciqlop_cancel_job", "sciqlop_job_status", "sciqlop_list_jobs")})
print("total tools:", len(tools))
PY
```
Expected: `OK: {'sciqlop_submit_job': True, 'sciqlop_cancel_job': True, 'sciqlop_job_status': False, 'sciqlop_list_jobs': False}` and `total tools: 32`.

- [ ] **Step 3: Commit (only if fixups were needed)**

```bash
git add -A && git commit -m "test(jobs): suite sanity for the jobs component"
```

## Self-Review

**Spec coverage:**
- Layer stack (component → user_api → agent tools, no `ui/` scaffolding) → Tasks 1-4. ✅
- Detached OS-level launch (`start_new_session=True`, `stdin=DEVNULL`, wrapper script writing log+marker) → Task 2. ✅
- Status computed not stored (done/running/crashed) → Task 1 (`compute_status`), consumed by Task 2. ✅
- TOML job record mirrors `WorkspaceManifest` → Task 1. ✅
- `JobsBackend` singleton mirrors `workspaces_manager_instance()` → Task 2 (`jobs_backend_instance`). ✅
- Reconciliation on construction (survives restart) → Task 2 (`_reconcile`, tested via `test_reconciliation_loads_existing_records_on_construction`). ✅
- Signals (`job_added`, `job_status_changed`) for future UI → Task 2. ✅
- `user_api.jobs` thin wrapper → Task 3. ✅
- 4 agent tools, correct gating, correct list placement → Task 4. ✅
- No-workspace raises cleanly, agent layer's existing generic exception handler covers it → Task 2 Global-Constraints note + `test_no_workspace_raises_runtime_error`; not separately re-tested at the tool layer since `_text_tool`'s catch-all (unchanged, pre-existing code) already covers every tool uniformly. ⚠️ Cannot verify tool-layer behavior from a new test without duplicating existing `_text_tool` coverage — acceptable, this is exactly the same guarantee every other gated tool in this codebase already relies on.
- Close-time warning, reuses existing deferred-close idiom, testable in isolation → Task 5. ✅
- One real-subprocess integration test → Task 2 (`test_real_detached_subprocess_writes_marker_and_log`). ✅

**Placeholder scan:** No TBD/TODO; every code step is complete. ✅

**Type consistency:** `JobsBackend(workspace_dir_getter, parent=None)` constructor signature identical across Task 2's tests and Task 2's `jobs_backend_instance()`; `Job` fields identical between Task 1 and Task 2's `submit_job`/`_reconcile`; `job_status`/`list_jobs` return-dict shape (`id/name/command/submitted_at/status/exit_code/finished_at/log_tail`) identical across Tasks 2, 3, 4; `_confirm_close_with_running_jobs(parent, event, jobs)` signature identical between its definition and `_warn_if_jobs_running`'s call site in Task 5. ✅

**Deviation from spec, flagged:** the spec's file tree showed `components/agents/tools/jobs.py` as a separate module; the plan instead adds the 4 tool factories directly into `_builder.py`, matching the established precedent for thin-delegation tools (`_install_package_tool`, `_create_panel_tool`) rather than tools with real internal logic (`fetch.py`, `describe.py`, which DO get their own file). This preserves the spec's intent (thin delegation to `user_api.jobs`, no logic duplicated) while following the codebase's actual convention more precisely — discovered during planning by checking the exact precedent.
