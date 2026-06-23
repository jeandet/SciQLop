# Agent Notebook & Kernel Tools — Design

**Date:** 2026-06-23
**Status:** Approved design, pending implementation plan
**Component:** `SciQLop/components/agents/` (public out-of-tree agent API — extend, don't refactor)

## 1. Problem

The in-app Claude agent can *author* notebooks (file-level cell CRUD) and run
ephemeral code (`exec_python`), but it cannot **run a notebook cell and see its
result**, **read a cell's existing outputs**, **introspect the live kernel**, or
**recover a long/hung cell**. The author→execute→observe loop is broken: the user
must manually run everything the agent writes.

This design adds four capabilities to close that loop, all on the existing
in-process embedded kernel.

## 2. Ecosystem context & scope decision

Jupyter AI 3.0 (`jupyterlab/jupyter-ai`) and `datalayer/jupyter-ai-agents` solve
live notebook editing with **RTC / shared models** (Yjs / `pycrdt`) plus a kernel
client and an MCP server — explicitly avoiding disk-level edits because those
"don't reflect synchronously on the notebook UI."

Our embedded jupyverse does **not** have RTC enabled (`jupyter_ydoc`, `fps_yjs`,
`jupyter_server_ydoc`, collaboration modules are all absent; JupyterLab runs
non-collaborative). The only mechanism to reflect an agent edit in the live UI is
the **file-watcher reload** (`fps_file_watcher`).

**Decisions:**
- **RTC is its own future epic** (it would also underpin live JupyterLab presence,
  i.e. deferred feature #5). Not in this spec.
- This spec ships **#1 run-cell on the disk path, behind an RTC-ready
  `NotebookSink` seam**, plus **#2 read-outputs, #3 kernel introspection, #4
  interrupt** — all infra-free on the in-process shell.
- **#5 (live focused-notebook/cell awareness)** is a separate design pass.

The RTC question only affects #1's write-back quality; #2/#3/#4 are independent of
it.

## 3. Architecture & file layout

Small, focused units. SciQLop-side only.

**jupyqt prerequisite (clean interface, separate PR):** add two public members to
`EmbeddedJupyter` so SciQLop stops reaching private attributes —
`interrupt()` (wraps the kernel thread's `interrupt()`) and a read-only
`kernel_thread` property (legitimizes what `submit_cell` already does via
`self._jupyter._kernel_thread.loop`). Done test-first in the jupyqt repo,
PR'd, and installed into SciQLop's venv before the SciQLop work consumes it.

| File | Responsibility |
|---|---|
| `components/jupyter/kernel/manager.py` (modify) | use the public `self._jupyter.kernel_thread` / `self._jupyter.interrupt()`; add `run_cell_capture(code)` (rich capture: stdout/stderr/result/display outputs/error) and `interrupt()` |
| `components/agents/tools/_outputs.py` (new) | pure: captured run → list of **nbformat output dicts** |
| `components/agents/tools/_notebook_sink.py` (new) | `NotebookSink` Protocol + `DiskNotebookSink` (nbformat write-back). **The RTC seam.** |
| `components/agents/tools/notebooks.py` (modify) | add `run_cell(...)`; extend `read_notebook` to render outputs |
| `components/agents/tools/kernel.py` (new) | `kernel_vars()`, `inspect(name)` |
| `components/agents/tools/_builder.py` (modify) | register the 4 tools |

`run_cell_capture` extends today's `_run_and_capture` (which already uses
`IPython.utils.capture.capture_output`) to also surface `cap.outputs` (rich
display data) rather than only `stdout`/`stderr`/`result` repr.

## 4. #1 — `sciqlop_run_notebook_cell(path, index)` (gated: write)

Flow (orchestrated in `notebooks.run_cell`):
1. Resolve `.ipynb` (existing `_resolve_notebook`), read the cell's source. Reject
   non-code cells with an error content.
2. Execute the source on the **shared embedded kernel** via
   `KernelManager.run_cell_capture` (same shell the user's JupyterLab is bound to,
   so variables persist; runs on the kernel thread, off the GUI loop).
3. Build nbformat outputs via `_outputs.to_nbformat(captured)`:
   - `stdout`/`stderr` → `{"output_type":"stream","name":...,"text":...}`
   - cell result (displayhook value) → `{"output_type":"execute_result",
     "execution_count":N,"data":{"text/plain":repr},"metadata":{}}`
   - each captured rich display (incl. figures) → `{"output_type":"display_data",
     "data":obj.data,"metadata":obj.metadata}`
   - failure → `{"output_type":"error","ename","evalue","traceback":[...]}`
4. Assign an advancing `execution_count` (monotonic per `KernelManager`).
5. Persist via `sink.write_outputs(rel_path, index, outputs, execution_count)` —
   `DiskNotebookSink` writes the cell's `outputs` and `execution_count` into the
   `.ipynb` with `nbformat`; JupyterLab's file-watcher reloads it.
6. Return a compact text summary to the agent: `[N]`, ok/error, and truncated
   stdout/result or the error `ename: evalue`.

Errors during execution are captured into an `error` output and reported in the
summary — never raised into the agent loop.

## 5. #2 — `read_notebook` includes outputs (read)

`_render_cell` additionally emits each code cell's existing outputs:
- `execute_result` / `stream` → truncated text
- `error` → `ename: evalue` + truncated traceback
- `display_data` / `execute_result` image MIME types → a `[image: <mime>]` text
  marker (read_notebook stays a text tool; the `sciqlop_screenshot_*` tools cover
  rendering)

Output text is truncated to a per-cell cap to bound payload size.

## 6. #3 — `sciqlop_kernel_vars()` / `sciqlop_inspect(name)` (read)

`kernel_vars`: snapshot `shell.user_ns`; filter out modules, dunders, and IPython
internals (`In`, `Out`, `get_ipython`, `exit`, `quit`, `_`, `__`, `___`, `_i*`,
`_oh`, `_dh`, …). For each remaining binding return `name`, `type` name, and a
short summary: shape+dtype for ndarray/DataFrame, `len(...)` for sized containers,
otherwise a length-capped `repr`. Cap the number of entries and each summary's
length.

`inspect(name)`: `shell.object_inspect(name, detail_level=...)` → type, signature,
and docstring (the control path hardened by the jupyqt busy-kernel fix). Not found
→ a clear "not defined" message.

## 7. #4 — `sciqlop_interrupt_kernel()` (gated: write)

`KernelManager.interrupt()` delegates to the new public `EmbeddedJupyter.interrupt()`
(raises `KeyboardInterrupt` in the running cell via the kernel thread). Returns a
short confirmation. Lets the agent recover a long/hung cell it started — the
failure mode behind the recently fixed busy-kernel crash.

## 8. Error handling

Every tool follows the existing agent-tool contract: catch internal failures and
return error *content* (`_error_content`), never propagate into the session loop.
`run_cell` additionally records execution failures as an `error` output in the
notebook so the user sees them in JupyterLab.

## 9. Testing (test-first)

- `_outputs.to_nbformat` — pure unit tests per output type (stream, execute_result,
  display_data incl. an image MIME, error), dtype/shape rendering, truncation.
- `run_cell` — end-to-end with a real kernel (pytest-qt): run a cell that prints +
  returns a value → assert nbformat outputs land in the `.ipynb` and the summary
  reflects them; a raising cell → `error` output + error summary. `NotebookSink`
  faked in the orchestration unit test to assert the seam is used.
- `read_notebook` — a fixture `.ipynb` with mixed outputs → assert rendered text,
  truncation, and image marker.
- `kernel_vars` / `inspect` — seed `shell.user_ns` → assert filtering, summaries,
  caps; `inspect` of a known and an unknown name.
- `interrupt` — start a long cell on the kernel, interrupt, assert it stops.

## 10. Out of scope (explicit)

- **RTC / live shared-model sync** — separate future epic; `NotebookSink` is the
  seam that lets an `RTCNotebookSink` replace `DiskNotebookSink` later.
- **#5 live focused-notebook/cell awareness** — separate design pass (depends on
  the RTC/front-end bridge work).
- **Exposing our own MCP server** the way Jupyter AI does — not needed; tools are
  registered through the existing agent tool surface.
