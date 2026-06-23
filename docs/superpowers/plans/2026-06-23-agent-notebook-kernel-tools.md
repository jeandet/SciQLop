# Agent Notebook & Kernel Tools — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the in-app Claude agent run a notebook cell and see its outputs, read existing cell outputs, introspect the live kernel, and interrupt a running cell — all on the in-process embedded kernel.

**Architecture:** A small jupyqt PR adds a clean `EmbeddedJupyter.interrupt()` + `kernel_thread` accessor so SciQLop stops touching privates. SciQLop's `KernelManager` gains rich cell capture + interrupt; four new agent tools wire them to the agent surface. Notebook write-back goes through a `NotebookSink` seam (disk now, RTC later); JupyterLab reloads via its file-watcher.

**Tech Stack:** Python 3.13, jupyqt (embedded IPython kernel), nbformat, IPython capture, the SciQLop agent tool builder, pytest / pytest-qt.

---

## Prerequisites & deployment chain

- The jupyqt changes (Task 1) live in `/var/home/jeandet/Documents/prog/jupyqt`. After committing them there, **install jupyqt editable into SciQLop's venv** so Tasks 2–10 can use the new API:
  `uv pip install -e /var/home/jeandet/Documents/prog/jupyqt` (run from the SciQLop dir).
- All SciQLop commands use `uv run`; run pytest with `--no-xvfb`.
- The SciQLop branch for this work is `feat/agent-notebook-kernel-tools` (already checked out).

## File structure

| File | Responsibility |
|---|---|
| `jupyqt: src/jupyqt/api.py` (modify) | `EmbeddedJupyter.interrupt()` + `kernel_thread` property |
| `SciQLop/components/jupyter/kernel/manager.py` (modify) | `run_cell_capture()`, `interrupt()`, public `kernel_thread` use |
| `SciQLop/components/agents/tools/_outputs.py` (new) | captured run → nbformat output dicts (pure) |
| `SciQLop/components/agents/tools/_notebook_sink.py` (new) | `NotebookSink` Protocol + `DiskNotebookSink` |
| `SciQLop/components/agents/tools/notebooks.py` (modify) | `run_cell()` orchestration; `read_notebook` outputs |
| `SciQLop/components/agents/tools/kernel.py` (new) | `kernel_vars()`, `inspect()` |
| `SciQLop/components/agents/tools/_builder.py` (modify) | register the 4 tools |

---

### Task 1: jupyqt — clean `EmbeddedJupyter.interrupt()` + `kernel_thread`

**Repo:** `/var/home/jeandet/Documents/prog/jupyqt` (use `uv run`). Branch off `main`.

**Files:**
- Modify: `src/jupyqt/api.py`
- Test: `tests/test_api.py` (create if absent; otherwise append)

- [ ] **Step 1: Branch**

```bash
cd /var/home/jeandet/Documents/prog/jupyqt
git checkout main && git checkout -b feat/embedded-jupyter-interrupt
```

- [ ] **Step 2: Write the failing test** (`tests/test_api.py`)

```python
from __future__ import annotations

from jupyqt.api import EmbeddedJupyter


def test_kernel_thread_accessor_and_interrupt():
    ej = EmbeddedJupyter()
    # kernel_thread is the same object used internally, exposed read-only
    assert ej.kernel_thread is ej._kernel_thread
    # interrupt must not raise even before the thread is started (no-op)
    ej.interrupt()
```

- [ ] **Step 3: Run it, confirm failure**

Run: `uv run pytest tests/test_api.py::test_kernel_thread_accessor_and_interrupt -p no:xdist -q`
Expected: FAIL — `AttributeError: 'EmbeddedJupyter' object has no attribute 'kernel_thread'`.

- [ ] **Step 4: Implement** in `src/jupyqt/api.py`. Add next to the existing `shell` property (around line 49):

```python
    @property
    def kernel_thread(self) -> KernelThread:
        """The background KernelThread that owns the shell after start()."""
        return self._kernel_thread

    def interrupt(self) -> None:
        """Raise KeyboardInterrupt in the kernel thread to stop a running cell."""
        self._kernel_thread.interrupt()
```

(`KernelThread` is already imported in `api.py`; `KernelThread.interrupt()` already exists and is a no-op when the thread has no id.)

