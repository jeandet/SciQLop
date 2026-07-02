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
