# Workspace Package-Install API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give agents (and scripts) a clean, persistent way to install packages into a workspace — recorded in the manifest so they survive restarts and venv rebuilds — instead of transient raw `pip install`.

**Architecture:** One backend method, `Workspace.add_packages`, becomes the single source of truth for "install via uv + record in the manifest's `requires`". A public `user_api.install_packages` function, a new gated `sciqlop_install_package` agent tool, and the `%install` / `%workspace install` magics all delegate to it.

**Tech Stack:** Python 3.x, `uv` (via `uv_command`), IPython magics, PySide6 (Workspace is a QObject), pytest (`pytest-qt`/`pytest-xvfb`).

## Global Constraints

- Persistence is via the manifest's `requires`; `prepare_workspace` already turns that into the generated `pyproject.toml` + `uv sync` at launch. `add_packages` only needs to install now + append to `requires` + save.
- A **failed** uv install must leave the manifest untouched (no phantom entry).
- `add_packages` is synchronous/blocking with no Qt signal emission; callers keep it off the GUI thread (the agent tool uses the IO pool; magics run on the kernel thread).
- Structured result shape, used verbatim everywhere: `{"ok": bool, "installed": list[str], "already_present": list[str], "error": str}`.
- Names verbatim: `Workspace.add_packages`, `SciQLop.user_api.packages.install_packages`, tool name `sciqlop_install_package`.
- SciQLop test command (run from the SciQLop repo root): `uv run pytest --no-xvfb <path> -v`.
- Tasks 1–4 are in the SciQLop repo (branch `feat/workspace-package-install`). Task 5 is in the `plugins_sciqlop` repo. Stage only the files each task lists — never `git add -A` (untracked build dirs exist).

---

## File Structure

- `SciQLop/components/workspaces/backend/workspace.py` — add `add_packages`; remove dead `install_dependency`/`install_dependencies` (Task 1); remove `record_dependencies` once unused (Task 3).
- `SciQLop/user_api/packages.py` — new; `install_packages` (Task 2).
- `SciQLop/components/agents/tools/_builder.py` — new `sciqlop_install_package` tool + `_format_install_result` (Task 3... no: Task 4).
- `SciQLop/user_api/magics/install_magic.py` + `workspace_magic.py` — refactor onto the API (Task 3).
- `SciQLop/examples/tutorials/SciQLop/11-SciQLopWorkspace.ipynb` — §3 update (Task 4... renumbered below).
- `tests/test_workspace_add_packages.py`, `tests/test_install_packages_api.py`, `tests/test_install_package_tool.py`, `tests/test_magics/test_install_magic.py` (update).
- `plugins_sciqlop/sciqlop_{claude,opencode,copilot}/.../backend.py` — `SYSTEM_PROMPT` bullet (Task 5).

---

### Task 1: `Workspace.add_packages` backend method

**Files:**
- Modify: `SciQLop/components/workspaces/backend/workspace.py`
- Test: `tests/test_workspace_add_packages.py` (create)

**Interfaces:**
- Produces: `Workspace.add_packages(self, specs: list[str]) -> dict` returning
  `{"ok": bool, "installed": list[str], "already_present": list[str], "error": str}`.
  Uses the existing `self._uv_install(packages) -> subprocess.CompletedProcess`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_workspace_add_packages.py`:

```python
"""Workspace.add_packages: install via uv + record in manifest, structured result."""
from types import SimpleNamespace

from SciQLop.components.workspaces.backend.workspace import Workspace
from SciQLop.components.workspaces.backend.workspace_manifest import WorkspaceManifest


def _make_ws(tmp_path, requires=None):
    # Bypass the QObject __init__ so the test needs no QApplication.
    m = WorkspaceManifest(name="T", requires=list(requires or []))
    m.save(tmp_path / "workspace.sciqlop")          # sets m.directory = tmp_path
    ws = Workspace.__new__(Workspace)
    ws._manifest = m
    ws._manifest_path = tmp_path / "workspace.sciqlop"
    return ws


def test_installs_new_package_and_records(tmp_path):
    ws = _make_ws(tmp_path)
    calls = []
    ws._uv_install = lambda pkgs: calls.append(pkgs) or SimpleNamespace(
        returncode=0, stdout="ok", stderr="")
    result = ws.add_packages(["astropy"])
    assert result == {"ok": True, "installed": ["astropy"],
                      "already_present": [], "error": ""}
    assert calls == [["astropy"]]
    assert "astropy" in ws._manifest.requires
    # persisted
    assert "astropy" in WorkspaceManifest.load(tmp_path / "workspace.sciqlop").requires