- [ ] **Step 5: Run it, confirm pass + full suite**

Run: `uv run pytest tests/test_api.py -p no:xdist -q` → expect pass.
Run: `uv run pytest -q` → expect all green (70+ tests).

- [ ] **Step 6: Commit, push, PR**

```bash
git add src/jupyqt/api.py tests/test_api.py
git commit -m "feat(api): expose EmbeddedJupyter.interrupt() and kernel_thread

Gives embedders a clean public way to interrupt a running cell and to
schedule work on the kernel loop, instead of reaching private attributes.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
git push -u origin feat/embedded-jupyter-interrupt
gh pr create --repo SciQLop/jupyqt --base main --head jeandet:feat/embedded-jupyter-interrupt \
  --title "feat(api): expose EmbeddedJupyter.interrupt() and kernel_thread" \
  --body "Adds a public \`interrupt()\` and a read-only \`kernel_thread\` accessor so embedders (SciQLop) stop reaching private attributes. Test-first; full suite green.

🤖 Generated with [Claude Code](https://claude.com/claude-code)"
```

- [ ] **Step 7: Install editable into SciQLop's venv**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
uv pip install -e /var/home/jeandet/Documents/prog/jupyqt
uv run python -c "from jupyqt import EmbeddedJupyter; assert hasattr(EmbeddedJupyter, 'interrupt') and hasattr(EmbeddedJupyter, 'kernel_thread'); print('jupyqt API present')"
```
Expected: `jupyqt API present`.

---

### Task 2: `KernelManager.interrupt()` + public `kernel_thread`

**Files:**
- Modify: `SciQLop/components/jupyter/kernel/manager.py`
- Test: `tests/test_kernel_manager_interrupt.py`

- [ ] **Step 1: Write the failing test** (`tests/test_kernel_manager_interrupt.py`)

```python
import time
import pytest
from SciQLop.components.jupyter.kernel.manager import KernelManager


@pytest.mark.timeout(30)
def test_interrupt_stops_a_long_cell(qtbot):
    km = KernelManager()
    km.start(port=0)
    try:
        fut = km.submit_cell("import time\nfor _ in range(100):\n    time.sleep(0.1)")
        qtbot.wait(300)              # let the cell get going
        km.interrupt()               # must raise KeyboardInterrupt in the cell
        result = fut.result(timeout=10)
        assert result["success"] is False
        assert "KeyboardInterrupt" in (result["error"] or "")
    finally:
        km.shutdown()
```

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_kernel_manager_interrupt.py -q --no-xvfb`
Expected: FAIL — `AttributeError: 'KernelManager' object has no attribute 'interrupt'`.

- [ ] **Step 3: Implement** in `manager.py`. Add the method to `KernelManager` (next to `submit_cell`), and switch `submit_cell` to the public accessor:

```python
    def interrupt(self) -> None:
        """Raise KeyboardInterrupt in the kernel thread to stop a running cell."""
        self._jupyter.interrupt()
```

In `submit_cell`, replace `self._jupyter._kernel_thread.loop` with `self._jupyter.kernel_thread.loop`.

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_kernel_manager_interrupt.py -q --no-xvfb`
Expected: PASS (1 passed). (`pytest-timeout` provides `@pytest.mark.timeout`; if unknown, drop the decorator.)

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/jupyter/kernel/manager.py tests/test_kernel_manager_interrupt.py
git commit -m "feat(kernel): KernelManager.interrupt() via public jupyqt API

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `KernelManager.run_cell_capture()` — rich output

**Files:**
- Modify: `SciQLop/components/jupyter/kernel/manager.py`
- Test: `tests/test_run_cell_capture.py`

- [ ] **Step 1: Write the failing test** (`tests/test_run_cell_capture.py`)

```python
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
```

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_run_cell_capture.py -q --no-xvfb`
Expected: FAIL — `AttributeError: ... 'run_cell_capture'`.

- [ ] **Step 3: Implement** in `manager.py`. Add a rich capture coroutine + counter, mirroring `_run_and_capture` but surfacing displays/traceback/execution_count. Add near `_run_and_capture`:

