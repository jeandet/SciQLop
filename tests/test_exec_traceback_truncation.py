def test_short_traceback_unchanged(qtbot):
    from SciQLop.components.agents.tools._builder import _truncate_traceback
    txt = "\n".join(f"line {i}" for i in range(10))
    assert _truncate_traceback(txt) == txt


def test_long_traceback_keeps_head_and_tail(qtbot):
    from SciQLop.components.agents.tools._builder import _truncate_traceback
    txt = "\n".join(f"line {i}" for i in range(200))
    out = _truncate_traceback(txt)
    assert "line 0" in out            # head kept
    assert "line 199" in out          # tail (the actual exception) kept
    assert "line 100" not in out      # middle elided
    assert "elided" in out
    assert len(out.splitlines()) < 60


def test_format_exec_result_truncates_error(qtbot):
    from SciQLop.components.agents.tools._builder import _format_exec_result
    big = "\n".join(f"trace {i}" for i in range(200))
    out = _format_exec_result({"success": False, "error": big})
    assert "elided" in out and "trace 199" in out
