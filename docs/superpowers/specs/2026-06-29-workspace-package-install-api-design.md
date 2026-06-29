# Workspace package-install API for agents

**Date:** 2026-06-29
**Status:** Approved (design)
**Repos:** SciQLop (bulk) + plugins_sciqlop (system-prompt nudge only).

## Problem

AI agents embedded in SciQLop add Python libraries by running raw `pip install`
through `sciqlop_exec_python`. That lands the package in the workspace venv
**transiently**: it is not recorded in the `workspace.sciqlop` manifest, so it is
not reinstalled on the next launch and is wiped whenever the venv is recreated
(SciQLop upgrade / system-fingerprint change — see `workspace_venv._needs_recreate`).

A clean, persistent install path already exists for humans (`%install`,
`%workspace install`) but there is **no public `user_api` function** an agent can
call, and no agent tool — so agents fall back to raw pip.

## Existing state (verified)

- **Persistence model:** the manifest's `[dependencies] requires` is the source of
  truth. `prepare_workspace` regenerates `pyproject.toml` from it on every launch
  (`generate_pyproject_toml`), invalidates a stale `uv.lock`, and `uv sync`s the
  venv. So a package is persistent **iff** it is in `manifest.requires`.
- **Backend:** `Workspace` (`components/workspaces/backend/workspace.py`) has
  `_uv_install`, `record_dependencies` (used by the `%install` magic), and two
  **unused** methods `install_dependency` / `install_dependencies` (no callers in
  either repo — confirmed by grep).
- **Magics:** `%install <pkgs>` (`install_magic.py`) installs + records;
  `%workspace install <pkgs>` (`workspace_magic.py::_cmd_install`) delegates to
  `install_magic`. Both duplicate the `uv pip install` call.
- **Agent tools:** built in `components/agents/tools/_builder.py` as dicts
  `{name, description, input_schema, handler, gated}`. `_text_tool(..., gated=True,
  thread=True)` is the canonical write-tool helper; `gated` tools are denied when
  writes are off and otherwise prompt per call. `sciqlop_exec_python` is the gated
  analog. The agent discovers `user_api` via the `sciqlop_api_reference` tool.
- **Tutorial:** `examples/tutorials/SciQLop/11-SciQLopWorkspace.ipynb` §3
  ("Installing packages") documents `%install` / `%workspace install`.

## Design

One backend method becomes the single source of truth for "install + persist";
the magics, a new `user_api` function, and a new gated agent tool all delegate to
it.

### 1. Backend — `Workspace.add_packages` (consolidation)

```python
def add_packages(self, specs: list[str]) -> dict:
    """Install packages into the workspace venv (uv) and record the newly
    added ones in the manifest so they persist. Returns
    {"ok": bool, "installed": [...], "already_present": [...], "error": str}.
    Synchronous and blocking — callers must keep it off the GUI thread."""
```

Behaviour:
- `already_present = [s for s in specs if s in self._manifest.requires]`;
  `to_install = [s for s in specs if s not in self._manifest.requires]`
  (order preserved).
- If `to_install` is empty: return `ok=True, installed=[], already_present=...`
  (no uv call).
- Run `self._uv_install(to_install)` (`uv pip install`, captured output). On
  `returncode != 0`: return `ok=False, installed=[], already_present=...,
  error=stderr` — **manifest untouched**.
- On success: `self._manifest.requires.extend(to_install)`;
  `self._manifest.save(self._manifest_path)`; return
  `ok=True, installed=to_install, already_present=..., error=""`.

Remove the unused `install_dependency` / `install_dependencies`. After the magic
refactor (below) `record_dependencies` has no remaining callers — remove it too
if grep confirms none; otherwise leave it.