def test_already_present_skips_uv(tmp_path):
    ws = _make_ws(tmp_path, requires=["astropy"])
    ws._uv_install = lambda pkgs: (_ for _ in ()).throw(AssertionError("uv called"))
    result = ws.add_packages(["astropy"])
    assert result == {"ok": True, "installed": [],
                      "already_present": ["astropy"], "error": ""}


def test_mix_installs_only_new(tmp_path):
    ws = _make_ws(tmp_path, requires=["astropy"])
    ws._uv_install = lambda pkgs: SimpleNamespace(returncode=0, stdout="", stderr="")
    result = ws.add_packages(["astropy", "scipy"])
    assert result["installed"] == ["scipy"]
    assert result["already_present"] == ["astropy"]
    assert "scipy" in ws._manifest.requires


def test_failed_install_leaves_manifest_untouched(tmp_path):
    ws = _make_ws(tmp_path)
    ws._uv_install = lambda pkgs: SimpleNamespace(
        returncode=1, stdout="", stderr="No match for nonexistent-xyz")
    result = ws.add_packages(["nonexistent-xyz"])
    assert result["ok"] is False
    assert result["installed"] == []
    assert "No match" in result["error"]
    assert ws._manifest.requires == []
    assert WorkspaceManifest.load(tmp_path / "workspace.sciqlop").requires == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_workspace_add_packages.py -v`
Expected: FAIL — `AttributeError: 'Workspace' object has no attribute 'add_packages'`.

- [ ] **Step 3: Implement `add_packages` and remove the dead methods**

In `SciQLop/components/workspaces/backend/workspace.py`, **replace** the two methods `install_dependency` and `install_dependencies` (they have no callers) with `add_packages`. Keep `_uv_install` and `record_dependencies` (still used by the magic until Task 3). Result:

```python
    def add_packages(self, specs: list[str]) -> dict:
        """Install packages into the workspace venv (uv) and record the newly
        added ones in the manifest so they persist across restarts and venv
        rebuilds. Synchronous/blocking — call off the GUI thread.

        Returns {"ok", "installed", "already_present", "error"}."""
        already_present = [s for s in specs if s in self._manifest.requires]
        to_install = [s for s in specs if s not in self._manifest.requires]
        if not to_install:
            return {"ok": True, "installed": [],
                    "already_present": already_present, "error": ""}
        result = self._uv_install(to_install)
        if result.returncode != 0:
            log.error("Failed to install %s: %s", to_install, result.stderr)
            return {"ok": False, "installed": [],
                    "already_present": already_present, "error": result.stderr}
        self._manifest.requires.extend(to_install)
        self._manifest.save(self._manifest_path)
        return {"ok": True, "installed": to_install,
                "already_present": already_present, "error": ""}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_workspace_add_packages.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/workspaces/backend/workspace.py tests/test_workspace_add_packages.py
git commit -m "feat(workspaces): Workspace.add_packages — install + persist in manifest

Single source of truth for installing a package into the workspace venv and
recording it in the manifest requires. Replaces the unused install_dependency/
install_dependencies. Failed installs leave the manifest untouched.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `user_api.install_packages`

**Files:**
- Create: `SciQLop/user_api/packages.py`
- Test: `tests/test_install_packages_api.py` (create)

**Interfaces:**
- Consumes: `Workspace.add_packages` (Task 1); `workspaces_manager_instance()` (has `.has_workspace` and `.workspace`).
- Produces: `SciQLop.user_api.packages.install_packages(*specs: str) -> dict` (same result shape).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_install_packages_api.py`:

```python
"""user_api.install_packages: resolve active workspace and delegate to add_packages."""
from unittest.mock import MagicMock

import SciQLop.user_api.packages as pkgs


def test_no_active_workspace(monkeypatch):
    monkeypatch.setattr(pkgs, "workspaces_manager_instance", lambda: None)
    result = pkgs.install_packages("astropy")
    assert result == {"ok": False, "installed": [],
                      "already_present": [], "error": "no active workspace"}


