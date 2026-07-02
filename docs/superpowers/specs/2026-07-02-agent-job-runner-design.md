# Background job runner — Jobs component

**Date:** 2026-07-02
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — new component `SciQLop/components/jobs/`, new `SciQLop/user_api/jobs.py`, new agent tools).

## Problem

From the in-app Claude feedback: long-running work (an 11-year data build, an
overnight survey, PRADAN downloads) was run via `nohup` + a log file + a
hand-rolled bash "waiter," because nothing inside SciQLop lets the agent
submit something and check back later. This is Tier-3 of the agent-MCP-tooling
backlog — the highest-effort item, but per user direction (2026-07-02) also
judged the highest-leverage: it showed up three separate times in the raw
feedback, and it benefits every other tool whenever a call needs to run long,
not just one workflow.

This also closes **GitHub issue #25** ("Add a task manager like QTC") — an
open, unaddressed, several-times-referenced gap: "Operations like package
install while loading a workspace can be quite long, the user needs to know
that dependencies aren't installed yet."

## Key finding (grounds the design)

A codebase survey (2026-07-02) confirmed **no job/task abstraction exists
anywhere** in SciQLop. Three prior specs (`2026-07-01-agent-fetch-tools`,
`2026-07-02-agent-describe-product`, `2026-07-02-agent-doi-fulltext`) already
deferred "background-job runner" by name as out of scope. Relevant existing
substrate found, reused below:

- **`_IO_POOL`** (`components/agents/tools/_builder.py`) — the app's only
  general worker pool; NOT reusable here because it's threads inside SciQLop's
  own process, which die when SciQLop closes.
- **`RemoteWorker`** (`components/plotting/backend/remote/`) — subprocess +
  duplex-pipe + `QSocketNotifier`-pump pattern is architecturally sound but
  hard-wired to plot-data's "coalesce to latest request, drop older ones"
  semantics — wrong for jobs, which must never drop earlier work. Not reused
  directly.
- **`WorkspaceManifest`** (`components/workspaces/backend/workspace_manifest.py`)
  — the exact precedent for durable, restart-surviving state: a `@dataclass`
  round-tripped to a TOML file via `tomllib`/`tomli_w`, `load()`/`save()`
  staticmethods, `field()` for nested lists, a documented TOML-format
  docstring. `job_record.py` (below) follows this pattern exactly.
- **`user_api/packages.py`** — the exact precedent for a thin `user_api`
  module wrapping a component's backend (mirrors `Workspace.add_packages()`).
  `user_api/jobs.py` (below) follows this shape.
- **`SciQLopMainWindow.closeEvent`** (`core/ui/mainwindow.py:475`) — already
  has a deferred-close idiom (`_schedule_async_close()` → `event.ignore()`)
  used for async plugin teardown. The running-jobs warning (§6) reuses this
  same idiom rather than inventing a new one.
- **No cross-agent-turn mechanism exists today** — `sciqlop_wait_for_plot_data`
  blocks *within* one tool call; `ToolActivityBlock` is transcript rendering
  only. This confirms the core gap this feature closes: submit now, check
  status in a later, unrelated turn.

## Two decisions made explicit (both confirmed)

1. **Survival scope: restart-survives**, not just cross-turn-in-one-session.
   The motivating use cases (multi-day builds, overnight surveys) can easily
   outlive a chat session or a SciQLop restart; a session-only runner would
   not actually replace the nohup hack.
2. **Job payload: a shell command**, not arbitrary Python. The agent builds
   the actual work with tools it already has (`exec_python`, notebook cells, a
   script written to the workspace), then hands the *command that runs it* to
   the job runner purely to detach + track it. No cloudpickle payload risk, no
   separate interpreter/venv bootstrap for the detached process.

## Design

### Layer stack (component → user_api → agent tools)

```
SciQLop/components/jobs/backend/
  job_record.py     — Job dataclass + TOML load/save (mirrors WorkspaceManifest)
  jobs_backend.py   — JobsBackend: submit/cancel/list/status, detached subprocess
                       launch, startup reconciliation, QObject signals
SciQLop/user_api/jobs.py
                    — submit_job(command, name) -> str, job_status(id) -> dict,
                       list_jobs() -> list[dict], cancel_job(id) -> None
SciQLop/components/agents/tools/jobs.py
                    — sciqlop_submit_job / sciqlop_job_status / sciqlop_list_jobs /
                       sciqlop_cancel_job — thin delegation to user_api.jobs
```

No `ui/` subdirectory yet — deliberately not scaffolded (YAGNI). The
signal-emitting `JobsBackend` (below) is what makes adding a future
"browse running jobs and job history" panel cheap without a redesign: it
would subscribe to the same in-memory model and signals that `list_jobs()`
already reads from, not re-derive job state from scratch.