The manifest mutation is a list append + TOML file write with **no Qt signal
emission**, so it is safe off the GUI thread (matching today's `%install`).

### 2. `user_api` — `install_packages`

New module `user_api/packages.py`:

```python
def install_packages(*specs: str) -> dict:
    """Install Python package(s) into the active workspace and record them in the
    workspace manifest so they persist across restarts and venv rebuilds.
    Returns {"ok", "installed", "already_present", "error"}."""
```

Resolves the active workspace via `workspaces_manager_instance()` (returns the
no-active-workspace error dict `{"ok": False, "installed": [], "already_present":
[], "error": "no active workspace"}` if absent), else returns
`ws.add_packages(list(specs))`. Auto-discovered by `sciqlop_api_reference`.

### 3. Agent tool — `sciqlop_install_package` (gated)

Add to `_write_tools` in `_builder.py` via `_text_tool(..., gated=True,
thread=True)` (blocking uv runs in the IO pool, off the GUI thread):

- name: `sciqlop_install_package`
- schema: `{"packages": {"type": "array", "items": {"type": "string"}}}`,
  required `["packages"]`
- handler: calls `user_api.packages.install_packages(*packages)` and renders the
  structured result to a short text summary (a `_format_install_result` helper in
  `_builder.py`: e.g. `installed: astropy` / `already present: …` /
  `error: <stderr>`).
- description: install + persist into the workspace; **use instead of raw
  `pip install`**, which is not recorded and is wiped on venv rebuild.

### 4. Magics refactor

`install_magic` is refactored to call `add_packages` (drops its duplicate
`_run_uv_install`), still printing installed / error to the console. `%workspace
install` already delegates to `install_magic`, so it is consolidated transitively;
refresh its one-line help text to mention persistence. No new cell magic is added
— `%workspace` stays a line magic.

### 5. Agent system prompts (plugins_sciqlop)

Add one bullet to the write-tools section of each `SYSTEM_PROMPT`
(`sciqlop_claude`, `sciqlop_opencode`, `sciqlop_copilot`): to add a Python
dependency, call `sciqlop_install_package` — never `pip install` directly (not
recorded; lost on venv rebuild).

### 6. Tutorial notebook

`11-SciQLopWorkspace.ipynb` §3: add a markdown + code cell showing the
programmatic API —
`from SciQLop.user_api.packages import install_packages; install_packages("astropy")`
— next to the existing `%install` example, and a one-line note that AI agents add
dependencies via the gated `sciqlop_install_package` tool, which routes through the
same `add_packages` path. Keep the existing magic examples and reference table.

## Data flow

`sciqlop_install_package` (agent, gated+IO-pool) ─┐
`install_packages` (console / scripts) ───────────┼─→ `Workspace.add_packages`
`%install` / `%workspace install` (magics) ───────┘        │
                                                           ├─ `uv pip install` (venv, now)
                                                           └─ append `requires` + save manifest (persist)
next launch → `prepare_workspace` → regenerate `pyproject.toml` → `uv sync`.

## Error handling

- uv failure → structured `error` carries stderr; manifest is **not** mutated, so a
  failed install leaves no phantom entry.
- No active workspace → `install_packages` returns the error dict (the tool renders
  it; no exception).
- The tool wrapper (`_text_tool`) already converts handler exceptions to error
  content.

## Testing

SciQLop test env (`uv run pytest --no-xvfb`):
- **`Workspace.add_packages`** with `_uv_install` / subprocess stubbed:
  (a) all already present → no uv call, manifest unchanged, `already_present` set;
  (b) new pkg, uv success → `installed=[pkg]`, `requires` updated, manifest saved;
  (c) uv failure → `ok=False`, `error` carries stderr, `requires` unchanged;
  (d) mix → only new in `installed`, old in `already_present`.
- **`user_api.install_packages`**: no active workspace → error dict; with a fake
  workspace → delegates and returns its result.
- **Tool**: `build_sciqlop_tools` includes `sciqlop_install_package` with
  `gated=True` and the array schema; handler returns `{content}` and invokes
  `install_packages`.
- **Magic**: `%install` / `%workspace install` route through `add_packages`
  (stub `add_packages`, assert delegation + console output).

## Out of scope

- Uninstall / remove-package API (possible follow-up).
- The appstore `installed_packages` settings registry (a separate, global
  plugin-package mechanism — unchanged).
- Any GUI package-management surface.
- Running `uv sync` / regenerating `pyproject.toml` at runtime — `add_packages`
  installs additively now; full reconciliation already happens at next launch.