```python
import traceback as _traceback


async def _run_and_capture_rich(shell, code: str, execution_count: int) -> Dict[str, Any]:
    """Like _run_and_capture but also returns rich display outputs, a traceback,
    and the execution_count, for notebook-style write-back."""
    from IPython.utils.capture import capture_output

    try:
        transformed = shell.transform_cell(code)
    except Exception:
        transformed = code
    with capture_output() as cap:
        if shell.should_run_async(code, transformed_cell=transformed):
            result = await shell.run_cell_async(code, store_history=False)
        else:
            result = shell.run_cell(code, store_history=False)
    error = None
    tb: list = []
    if not result.success:
        err = result.error_in_exec or result.error_before_exec
        error = f"{type(err).__name__}: {err}" if err is not None else "cell failed"
        if err is not None:
            tb = _traceback.format_exception(type(err), err, err.__traceback__)
    displays = [{"data": dict(o.data), "metadata": dict(o.metadata or {})}
                for o in cap.outputs]
    return {
        "stdout": cap.stdout or "",
        "stderr": cap.stderr or "",
        "result": repr(result.result) if result.result is not None else None,
        "displays": displays,
        "success": bool(result.success),
        "error": error,
        "traceback": tb,
        "execution_count": execution_count,
    }
```

Add to `KernelManager.__init__`: `self._exec_count = 0`. Add the method:

```python
    def run_cell_capture(self, code: str) -> concurrent.futures.Future:
        """Schedule ``code`` on the kernel thread and return a Future resolving to
        a rich captured-output dict (stdout/stderr/result/displays/success/error/
        traceback/execution_count). Await via ``asyncio.wrap_future``."""
        loop = self._jupyter.kernel_thread.loop
        if loop is None:
            raise RuntimeError("kernel thread is not running")
        self._exec_count += 1
        return asyncio.run_coroutine_threadsafe(
            _run_and_capture_rich(self.shell, code, self._exec_count), loop,
        )
```

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_run_cell_capture.py -q --no-xvfb`
Expected: PASS (2 passed). If `res["result"]` for `1 + 2` comes back as a display rather than `result.result`, adjust the assertion to read it from `displays` — but `run_cell` returns the last-expression value in `result.result`, so this should hold.

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/jupyter/kernel/manager.py tests/test_run_cell_capture.py
git commit -m "feat(kernel): run_cell_capture() with rich outputs + execution_count

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `_outputs.to_nbformat` — captured run → nbformat outputs

**Files:**
- Create: `SciQLop/components/agents/tools/_outputs.py`
- Test: `tests/test_agent_outputs.py`

- [ ] **Step 1: Write the failing test** (`tests/test_agent_outputs.py`)

```python
from SciQLop.components.agents.tools._outputs import to_nbformat


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
```

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_agent_outputs.py -q --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** `SciQLop/components/agents/tools/_outputs.py`:

```python
"""Turn a KernelManager.run_cell_capture() dict into nbformat output dicts."""
from __future__ import annotations

from typing import Any, Dict, List


def _split_error(error: str) -> tuple[str, str]:
    if error and ": " in error:
        ename, evalue = error.split(": ", 1)
        return ename, evalue
    return (error or "Error"), ""


def to_nbformat(captured: Dict[str, Any]) -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    if captured.get("stdout"):
        outputs.append({"output_type": "stream", "name": "stdout",
                        "text": captured["stdout"]})
    if captured.get("stderr"):
        outputs.append({"output_type": "stream", "name": "stderr",
                        "text": captured["stderr"]})
    for d in captured.get("displays", []):
        outputs.append({"output_type": "display_data",
                        "data": d.get("data", {}), "metadata": d.get("metadata", {})})
    if captured.get("result") is not None:
        outputs.append({"output_type": "execute_result",
                        "execution_count": captured.get("execution_count"),
                        "data": {"text/plain": captured["result"]}, "metadata": {}})
    if not captured.get("success", True):
        ename, evalue = _split_error(captured.get("error") or "")
        outputs.append({"output_type": "error", "ename": ename, "evalue": evalue,
                        "traceback": list(captured.get("traceback") or [])})
    return outputs
```

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_agent_outputs.py -q --no-xvfb`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/_outputs.py tests/test_agent_outputs.py
git commit -m "feat(agents): captured run -> nbformat outputs

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `NotebookSink` + `DiskNotebookSink`