### Execution — genuine OS-level detachment, same mechanism as `nohup`

`submit_job(command, name)`:
1. Generates a job id, creates its TOML record and paths (`log_path`,
   `marker_path`) under `.sciqlop-jobs/` in the active workspace directory.
2. Wraps `command` in a small shell script that, on completion, writes the
   exit code to `marker_path` (e.g. `{ <command>; } > <log_path> 2>&1; echo $? > <marker_path>`).
3. Launches it via `subprocess.Popen([...], start_new_session=True)` — the
   POSIX `setsid` equivalent, detaching it from SciQLop's process group and
   session — and does **not** wait on it.

This survives SciQLop closing or crashing: the job is no longer a child of
SciQLop's process once detached (on Linux it reparents to init/a subreaper),
exactly like `nohup ... &`.

### Persistence & status computation

Each job's `Job` record (`job_record.py`, TOML, same dataclass/load/save shape
as `WorkspaceManifest`): `id`, `name`, `command`, `pid`, `log_path`,
`marker_path`, `submitted_at`, `finished_at` (set once known).

Status is **computed, not stored**, from marker + pid at query time:
- marker file present → `done` (exit code = marker file contents)
- marker absent, `os.kill(pid, 0)` succeeds → `running`
- marker absent, pid not alive → `crashed` (e.g. `SIGKILL`, no chance to
  write the marker)

### `JobsBackend` — reconciliation + in-memory model

Singleton accessor `jobs_backend_instance()` (mirrors
`workspaces_manager_instance()`). On first construction, scans
`.sciqlop-jobs/*.toml`, loads each record, computes current status, and
populates an in-memory `dict[str, Job]` — reads (`list_jobs`, `job_status`)
serve from this model, not a filesystem scan every call. A `QObject` with
signals `job_added` and `job_status_changed` (emitted on a detected
transition, e.g. `running`→`done`, recomputed on-demand when something calls
`job_status`/`list_jobs` — no internal polling thread; nothing runs
continuously inside SciQLop for this).

### Tool surface

- `sciqlop_submit_job(command: str, name: str) -> str` — **gated** (spawns a
  process). Returns the job id.
- `sciqlop_job_status(id: str) -> dict` — read-only. Status + a tail of the
  log file.
- `sciqlop_list_jobs() -> list[dict]` — read-only. All known jobs + status, so
  the agent can rediscover work across a restarted session without
  remembering ids.
- `sciqlop_cancel_job(id: str)` — **gated**. `os.kill(pid, SIGTERM)`; the
  record is left as-is (status computation will naturally observe the process
  died — `crashed` if no marker was written, or `done` if the command trapped
  the signal and exited cleanly).

### Close-time warning for running jobs

`SciQLopMainWindow.closeEvent` (`core/ui/mainwindow.py:475`) gets a check
inserted before it proceeds: if `jobs_backend_instance().list_jobs()` has any
`running`-status job, show a modal warning — "N job(s) are still running and
will continue in the background: `<names>`. Close anyway?" — Continue/Cancel.
Continue proceeds with the existing close flow (jobs keep running detached,
as designed); Cancel calls `event.ignore()`, reusing the same deferred-close
idiom the file already has for async plugin teardown. Purely
informational/confirmatory — never blocks or kills a job.

### Testing

- **Pure:** `job_record.py` TOML round-trip; status computation
  (`done`/`running`/`crashed`) as a plain function taking injected
  `os.kill`/path-exists checks — no real subprocess in unit tests.
- **`JobsBackend`:** submit builds the correct wrapper script + `Popen` call
  (mock `subprocess.Popen`, assert `start_new_session=True` and the command
  wrapping); reconciliation scan populates the in-memory model from fixture
  TOML files; signal emission on a detected status transition.
- **One real-subprocess integration test:** spawn an actual short-lived
  detached command (e.g. `sleep 0.2 && exit 3`), poll until its marker
  appears, assert the exit code — kept small and fast, the only test touching
  a real process.
- **`user_api/jobs.py`:** thin-wrapper delegation tests.
- **Agent tools:** registration/gating (`qtbot` pattern, matching every other
  tool in this codebase), handler delegation via monkeypatch.
- **Close-warning:** a widget-level test that a running job triggers the
  modal and `event.ignore()` on Cancel, and that no jobs → close proceeds
  unprompted (matching existing `mainwindow` test patterns).

## Out of scope (tracked in backlog)

A UI panel for browsing running jobs/history (the signal-emitting model is
designed to make this cheap later, not built now); ephemeris/coordinate
transforms (3DView); generic CDF/netCDF/HDF5 file inspector; live streaming
of job stdout into the existing Log panel (nice-to-have, not required for the
submit/poll loop to work — a job's log is already a plain file
`sciqlop_job_status` can tail).
