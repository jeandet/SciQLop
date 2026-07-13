# Gate profiling tools behind SCIQLOP_DEBUG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the watchdog, hang-dump signal handler, and sampler from starting unconditionally at every SciQLop launch, and stop the three debug-only `Tools > Profiling` menu actions from always appearing — gate all of it behind the existing `SCIQLOP_DEBUG` env var.

**Architecture:** Add one pure helper `is_debug_mode()` to the existing `sciqlop_logging` package (which already owns `SCIQLOP_DEBUG` semantics for log level). Wrap the profiling startup calls in `SciQLopApp.__init__` and the three debug-only menu actions in `ProfilingMenu.__init__` in `if is_debug_mode():`. No other files change.

**Tech Stack:** Python 3, pytest, PySide6/Qt.

## Global Constraints

- Reuse `SCIQLOP_DEBUG` (do not add a new env var) — spec decision, confirmed by user.
- The `Tools > Profiling` menu itself must always exist; only the three debug-only actions ("Show hot OS threads…", "Dump thread stacks now", "Flush sampling history") and their preceding separator are gated. Trace Start/Stop/Open/status actions stay unconditional.
- `SciQLop/user_api/diagnostics.py` and `ProfilingSettings` are out of scope — do not modify.
- Run with `uv run pytest` / `uv run python`, per project convention.
- TDD: write the failing test before the implementation for `is_debug_mode()`.

---

### Task 1: `is_debug_mode()` helper

**Files:**
- Modify: `SciQLop/components/sciqlop_logging/logger.py:1-11`
- Modify: `SciQLop/components/sciqlop_logging/__init__.py`
- Test: `tests/test_sciqlop_logging_debug_mode.py` (new)

**Interfaces:**
- Produces: `SciQLop.components.sciqlop_logging.is_debug_mode() -> bool`. Reads `os.environ` live on every call (not cached at import time), so tests can `monkeypatch.setenv`/`delenv` around it. Tasks 2 and 3 import and call this.

- [ ] **Step 1: Write the failing test**

Create `tests/test_sciqlop_logging_debug_mode.py`:

```python
from SciQLop.components.sciqlop_logging import is_debug_mode


def test_is_debug_mode_false_when_unset(monkeypatch):
    monkeypatch.delenv("SCIQLOP_DEBUG", raising=False)
    assert is_debug_mode() is False


def test_is_debug_mode_true_when_set(monkeypatch):
    monkeypatch.setenv("SCIQLOP_DEBUG", "1")
    assert is_debug_mode() is True


def test_is_debug_mode_true_when_set_empty(monkeypatch):
    # presence, not truthiness of the value, is what matters -- matches the
    # existing `'SCIQLOP_DEBUG' in os.environ` check in logger.py's module
    # level log-level setup.
    monkeypatch.setenv("SCIQLOP_DEBUG", "")
    assert is_debug_mode() is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sciqlop_logging_debug_mode.py -v`
Expected: FAIL with `ImportError: cannot import name 'is_debug_mode'`

- [ ] **Step 3: Implement `is_debug_mode()`**

In `SciQLop/components/sciqlop_logging/logger.py`, after the existing module-level `if 'SCIQLOP_DEBUG' in os.environ:` block (lines 7-11), add:

```python
def is_debug_mode() -> bool:
    return 'SCIQLOP_DEBUG' in os.environ
```

In `SciQLop/components/sciqlop_logging/__init__.py`, change the import line:

```python
from .logger import  SciQLopLogger, listen_sciqlop_logger, set_log_level, getLogger, is_debug_mode
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sciqlop_logging_debug_mode.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add SciQLop/components/sciqlop_logging/logger.py SciQLop/components/sciqlop_logging/__init__.py tests/test_sciqlop_logging_debug_mode.py
git commit -m "feat(logging): add is_debug_mode() helper for SCIQLOP_DEBUG gating"
```

---

### Task 2: Gate profiling startup wiring in `SciQLopApp.__init__`