**Files:**
- Create: `SciQLop/components/agents/tools/_notebook_sink.py`
- Test: `tests/test_notebook_sink.py`

- [ ] **Step 1: Write the failing test** (`tests/test_notebook_sink.py`)

```python
import nbformat
from SciQLop.components.agents.tools._notebook_sink import DiskNotebookSink


def test_disk_sink_writes_outputs_and_count(tmp_path):
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell("1+1")]
    p = tmp_path / "n.ipynb"
    nbformat.write(nb, str(p))

    outputs = [{"output_type": "execute_result", "execution_count": 7,
                "data": {"text/plain": "2"}, "metadata": {}}]
    DiskNotebookSink().write_outputs(str(p), 0, outputs, 7)

    reloaded = nbformat.read(str(p), as_version=4)
    cell = reloaded.cells[0]
    assert cell["execution_count"] == 7
    assert cell["outputs"][0]["data"]["text/plain"] == "2"
```

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_notebook_sink.py -q --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** `SciQLop/components/agents/tools/_notebook_sink.py`:

```python
"""Where run-cell outputs are written. Disk now; an RTC-backed sink can replace
DiskNotebookSink later without touching the run_cell tool."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Protocol


class NotebookSink(Protocol):
    def write_outputs(self, rel_path: str, index: int,
                      outputs: List[Dict[str, Any]], execution_count: int) -> None:
        ...


class DiskNotebookSink:
    """Write cell outputs + execution_count into the .ipynb on disk. JupyterLab's
    file-watcher reloads it."""

    def __init__(self, resolve: Any = None) -> None:
        # resolve(rel_path) -> absolute Path; defaults to notebooks._resolve_notebook
        self._resolve = resolve

    def _path(self, rel_path: str) -> Path:
        if self._resolve is not None:
            return Path(self._resolve(rel_path))
        from . import notebooks
        return notebooks._resolve_notebook(rel_path)

    def write_outputs(self, rel_path: str, index: int,
                      outputs: List[Dict[str, Any]], execution_count: int) -> None:
        import nbformat
        path = self._path(rel_path)
        nb = nbformat.read(str(path), as_version=4)
        cell = nb.cells[index]
        cell["outputs"] = outputs
        cell["execution_count"] = execution_count
        nbformat.write(nb, str(path))
```

