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
