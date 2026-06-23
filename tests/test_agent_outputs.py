"""Pure unit test for _outputs.to_nbformat — no Qt, no kernel.

Imported via importlib to bypass tools/__init__.py which eagerly pulls in
Qt-dependent code (context, _builder). _outputs itself has no Qt dependency.
"""
import importlib.util
from pathlib import Path

_mod_path = Path(__file__).parent.parent / "SciQLop" / "components" / "agents" / "tools" / "_outputs.py"
_spec = importlib.util.spec_from_file_location("_outputs", _mod_path)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
to_nbformat = _mod.to_nbformat


def _cap(**over):
    base = {"stdout": "", "stderr": "", "result": None, "displays": [],
            "success": True, "error": None, "traceback": [], "execution_count": 5}
    base.update(over)
    return base


def test_stream_result_and_display():
    out = to_nbformat(_cap(
        stdout="hello\n", result="42",
        displays=[{"data": {"text/plain": "<Figure>", "image/png": "BASE64"},
                   "metadata": {}}],
    ))
    types = [o["output_type"] for o in out]
    assert "stream" in types and "execute_result" in types and "display_data" in types
    stream = next(o for o in out if o["output_type"] == "stream")
    assert stream["name"] == "stdout" and stream["text"] == "hello\n"
    er = next(o for o in out if o["output_type"] == "execute_result")
    assert er["data"]["text/plain"] == "42" and er["execution_count"] == 5
    dd = next(o for o in out if o["output_type"] == "display_data")
    assert dd["data"]["image/png"] == "BASE64"


def test_error_output():
    out = to_nbformat(_cap(success=False, error="ValueError: boom",
                           traceback=["Traceback...", "ValueError: boom"]))
    err = next(o for o in out if o["output_type"] == "error")
    assert err["ename"] == "ValueError" and err["evalue"] == "boom"
    assert err["traceback"] == ["Traceback...", "ValueError: boom"]


def test_no_outputs_when_empty():
    assert to_nbformat(_cap()) == []