(The `tmp_path` test passes an absolute path that `_resolve_notebook` returns as-is for existing absolute paths; if `_resolve_notebook` rejects absolute paths, the test instead constructs `DiskNotebookSink(resolve=lambda p: p)`. Verify `_resolve_notebook`'s behavior and pick the matching form.)

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_notebook_sink.py -q --no-xvfb`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/_notebook_sink.py tests/test_notebook_sink.py
git commit -m "feat(agents): NotebookSink seam + DiskNotebookSink (RTC-ready)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `notebooks.run_cell` + `sciqlop_run_notebook_cell` tool

**Files:**
- Modify: `SciQLop/components/agents/tools/notebooks.py`
- Modify: `SciQLop/components/agents/tools/_builder.py`
- Test: `tests/test_run_notebook_cell.py`

- [ ] **Step 1: Write the failing test** (`tests/test_run_notebook_cell.py`)

```python
import nbformat
import pytest
from SciQLop.components.jupyter.kernel.manager import KernelManager
from SciQLop.components.agents.tools import notebooks


@pytest.mark.timeout(40)
def test_run_cell_writes_outputs_and_summarizes(tmp_path, qtbot, monkeypatch):
    nb = nbformat.v4.new_notebook()
    nb.cells = [nbformat.v4.new_code_cell("print('hi')\n6 * 7")]
    p = tmp_path / "nb.ipynb"
    nbformat.write(nb, str(p))
    monkeypatch.setattr(notebooks, "_resolve_notebook", lambda rel: p)

    km = KernelManager()
    km.start(port=0)
    try:
        summary = notebooks.run_cell(km, str(p), 0).result(timeout=20)
        assert "42" in summary and "[1]" in summary    # result + execution_count
        reloaded = nbformat.read(str(p), as_version=4)
        outs = reloaded.cells[0]["outputs"]
        assert any(o["output_type"] == "stream" and "hi" in o["text"] for o in outs)
        assert reloaded.cells[0]["execution_count"] == 1
    finally:
        km.shutdown()
```

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_run_notebook_cell.py -q --no-xvfb`
Expected: FAIL — `AttributeError: ... 'run_cell'`.

- [ ] **Step 3: Implement.** In `notebooks.py` add (uses the rich capture + sink + outputs):

```python
def run_cell(km, rel_path: str, index: int, sink=None):
    """Run a code cell on the embedded kernel, write its outputs back via the
    sink, and return a concurrent.futures.Future[str] summary. ``km`` is the
    KernelManager; ``sink`` defaults to DiskNotebookSink."""
    import nbformat
    from ._notebook_sink import DiskNotebookSink
    from ._outputs import to_nbformat
    from concurrent.futures import Future

    nb_path = _resolve_notebook(rel_path)
    nb = nbformat.read(str(nb_path), as_version=4)
    if index < 0 or index >= len(nb.cells):
        f: Future = Future()
        f.set_result(f"error: index {index} out of range (0..{len(nb.cells) - 1})")
        return f
    cell = nb.cells[index]
    if cell.get("cell_type") != "code":
        f = Future()
        f.set_result(f"error: cell {index} is {cell.get('cell_type')}, not code")
        return f
    source = cell.get("source", "")
    if isinstance(source, list):
        source = "".join(source)
    the_sink = sink or DiskNotebookSink()

    cap_future = km.run_cell_capture(source)
    out: Future = Future()

    def _done(cf):
        try:
            captured = cf.result()
            outputs = to_nbformat(captured)
            the_sink.write_outputs(rel_path, index, outputs, captured["execution_count"])
            out.set_result(_summarize(captured))
        except Exception as e:  # noqa: BLE001
            out.set_result(f"error: {type(e).__name__}: {e}")

    cap_future.add_done_callback(_done)
    return out


def _summarize(captured) -> str:
    n = captured.get("execution_count")
    head = f"[{n}] " + ("ok" if captured.get("success") else "error")
    parts = [head]
    if captured.get("stdout"):
        parts.append("stdout: " + captured["stdout"].strip()[:500])
    if captured.get("result") is not None:
        parts.append("result: " + str(captured["result"])[:500])
    if not captured.get("success"):
        parts.append(captured.get("error") or "cell failed")
    return "\n".join(parts)
```

In `_builder.py`, add the tool inside `_notebook_write_tools()` (find it; it returns the file-based notebook write tools), or add a dedicated helper and include it in `_write_tools`:

```python
def _run_notebook_cell_tool() -> Dict[str, Any]:
    async def _run(payload: Dict[str, Any]) -> Dict[str, Any]:
        km = _kernel_manager()
        if km is None:
            return _error_content("embedded IPython kernel is not available")
        from . import notebooks
        try:
            summary = await asyncio.wrap_future(
                notebooks.run_cell(km, str(payload["path"]), int(payload["index"])),
            )
        except Exception as e:  # noqa: BLE001
            return _error_content(f"{type(e).__name__}: {e}")
        return {"content": [{"type": "text", "text": summary}]}

    return {
        "name": "sciqlop_run_notebook_cell",
        "description": (
            "Run a code cell in a workspace notebook on the SciQLop embedded "
            "kernel (shared with JupyterLab — variables persist). Writes the "
            "cell's outputs back into the .ipynb (JupyterLab reloads) and returns "
            "a summary. path is workspace-relative; index is 0-based."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"path": {"type": "string"}, "index": {"type": "integer"}},
            "required": ["path", "index"],
        },
        "handler": _run,
        "gated": True,
    }
```

Register it: add `_run_notebook_cell_tool()` to the list returned by `_write_tools` (the `return [set_time_range, _create_panel_tool(main_window), _exec_python_tool()] + _notebook_write_tools()` line — append `+ [_run_notebook_cell_tool()]`).

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_run_notebook_cell.py -q --no-xvfb`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/notebooks.py SciQLop/components/agents/tools/_builder.py tests/test_run_notebook_cell.py
git commit -m "feat(agents): sciqlop_run_notebook_cell (run + write-back + summary)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: `read_notebook` renders outputs

**Files:**
- Modify: `SciQLop/components/agents/tools/notebooks.py`
- Test: `tests/test_read_notebook_outputs.py`

- [ ] **Step 1: Write the failing test** (`tests/test_read_notebook_outputs.py`)

```python
import nbformat
from SciQLop.components.agents.tools import notebooks


def test_read_notebook_includes_outputs(tmp_path, monkeypatch):
    nb = nbformat.v4.new_notebook()
    cell = nbformat.v4.new_code_cell("print('x')")
    cell["outputs"] = [
        {"output_type": "stream", "name": "stdout", "text": "x\n"},
        {"output_type": "error", "ename": "ValueError", "evalue": "boom",
         "traceback": ["tb1", "tb2"]},
        {"output_type": "display_data", "data": {"image/png": "B64"}, "metadata": {}},
    ]
    nb.cells = [cell]
    p = tmp_path / "n.ipynb"
    nbformat.write(nb, str(p))
    monkeypatch.setattr(notebooks, "_resolve_notebook", lambda rel: p)

    text = notebooks.read_notebook(str(p))
    assert "x\n" in text or "x" in text          # stream text
    assert "ValueError: boom" in text             # error
    assert "[image: image/png]" in text           # image marker, not the base64
    assert "B64" not in text
```

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_read_notebook_outputs.py -q --no-xvfb`
Expected: FAIL — outputs not rendered (assertions miss).

- [ ] **Step 3: Implement.** In `notebooks.py`, extend `_render_cell` to append rendered outputs for code cells. Replace the `return [header, "", body, ""]` tail with:

```python
    parts = [header, "", body]
    if kind == "code":
        parts += _render_outputs(cell.get("outputs", []))
    parts.append("")
    return parts


_MAX_OUTPUT_CHARS = 2000


def _render_outputs(outputs) -> List[str]:
    if not outputs:
        return []
    lines = ["", "**outputs:**"]
    for o in outputs:
        ot = o.get("output_type")
        if ot == "stream":
            lines.append(f"```\n{str(o.get('text',''))[:_MAX_OUTPUT_CHARS]}\n```")
        elif ot in ("execute_result", "display_data"):
            data = o.get("data", {})
            if "text/plain" in data:
                lines.append(f"```\n{str(data['text/plain'])[:_MAX_OUTPUT_CHARS]}\n```")
            for mime in data:
                if mime.startswith("image/"):
                    lines.append(f"[image: {mime}]")
        elif ot == "error":
            tb = "\n".join(o.get("traceback", []))[:_MAX_OUTPUT_CHARS]
            lines.append(f"```\n{o.get('ename','')}: {o.get('evalue','')}\n{tb}\n```")
    return lines
```

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_read_notebook_outputs.py -q --no-xvfb`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/notebooks.py tests/test_read_notebook_outputs.py
git commit -m "feat(agents): read_notebook renders cell outputs (text + image markers)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 8: `kernel.py` — `kernel_vars()` + `inspect()`

**Files:**
- Create: `SciQLop/components/agents/tools/kernel.py`
- Test: `tests/test_kernel_introspection.py`

- [ ] **Step 1: Write the failing test** (`tests/test_kernel_introspection.py`)

```python
import numpy as np
from SciQLop.components.agents.tools.kernel import kernel_vars, inspect_name


class _Shell:
    def __init__(self, ns):
        self.user_ns = ns

    def object_inspect(self, name, detail_level=0):
        if name in self.user_ns:
            return {"found": True, "type_name": type(self.user_ns[name]).__name__,
                    "string_form": repr(self.user_ns[name]), "docstring": ""}
        return {"found": False}


def test_kernel_vars_filters_and_summarizes():
    ns = {"x": 3, "arr": np.zeros((2, 3)), "_hidden": 1, "In": [], "Out": {},
          "get_ipython": lambda: None, "__name__": "__main__"}
    text = kernel_vars(_Shell(ns))
    assert "x" in text and "int" in text
    assert "arr" in text and "(2, 3)" in text         # ndarray shape summary
    assert "_hidden" not in text and "In" not in text and "get_ipython" not in text


def test_inspect_found_and_missing():
    sh = _Shell({"x": 42})
    assert "int" in inspect_name(sh, "x")
    assert "not defined" in inspect_name(sh, "nope").lower()
```

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_kernel_introspection.py -q --no-xvfb`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** `SciQLop/components/agents/tools/kernel.py`:

```python
"""Live kernel introspection for the agent: namespace listing + object inspect."""
from __future__ import annotations

import types
from typing import Any

_HIDDEN = {"In", "Out", "get_ipython", "exit", "quit", "open", "_", "__", "___",
           "_oh", "_dh", "_ih", "_sh"}
_MAX_VARS = 200
_MAX_REPR = 200


def _is_internal(name: str) -> bool:
    return name.startswith("_") or name in _HIDDEN


def _summary(value: Any) -> str:
    try:
        import numpy as np
        if isinstance(value, np.ndarray):
            return f"ndarray{tuple(value.shape)} {value.dtype}"
    except Exception:
        pass
    try:
        import pandas as pd
        if isinstance(value, pd.DataFrame):
            return f"DataFrame{tuple(value.shape)}"
    except Exception:
        pass
    if isinstance(value, (list, tuple, dict, set, str, bytes)):
        return f"len={len(value)} {type(value).__name__}"
    r = repr(value)
    return r[:_MAX_REPR] + ("…" if len(r) > _MAX_REPR else "")


def kernel_vars(shell) -> str:
    rows = []
    for name, value in list(shell.user_ns.items()):
        if _is_internal(name) or isinstance(value, types.ModuleType):
            continue
        rows.append(f"- `{name}`: {type(value).__name__} — {_summary(value)}")
        if len(rows) >= _MAX_VARS:
            break
    if not rows:
        return "kernel namespace is empty (no user variables)"
    return "# Kernel variables\n" + "\n".join(rows)


def inspect_name(shell, name: str) -> str:
    info = shell.object_inspect(name, detail_level=0)
    if not info.get("found"):
        return f"`{name}` is not defined in the kernel"
    out = [f"# `{name}`"]
    if info.get("type_name"):
        out.append(f"type: {info['type_name']}")
    if info.get("string_form"):
        out.append(f"value: {info['string_form'][:_MAX_REPR]}")
    if info.get("docstring"):
        out.append("\n" + info["docstring"][:1500])
    return "\n".join(out)
```

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_kernel_introspection.py -q --no-xvfb`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/kernel.py tests/test_kernel_introspection.py
git commit -m "feat(agents): kernel namespace listing + object inspect helpers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 9: Register `interrupt` / `kernel_vars` / `inspect` tools

**Files:**
- Modify: `SciQLop/components/agents/tools/_builder.py`
- Test: `tests/test_kernel_tools_registered.py`

- [ ] **Step 1: Write the failing test** (`tests/test_kernel_tools_registered.py`)

```python
from SciQLop.components.agents.tools._builder import build_sciqlop_tools


def test_new_kernel_tools_present():
    class _MW:  # minimal stand-in; build must not require a live window for names
        def __getattr__(self, _):
            return None
    names = {t["name"] for t in build_sciqlop_tools(_MW())}
    assert {"sciqlop_run_notebook_cell", "sciqlop_interrupt_kernel",
            "sciqlop_kernel_vars", "sciqlop_inspect"} <= names
    gated = {t["name"]: t.get("gated", False) for t in build_sciqlop_tools(_MW())}
    assert gated["sciqlop_interrupt_kernel"] is True
    assert gated["sciqlop_kernel_vars"] is False
```

(If `build_sciqlop_tools` dereferences `main_window` eagerly and the stub fails, build a real headless main window the way `tests/fixtures.py` does and use that instead — check the fixtures first.)

- [ ] **Step 2: Run it, confirm failure**

Run: `uv run pytest tests/test_kernel_tools_registered.py -q --no-xvfb`
Expected: FAIL — the three new names are missing.

- [ ] **Step 3: Implement** in `_builder.py`. Add read tools for vars/inspect and a gated interrupt tool, and register them:

```python
def _kernel_vars_tool() -> Dict[str, Any]:
    def _run(_payload: Dict[str, Any]) -> Any:
        km = _kernel_manager()
        if km is None:
            return _error_content("embedded IPython kernel is not available")
        from . import kernel
        return kernel.kernel_vars(km.shell)
    return _text_tool(
        "sciqlop_kernel_vars",
        "List the user variables currently defined in the SciQLop embedded "
        "kernel (name, type, and a short summary). Read-only.",
        {"type": "object", "properties": {}, "required": []},
        _run,
    )


def _inspect_tool() -> Dict[str, Any]:
    def _run(payload: Dict[str, Any]) -> Any:
        km = _kernel_manager()
        if km is None:
            return _error_content("embedded IPython kernel is not available")
        from . import kernel
        return kernel.inspect_name(km.shell, str(payload["name"]))
    return _text_tool(
        "sciqlop_inspect",
        "Inspect a name in the SciQLop embedded kernel — type, value, and "
        "docstring. Read-only.",
        {"type": "object", "properties": {"name": {"type": "string"}},
         "required": ["name"]},
        _run,
    )


def _interrupt_kernel_tool() -> Dict[str, Any]:
    def _run(_payload: Dict[str, Any]) -> Any:
        km = _kernel_manager()
        if km is None:
            return _error_content("embedded IPython kernel is not available")
        km.interrupt()
        return "interrupt sent to the embedded kernel"
    return _text_tool(
        "sciqlop_interrupt_kernel",
        "Interrupt the currently running cell in the SciQLop embedded kernel "
        "(raises KeyboardInterrupt). Use to recover a long or stuck cell.",
        {"type": "object", "properties": {}, "required": []},
        _run,
        gated=True,
    )
```

Add the two read tools to the read list in `build_sciqlop_tools` (next to `_list_notebooks_tool()`/`_read_notebook_tool()`): append `_kernel_vars_tool(), _inspect_tool(),`. Add `_interrupt_kernel_tool()` to the `_write_tools` return list alongside `_run_notebook_cell_tool()`.

- [ ] **Step 4: Run it, confirm pass**

Run: `uv run pytest tests/test_kernel_tools_registered.py -q --no-xvfb`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/agents/tools/_builder.py tests/test_kernel_tools_registered.py
git commit -m "feat(agents): register interrupt / kernel_vars / inspect tools

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 10: Regression sweep

**Files:** none (verification only)

- [ ] **Step 1: Run the agent + kernel test subset**

Run: `uv run pytest tests/ -k "agent or kernel or notebook or outputs or sink or introspection" -q --no-xvfb`
Expected: all green.

- [ ] **Step 2: Broad regression (watch for segfaults — SciQLop must never segfault)**

Run: `uv run pytest tests/ -q --no-xvfb --ignore=tests/fuzzing -p no:cacheprovider`
Expected: green (the known pre-existing `test_vector_vp_component_labels_passed_through` full-run pollution flake is unrelated; any other failure is in scope).

- [ ] **Step 3: Commit (if any test files were adjusted during the sweep)**

```bash
git add -A && git commit -m "test(agents): notebook/kernel tools regression pass" || echo "nothing to commit"
```

---

## Self-review checklist (run before execution)

- **Spec §3 (jupyqt prerequisite):** Task 1 (interrupt + kernel_thread) + editable install — covered.
- **Spec §4 (#1 run cell):** Tasks 3 (capture), 4 (outputs), 5 (sink), 6 (orchestration + tool) — covered, incl. error→error-output and execution_count.
- **Spec §5 (#2 read outputs):** Task 7 — stream/result/error/image-marker + truncation — covered.
- **Spec §6 (#3 introspection):** Task 8 (vars/inspect) + Task 9 (tools) — filtering, summaries, caps, not-found — covered.
- **Spec §7 (#4 interrupt):** Task 2 (KernelManager.interrupt) + Task 9 (tool) — covered.
- **Spec §8 (error handling):** every tool returns `_error_content` on failure; `run_cell` records `error` outputs — covered.
- **Spec §9 (testing):** each task is test-first; Task 10 sweeps.
- **Type/name consistency:** `run_cell_capture`→dict keys (`stdout/stderr/result/displays/success/error/traceback/execution_count`) are produced in Task 3 and consumed identically in Tasks 4 & 6; `to_nbformat`, `NotebookSink.write_outputs`, `kernel_vars`, `inspect_name` names match across tasks.

**Integration points to verify against live code during execution** (flagged, not guessed): `_resolve_notebook`'s handling of absolute vs workspace-relative paths (Task 5/6 tests monkeypatch it); whether `_notebook_write_tools()` is the right registration site vs. `_write_tools` (Task 6); whether `build_sciqlop_tools` tolerates a stub main window (Task 9, fallback: real headless window from `tests/fixtures.py`).
