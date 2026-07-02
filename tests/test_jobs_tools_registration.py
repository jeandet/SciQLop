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
