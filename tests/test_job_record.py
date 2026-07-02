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
