import pytest
from SciQLop.components.jupyter.kernel.manager import KernelManager


@pytest.mark.timeout(30)
def test_run_cell_capture_returns_rich_fields(qtbot):
    km = KernelManager()
    km.start(port=0)
    try:
        fut = km.run_cell_capture("print('hi')\n1 + 2")
        res = fut.result(timeout=10)
        assert res["success"] is True
        assert res["stdout"] == "hi\n"
        assert res["result"] == "3"            # repr of last expression
        assert isinstance(res["displays"], list)  # rich display_data outputs
        assert isinstance(res["execution_count"], int) and res["execution_count"] >= 1
    finally:
        km.shutdown()


@pytest.mark.timeout(30)
def test_run_cell_capture_reports_error(qtbot):
    km = KernelManager()
    km.start(port=0)
    try:
        res = km.run_cell_capture("raise ValueError('boom')").result(timeout=10)
        assert res["success"] is False
        assert "ValueError" in res["error"] and "boom" in res["error"]
        assert res["traceback"]                # non-empty list of strings
    finally:
        km.shutdown()


@pytest.mark.timeout(30)
def test_run_cell_capture_keeps_user_out_prompt_lookalike(qtbot):
    km = KernelManager()
    km.start(port=0)
    try:
        # a printed line that looks like a result echo must NOT be stripped,
        # and the real result echo must NOT leak into stdout
        res = km.run_cell_capture("print('Out[5]: hello')\n7").result(timeout=10)
        assert "Out[5]: hello" in res["stdout"]   # user output preserved
        assert res["result"] == "7"
        assert "Out[" not in res["stdout"].split("Out[5]: hello", 1)[1]  # no echo leak after it
    finally:
        km.shutdown()