**Files:**
- Modify: `SciQLop/core/sciqlop_application.py:38-59`

**Interfaces:**
- Consumes: `is_debug_mode()` from Task 1 (`SciQLop.components.sciqlop_logging`).

This task has no dedicated automated test — see the plan header and spec's Testing section for why (`qapp`/`main_window` fixtures in `tests/fixtures.py` are session-scoped, shared across the whole suite, so flipping `SCIQLOP_DEBUG` per-test to assert on `SciQLopApp` construction isn't practical). Verification is manual (Step 3 below) plus the full-suite run in Task 4.

- [ ] **Step 1: Read current code**

Current `SciQLop/core/sciqlop_application.py:38-50`:

```python
    def __init__(self, args):
        from SciQLop.components import sciqlop_logging
        super(SciQLopApp, self).__init__(args)
        self.setOrganizationName("LPP")
        self.setOrganizationDomain("lpp.fr")
        self.setApplicationName("SciQLop")
        sciqlop_logging.setup(capture_stdout=False)
        from SciQLop.components.profiling import hang_dump, sampler, watchdog
        hang_dump.install_signal_dump()
        sampler.maybe_start_from_settings()
        self._watchdog = watchdog.Watchdog()
        self._watchdog.start()
        self._watchdog_timer = watchdog.start_qt_heartbeat(self._watchdog)
```

- [ ] **Step 2: Gate the profiling block**

Replace lines 45-50 with:

```python
        from SciQLop.components.profiling import hang_dump, sampler, watchdog
        self._watchdog = None
        self._watchdog_timer = None
        if sciqlop_logging.is_debug_mode():
            hang_dump.install_signal_dump()
            sampler.maybe_start_from_settings()
            self._watchdog = watchdog.Watchdog()
            self._watchdog.start()
            self._watchdog_timer = watchdog.start_qt_heartbeat(self._watchdog)
```

The full method now reads:

```python
    def __init__(self, args):
        from SciQLop.components import sciqlop_logging
        super(SciQLopApp, self).__init__(args)
        self.setOrganizationName("LPP")
        self.setOrganizationDomain("lpp.fr")
        self.setApplicationName("SciQLop")
        sciqlop_logging.setup(capture_stdout=False)
        from SciQLop.components.profiling import hang_dump, sampler, watchdog
        self._watchdog = None
        self._watchdog_timer = None
        if sciqlop_logging.is_debug_mode():
            hang_dump.install_signal_dump()
            sampler.maybe_start_from_settings()
            self._watchdog = watchdog.Watchdog()
            self._watchdog.start()
            self._watchdog_timer = watchdog.start_qt_heartbeat(self._watchdog)
        # self.setAttribute(QtCore.Qt.AA_UseStyleSheetPropagationInWidgetStyles, True)
        self._current_palette_name = SciQLopStyle().color_palette
        self._current_palette = setup_palette(palette_name=self._current_palette_name)
        self.setPalette(self._current_palette)
        self.load_stylesheet()
        SciQLopStyle._notifier.changed.connect(self._on_style_changed)
        self._quickstart_shortcuts: Dict[str, Dict[str, Any]] = {}
        from SciQLop.components.command_palette.backend.registry import CommandRegistry
        self._command_registry = CommandRegistry()
```

- [ ] **Step 3: Manual verification**

Run: `SCIQLOP_DEBUG= uv run python -c "import os; os.environ.pop('SCIQLOP_DEBUG', None); from SciQLop.core.sciqlop_application import SciQLopApp; app = SciQLopApp([]); print('watchdog:', app._watchdog); print('timer:', app._watchdog_timer)"`
Expected output includes: `watchdog: None` and `timer: None`

Run: `SCIQLOP_DEBUG=1 uv run python -c "from SciQLop.core.sciqlop_application import SciQLopApp; app = SciQLopApp([]); print('watchdog:', app._watchdog); print('running:', app._watchdog.running)"`
Expected output includes: `running: True`

