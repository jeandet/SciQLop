from unittest.mock import patch
import pytest

from SciQLop.user_api.magics.job_magic import job_magic, SUBCOMMANDS


class TestJobSubmit:
    @patch("SciQLop.user_api.jobs.submit_job")
    def test_submit_plain_command(self, mock_submit, capsys):
        mock_submit.return_value = "abc123"
        job_magic("submit sleep 5 && echo hi")
        mock_submit.assert_called_once_with("sleep 5 && echo hi", "")
        assert "abc123" in capsys.readouterr().out

    @patch("SciQLop.user_api.jobs.submit_job")
    def test_submit_with_name(self, mock_submit, capsys):
        mock_submit.return_value = "abc123"
        job_magic("submit --name mybuild python build.py")
        mock_submit.assert_called_once_with("python build.py", "mybuild")
        assert "mybuild" in capsys.readouterr().out

    def test_submit_missing_command_raises(self):
        with pytest.raises(Exception, match="Usage"):
            job_magic("submit")

    def test_submit_name_without_command_raises(self):
        with pytest.raises(Exception, match="Usage"):
            job_magic("submit --name onlyname")


class TestJobStatus:
    @patch("SciQLop.user_api.jobs.job_status")
    def test_status_prints_fields(self, mock_status, capsys):
        mock_status.return_value = {
            "id": "abc123", "name": "build", "command": "make",
            "status": "done", "submitted_at": "2026-07-03T10:00:00",
            "finished_at": "2026-07-03T10:05:00", "exit_code": 0,
            "log_tail": "line1\nline2",
        }
        job_magic("status abc123")
        out = capsys.readouterr().out
        assert "abc123" in out
        assert "done" in out
        assert "line1" in out

    @patch("SciQLop.user_api.jobs.job_status")
    def test_status_no_log_tail_omits_header(self, mock_status, capsys):
        mock_status.return_value = {
            "id": "abc123", "name": "build", "command": "make",
            "status": "running", "submitted_at": "2026-07-03T10:00:00",
            "finished_at": None, "exit_code": None, "log_tail": "",
        }
        job_magic("status abc123")
        assert "--- log ---" not in capsys.readouterr().out

    @patch("SciQLop.user_api.jobs.job_status")
    def test_status_unknown_id_raises(self, mock_status):
        mock_status.side_effect = KeyError("abc123")
        with pytest.raises(Exception, match="No such job"):
            job_magic("status abc123")

    def test_status_missing_id_raises(self):
        with pytest.raises(Exception, match="Usage"):
            job_magic("status")


class TestJobList:
    @patch("SciQLop.user_api.jobs.list_jobs")
    def test_list_shows_all_jobs_sorted(self, mock_list, capsys):
        mock_list.return_value = [
            {"id": "b", "name": "second", "status": "running",
             "submitted_at": "2026-07-03T11:00:00"},
            {"id": "a", "name": "first", "status": "done",
             "submitted_at": "2026-07-03T10:00:00"},
        ]
        job_magic("list")
        out = capsys.readouterr().out
        assert "first" in out and "second" in out
        assert out.index("first") < out.index("second")

    @patch("SciQLop.user_api.jobs.list_jobs")
    def test_list_empty(self, mock_list, capsys):
        mock_list.return_value = []
        job_magic("list")
        assert "No jobs" in capsys.readouterr().out

    @patch("SciQLop.user_api.jobs.list_jobs")
    def test_bare_job_defaults_to_list(self, mock_list, capsys):
        mock_list.return_value = []
        job_magic("")
        assert "No jobs" in capsys.readouterr().out


class TestJobCancel:
    @patch("SciQLop.user_api.jobs.cancel_job")
    def test_cancel_delegates(self, mock_cancel, capsys):
        job_magic("cancel abc123")
        mock_cancel.assert_called_once_with("abc123")
        assert "Cancelled" in capsys.readouterr().out

    @patch("SciQLop.user_api.jobs.cancel_job")
    def test_cancel_unknown_id_raises(self, mock_cancel):
        mock_cancel.side_effect = KeyError("abc123")
        with pytest.raises(Exception, match="No such job"):
            job_magic("cancel abc123")

    def test_cancel_missing_id_raises(self):
        with pytest.raises(Exception, match="Usage"):
            job_magic("cancel")


class TestJobDispatch:
    def test_help(self, capsys):
        job_magic("help")
        out = capsys.readouterr().out
        for subcmd in SUBCOMMANDS:
            assert subcmd in out

    def test_unknown_subcommand_raises(self):
        with pytest.raises(Exception, match="Unknown subcommand"):
            job_magic("nonexistent")