def test_delegates_to_add_packages(monkeypatch):
    ws = MagicMock()
    ws.add_packages.return_value = {"ok": True, "installed": ["scipy"],
                                    "already_present": [], "error": ""}
    wm = MagicMock(has_workspace=True, workspace=ws)
    monkeypatch.setattr(pkgs, "workspaces_manager_instance", lambda: wm)
    result = pkgs.install_packages("scipy", "astropy>=5")
    ws.add_packages.assert_called_once_with(["scipy", "astropy>=5"])
    assert result["installed"] == ["scipy"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_install_packages_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'SciQLop.user_api.packages'`.

- [ ] **Step 3: Implement the module**

Create `SciQLop/user_api/packages.py`:

```python
"""Install Python packages into the active workspace and persist them.

Unlike a raw ``pip install``, ``install_packages`` records the packages in the
workspace manifest (``workspace.sciqlop``), so they are reinstalled on the next
launch and survive venv recreation.
"""
from __future__ import annotations

from SciQLop.components.workspaces import workspaces_manager_instance


def install_packages(*specs: str) -> dict:
    """Install one or more packages into the active workspace and record them.

    Accepts PEP 508 specifiers (e.g. ``"astropy"``, ``"scipy>=1.11"``). Returns
    ``{"ok": bool, "installed": list, "already_present": list, "error": str}``.
    """
    wm = workspaces_manager_instance()
    if wm is None or not getattr(wm, "has_workspace", False):
        return {"ok": False, "installed": [],
                "already_present": [], "error": "no active workspace"}
    return wm.workspace.add_packages(list(specs))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest --no-xvfb tests/test_install_packages_api.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/user_api/packages.py tests/test_install_packages_api.py
git commit -m "feat(user_api): install_packages — public workspace package install

Resolves the active workspace and delegates to Workspace.add_packages.
Discoverable by the agent via sciqlop_api_reference.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Refactor the install magics onto the API

**Files:**
- Modify: `SciQLop/user_api/magics/install_magic.py`
- Modify: `SciQLop/user_api/magics/workspace_magic.py` (help text only)
- Modify: `SciQLop/components/workspaces/backend/workspace.py` (remove `record_dependencies` if now unused)
- Test: `tests/test_magics/test_install_magic.py` (rewrite)

**Interfaces:**
- Consumes: `user_api.install_packages` (Task 2).

- [ ] **Step 1: Rewrite the magic tests (failing)**

Replace the contents of `tests/test_magics/test_install_magic.py`:

```python
"""%install delegates to user_api.install_packages and reports the result."""
from unittest.mock import patch

import pytest

from SciQLop.user_api.magics.install_magic import install_magic


def test_install_delegates_and_reports(capsys):
    with patch("SciQLop.user_api.magics.install_magic.install_packages") as m:
        m.return_value = {"ok": True, "installed": ["astropy", "spacepy"],
                          "already_present": [], "error": ""}
        install_magic("astropy spacepy")
    m.assert_called_once_with("astropy", "spacepy")
    assert "astropy" in capsys.readouterr().out


def test_install_no_args_raises():
    with pytest.raises(Exception, match="Usage"):
        install_magic("")


def test_install_failure_raises(capsys):
    with patch("SciQLop.user_api.magics.install_magic.install_packages") as m:
        m.return_value = {"ok": False, "installed": [],
                          "already_present": [], "error": "boom"}
        with pytest.raises(Exception, match="failed"):
            install_magic("nonexistent-pkg-xyz")
    assert "boom" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest --no-xvfb tests/test_magics/test_install_magic.py -v`
Expected: FAIL — `install_magic` has no `install_packages` symbol to patch (AttributeError) / old behaviour.

- [ ] **Step 3: Rewrite `install_magic.py`**

Replace the contents of `SciQLop/user_api/magics/install_magic.py`:

```python
"""Implementation of %install line magic — install packages and record them."""
import shlex

from IPython.core.error import UsageError

from SciQLop.user_api.packages import install_packages


def install_magic(line: str):
    """%install <package> [package2 ...]

    Install Python packages into the current workspace using uv and record them
    in the .sciqlop manifest so they persist across restarts and venv rebuilds.
    """
    packages = shlex.split(line)
    if not packages:
        raise UsageError("Usage: %install <package> [package2 ...]")

    print(f"Installing: {' '.join(packages)}")
    result = install_packages(*packages)
    if not result["ok"]:
        print(result["error"])
        raise UsageError("Installation failed")
    if result["installed"]:
        print(f"Installed and recorded: {', '.join(result['installed'])}")
    if result["already_present"]:
        print(f"Already present: {', '.join(result['already_present'])}")
```

- [ ] **Step 4: Refresh `%workspace install` help text**

In `SciQLop/components/workspaces/backend/workspace_magic.py`, update the `SUBCOMMANDS` entry so it reads:

```python
    "install": "Install packages and record in the manifest (persists across restarts)",
```

(`_cmd_install` already delegates to `install_magic` — leave it.)

- [ ] **Step 5: Remove `record_dependencies` if now unused**

Run: `git grep -n "record_dependencies" -- '*.py'`
If the only hit is its definition in `workspace.py`, delete the `record_dependencies` method. If anything else references it, leave it.

- [ ] **Step 6: Run the magic + backend tests**

Run: `uv run pytest --no-xvfb tests/test_magics/test_install_magic.py tests/test_magics/test_workspace_magic.py tests/test_workspace_add_packages.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/user_api/magics/install_magic.py SciQLop/components/workspaces/backend/workspace_magic.py SciQLop/components/workspaces/backend/workspace.py tests/test_magics/test_install_magic.py
git commit -m "refactor(magics): route %install / %workspace install through install_packages

Consolidates onto Workspace.add_packages (removes the magic's duplicate uv
call and the now-unused record_dependencies).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `sciqlop_install_package` agent tool + tutorial notebook

**Files:**
- Modify: `SciQLop/components/agents/tools/_builder.py`
- Modify: `SciQLop/examples/tutorials/SciQLop/11-SciQLopWorkspace.ipynb`
- Test: `tests/test_install_package_tool.py` (create)

**Interfaces:**
- Consumes: `user_api.packages.install_packages` (Task 2); `_text_tool`, `_write_tools` (existing in `_builder.py`).

- [ ] **Step 1: Write the failing tool test**

Create `tests/test_install_package_tool.py`:

```python
"""sciqlop_install_package: gated tool that delegates to install_packages."""
import asyncio
from unittest.mock import MagicMock

import SciQLop.components.agents.tools._builder as builder


def _get_tool():
    tools = builder.build_sciqlop_tools(MagicMock())
    return next(t for t in tools if t["name"] == "sciqlop_install_package")


def test_tool_is_registered_and_gated():
    tool = _get_tool()
    assert tool["gated"] is True
    assert tool["input_schema"]["properties"]["packages"]["type"] == "array"
    assert tool["input_schema"]["required"] == ["packages"]


def test_tool_handler_delegates(monkeypatch):
    import SciQLop.user_api.packages as pkgs
    monkeypatch.setattr(pkgs, "install_packages",
                        lambda *s: {"ok": True, "installed": list(s),
                                    "already_present": [], "error": ""})
    tool = _get_tool()
    out = asyncio.run(tool["handler"]({"packages": ["astropy"]}))
    text = out["content"][0]["text"]
    assert "astropy" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest --no-xvfb tests/test_install_package_tool.py -v`
Expected: FAIL — `StopIteration` (no `sciqlop_install_package` tool).

- [ ] **Step 3: Add the tool to `_builder.py`**

Add this helper near `_error_content` in `SciQLop/components/agents/tools/_builder.py`:

```python
def _format_install_result(result: Dict[str, Any]) -> str:
    parts: List[str] = []
    if result.get("installed"):
        parts.append(f"installed and recorded: {', '.join(result['installed'])}")
    if result.get("already_present"):
        parts.append(f"already present: {', '.join(result['already_present'])}")
    if not result.get("ok"):
        parts.append(f"error: {result.get('error', '')}")
    return "\n".join(parts) if parts else "ok (nothing to do)"
```

Add this tool builder (e.g. just above `_write_tools`):

```python
def _install_package_tool() -> Dict[str, Any]:
    def _run(payload: Dict[str, Any]) -> Any:
        from SciQLop.user_api.packages import install_packages
        packages = [str(p) for p in (payload.get("packages") or [])]
        if not packages:
            return _error_content("no packages given")
        return _format_install_result(install_packages(*packages))

    return _text_tool(
        "sciqlop_install_package",
        (
            "Install one or more Python packages into the active workspace's venv "
            "(via uv) AND record them in the workspace manifest, so they persist "
            "across restarts and survive venv rebuilds. Use this instead of running "
            "`pip install` in sciqlop_exec_python — raw pip installs are NOT recorded "
            "and are wiped when the venv is recreated. Pass PEP 508 specifiers, e.g. "
            "['astropy', 'scipy>=1.11']."
        ),
        {
            "type": "object",
            "properties": {
                "packages": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["packages"],
        },
        _run,
        gated=True,
        thread=True,  # uv install blocks; keep it off the GUI event loop
    )
```

In `_write_tools`, add `_install_package_tool()` to the returned list, e.g. change the final return to include it:

```python
    return [set_time_range, _create_panel_tool(main_window), _exec_python_tool(),
            _install_package_tool()] + _notebook_write_tools() + [_run_notebook_cell_tool(), _interrupt_kernel_tool()]
```

- [ ] **Step 4: Run the tool test**

Run: `uv run pytest --no-xvfb tests/test_install_package_tool.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Update the tutorial notebook §3**

In `SciQLop/examples/tutorials/SciQLop/11-SciQLopWorkspace.ipynb`, after the existing code cell `%install astropy` (the one that installs astropy), insert two new cells (use the NotebookEdit tool, `edit_mode=insert`):

A markdown cell:
```markdown
You can do the same from Python with the public API — this is what scripts and
the embedded AI agent use:

```python
from SciQLop.user_api.packages import install_packages
install_packages("astropy")
# -> {"ok": True, "installed": [...], "already_present": [...], "error": ""}
```

AI agents add dependencies through the gated `sciqlop_install_package` tool,
which routes through this same path — so anything they install is recorded in
`workspace.sciqlop` and persists. Never rely on a bare `pip install`: it is not
recorded and is wiped when the venv is rebuilt.
```

A code cell:
```python
from SciQLop.user_api.packages import install_packages
install_packages("astropy")
```

- [ ] **Step 6: Verify the notebook is still valid JSON**

Run: `uv run python -c "import json,nbformat; nbformat.read('SciQLop/examples/tutorials/SciQLop/11-SciQLopWorkspace.ipynb', as_version=4); print('ok')"`
Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
cd /var/home/jeandet/Documents/prog/SciQLop
git add SciQLop/components/agents/tools/_builder.py tests/test_install_package_tool.py SciQLop/examples/tutorials/SciQLop/11-SciQLopWorkspace.ipynb
git commit -m "feat(agents): sciqlop_install_package tool + tutorial update

Gated tool that installs+persists workspace packages via install_packages, so
agents stop using raw pip. Tutorial §3 now shows the programmatic API.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Agent system-prompt nudge (plugins_sciqlop repo)

**Files:**
- Modify: `sciqlop_claude/sciqlop_claude/backend.py`
- Modify: `sciqlop_opencode/sciqlop_opencode/backend.py`
- Modify: `sciqlop_copilot/sciqlop_copilot/backend.py`

Work from: `/var/home/jeandet/Documents/prog/plugins_sciqlop`

- [ ] **Step 1: Locate the write-tools bullet list in each SYSTEM_PROMPT**

Run: `git grep -n "sciqlop_exec_python" -- '*/backend.py'`
Each backend's `SYSTEM_PROMPT` has a "Write tools" section listing `sciqlop_exec_python` etc.

- [ ] **Step 2: Add one bullet after the `sciqlop_exec_python` description in each of the three SYSTEM_PROMPTs**

Insert this line (matching each file's existing string-concatenation style and indentation) right after the `sciqlop_exec_python` bullet:

```
    "  • sciqlop_install_package(packages) — install Python dependencies into "
    "    the workspace venv and record them in the manifest so they persist. "
    "    Use this to add libraries; never run `pip install` directly (it is not "
    "    recorded and is wiped when the venv is rebuilt).\n"
```

Apply the same insertion in all three files: `sciqlop_claude/sciqlop_claude/backend.py`, `sciqlop_opencode/sciqlop_opencode/backend.py`, `sciqlop_copilot/sciqlop_copilot/backend.py`.

- [ ] **Step 3: Verify each module still imports (prompt string is well-formed)**

Run (from the plugins repo root):
```
uv run --isolated --no-project --with pytest python -c "import ast; [ast.parse(open(p).read()) for p in ['sciqlop_claude/sciqlop_claude/backend.py','sciqlop_opencode/sciqlop_opencode/backend.py','sciqlop_copilot/sciqlop_copilot/backend.py']]; print('ok')"
```
Expected: `ok` (syntax valid; the inserted string concatenation is well-formed).

- [ ] **Step 4: Commit**

```bash
cd /var/home/jeandet/Documents/prog/plugins_sciqlop
git add sciqlop_claude/sciqlop_claude/backend.py sciqlop_opencode/sciqlop_opencode/backend.py sciqlop_copilot/sciqlop_copilot/backend.py
git commit -m "feat(agents): tell agents to use sciqlop_install_package, not pip

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- `Workspace.add_packages` (consolidation, dead-method removal, failed-install safety) → Task 1.
- `user_api.install_packages` (+ no-active-workspace path) → Task 2.
- Magic refactor (`%install`, `%workspace install` help, remove `record_dependencies`) → Task 3.
- `sciqlop_install_package` gated tool → Task 4. Tutorial §3 → Task 4.
- System prompts (claude/opencode/copilot) → Task 5.
- Structured result shape used verbatim in Tasks 1, 2, 4. ✓

**Placeholder scan:** none — every step has full code/commands.

**Type consistency:** the result dict keys (`ok`/`installed`/`already_present`/`error`), `add_packages(specs: list[str])`, `install_packages(*specs)`, and tool name `sciqlop_install_package` are identical across all tasks and tests.