- [ ] **Step 4: Commit**

```bash
git add SciQLop/core/sciqlop_application.py
git commit -m "feat(profiling): gate watchdog/hang-dump/sampler startup behind SCIQLOP_DEBUG"
```

---

### Task 3: Gate the three debug-only `Profiling` menu actions

**Files:**
- Modify: `SciQLop/components/profiling/menu.py:36-97`

**Interfaces:**
- Consumes: `is_debug_mode()` from Task 1 (`SciQLop.components.sciqlop_logging`).

No dedicated automated test for the same reason as Task 2 (`main_window` fixture in `tests/fixtures.py` is session-scoped; `ProfilingMenu` is constructed once for the whole test session under whatever `SCIQLOP_DEBUG` value CI/local already has). Verified manually in Step 3, plus Task 4's full suite run (CI sets `SCIQLOP_DEBUG=1`, so the gated branch is exercised there).

- [ ] **Step 1: Read current code**

Current `SciQLop/components/profiling/menu.py:36-58` (imports at top of file, unchanged):

```python
class ProfilingMenu(QObject):
    def __init__(self, host: QWidget):
        super().__init__(host)
        self._host = host
        install_speasy_tracing()
        self.menu = QMenu("Profiling", host)
        self.menu.setToolTipsVisible(True)
        self._start = self.menu.addAction("Start trace…", self._on_start)
        self._stop = self.menu.addAction("Stop trace", self._on_stop)
        self._start.setToolTip(rich_tooltip(
            "Start trace",
            "Begin recording a Perfetto performance trace."))
        self._stop.setToolTip(rich_tooltip(
            "Stop trace",
            "Stop recording and save the current trace."))
        self.menu.addSeparator()
        self._hot_threads = self.menu.addAction(
            "Show hot OS threads…", self._on_show_hot_threads)
        self._hot_threads.setToolTip(rich_tooltip(
            "Show hot OS threads",
            "Ranks this process's OS threads by CPU time over a short"
            " window -- works without a trace running, and without"
            " py-spy/perf/root, by reading /proc directly."))
        self._hot_threads_dispatcher = _HotThreadsDispatcher(self)
        self._hot_threads_dispatcher.ready.connect(self._on_hot_threads_ready)
        self._dump_stacks = self.menu.addAction(
            "Dump thread stacks now", self._on_dump_stacks)
        self._dump_stacks.setToolTip(rich_tooltip(
            "Dump thread stacks now",
            "Writes an all-threads traceback dump to the diagnostics"
            " directory -- useful when SciQLop feels slow right now."
            " The same dump can be triggered from outside the app with"
            " kill -USR1 <pid>, no elevated privilege needed."))
        self._flush_samples = self.menu.addAction(
            "Flush sampling history", self._on_flush_samples)
        self._flush_samples.setToolTip(rich_tooltip(
            "Flush sampling history",
            "Writes the last minute or so of periodic all-threads stack"
            " samples to the diagnostics directory -- shows what was"
            " running even in code nobody hand-instrumented with a trace"
            " zone. The sampler itself is off by default; enable it in"
            " Settings > Profiling."))
        self.menu.addSeparator()
```

`self._hot_threads`, `self._hot_threads_dispatcher`, `self._dump_stacks`, `self._flush_samples` are only otherwise referenced inside their own `_on_*`/`_on_hot_threads_ready` handlers (confirmed by reading the rest of the file) — safe to make them conditionally `None`.

- [ ] **Step 2: Gate the three actions**

Add the import at the top of the file (alongside the existing `from SciQLop.components import sciqlop_logging` import already on line 18 — reuse it, no new import line needed since `sciqlop_logging` is already imported for `log = sciqlop_logging.getLogger(__name__)`).

Replace the block from `self.menu.addSeparator()` (first one, after `_stop.setToolTip`) through the second `self.menu.addSeparator()` with:

```python
        self.menu.addSeparator()
        self._hot_threads = None
        self._hot_threads_dispatcher = None
        self._dump_stacks = None
        self._flush_samples = None
        if sciqlop_logging.is_debug_mode():
            self._hot_threads = self.menu.addAction(
                "Show hot OS threads…", self._on_show_hot_threads)
            self._hot_threads.setToolTip(rich_tooltip(
                "Show hot OS threads",
                "Ranks this process's OS threads by CPU time over a short"
                " window -- works without a trace running, and without"
                " py-spy/perf/root, by reading /proc directly."))
            self._hot_threads_dispatcher = _HotThreadsDispatcher(self)
            self._hot_threads_dispatcher.ready.connect(self._on_hot_threads_ready)
            self._dump_stacks = self.menu.addAction(
                "Dump thread stacks now", self._on_dump_stacks)
            self._dump_stacks.setToolTip(rich_tooltip(
                "Dump thread stacks now",
                "Writes an all-threads traceback dump to the diagnostics"
                " directory -- useful when SciQLop feels slow right now."
                " The same dump can be triggered from outside the app with"
                " kill -USR1 <pid>, no elevated privilege needed."))
            self._flush_samples = self.menu.addAction(
                "Flush sampling history", self._on_flush_samples)
            self._flush_samples.setToolTip(rich_tooltip(
                "Flush sampling history",
                "Writes the last minute or so of periodic all-threads stack"
                " samples to the diagnostics directory -- shows what was"
                " running even in code nobody hand-instrumented with a trace"
                " zone. The sampler itself is off by default; enable it in"
                " Settings > Profiling."))
            self.menu.addSeparator()
```

Note the trailing `self.menu.addSeparator()` before `self._open_last = ...` is now only added in debug mode too — intentional, so there's no dangling double-separator when the three actions are hidden (the menu already has one separator right after Start/Stop trace).

- [ ] **Step 3: Manual verification**

Run: `SCIQLOP_DEBUG= uv run python -c "
import os; os.environ.pop('SCIQLOP_DEBUG', None)
from SciQLop.core.sciqlop_application import SciQLopApp
app = SciQLopApp([])
from SciQLop.components.profiling import ProfilingMenu
from PySide6.QtWidgets import QWidget
host = QWidget()
pm = ProfilingMenu(host)
actions = [a.text() for a in pm.menu.actions()]
print(actions)
assert 'Show hot OS threads…' not in actions
assert 'Dump thread stacks now' not in actions
assert 'Flush sampling history' not in actions
assert 'Start trace…' in actions
print('OK: debug-off menu correct')
"`
Expected: prints the action list (Start trace…, Stop trace, Open last trace in Perfetto, Open trace in Perfetto…, Status: idle — no hot-threads/dump/flush entries) then `OK: debug-off menu correct`.

Run the same with `SCIQLOP_DEBUG=1` and inverted asserts (`in actions` instead of `not in`) to confirm the debug-on case.

- [ ] **Step 4: Commit**

```bash
git add SciQLop/components/profiling/menu.py
git commit -m "feat(profiling): gate hot-threads/dump-stacks/flush-samples menu actions behind SCIQLOP_DEBUG"
```

---

### Task 4: Full suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest --no-xvfb`
Expected: all tests pass (same pass count as the pre-change baseline plus the 3 new tests from Task 1); read the actual printed pass/fail count and exit code, don't infer from a partial grep.

- [ ] **Step 2: If anything fails, diagnose before touching code**

Per project convention: never dismiss a new failure as unrelated without checking. If `test_watchdog.py` or `test_profiling_settings.py` fail, re-read Tasks 2/3 diffs — they should not affect either file (both exercise the `Watchdog`/`ProfilingSettings` classes directly, not through `SciQLopApp`/`ProfilingMenu`).

- [ ] **Step 3: Update project memory**

This is a small, self-contained change — no memory update needed beyond what's already captured in the committed spec/plan docs, per the "don't save what's derivable from git history" rule.
