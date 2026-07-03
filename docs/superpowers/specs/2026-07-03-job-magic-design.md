# `%job` cell/line magic — user-facing access to the Jobs component

**Date:** 2026-07-03
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — new `SciQLop/user_api/magics/job_magic.py`, additions to
`completions.py` and `register_all_magics`).

## Problem

The background job runner (`SciQLop/components/jobs/`, `user_api/jobs.py`:
`submit_job`/`job_status`/`list_jobs`/`cancel_job` — see
`docs/superpowers/specs/2026-07-02-agent-job-runner-design.md`) shipped with an
agent tool surface (`sciqlop_submit_job` etc.) but no notebook-facing magic. A
user working directly in a notebook cell (not through the agent) currently has
no way to submit/inspect/cancel a job without dropping into `exec_python` and
calling `user_api.jobs` functions by hand. This closes that gap, following the
same "thin magic wrapping an existing user_api module" shape as `%workspace`
(wrapping `user_api.packages`/`workspaces`) and `%install`
(wrapping `user_api.packages.install_packages`).

## Design

### Shape: one `%job` line magic, subcommand-dispatched

Mirrors `SciQLop/user_api/magics/workspace_magic.py` exactly: a
`SUBCOMMANDS` dict (name → help text) and a `DISPATCH` dict (name → handler),
with the magic function doing `shlex.split(line)`, popping the first token as
the subcommand, and calling the matching handler with the rest. Unknown
subcommand raises `UsageError` listing valid ones (same as `%workspace`).

New file: `SciQLop/user_api/magics/job_magic.py`.

### Subcommands

- **`submit [--name NAME] <command>`** — delegates to
  `user_api.jobs.submit_job(command, name)`. Parsing note: the command is
  arbitrary shell text (may itself contain flags, `&&`, quoting), so it is
  **not** `shlex.split`. Only a leading `--name VALUE` is special-cased by
  splitting the line on whitespace at most twice
  (`line.split(None, 2)` when it starts with `--name`); everything after that
  point is passed through verbatim as `command`. Missing command after
  stripping `--name` raises `UsageError`. Prints
  `Submitted job <id>: <name>`.
- **`status <id>`** — delegates to `user_api.jobs.job_status(id)`. Prints
  `id`/`name`/`command`/`status`/`submitted_at`/`finished_at`/`exit_code`,
  then the log tail under a `--- log ---` header (only if non-empty).
  Unknown id: the underlying `KeyError` from `JobsBackend.job_status` is
  caught and re-raised as `UsageError(f"No such job '{id}'")`.
- **`list`** — delegates to `user_api.jobs.list_jobs()`. Prints an
  fixed-width columns table `ID  NAME  STATUS  SUBMITTED`, sorted by
  `submitted_at` ascending. Prints `No jobs.` when the list is empty.
- **`cancel <id>`** — delegates to `user_api.jobs.cancel_job(id)`. Same
  unknown-id handling as `status`. Prints `Cancelled job <id>.`
- **`help`** — prints usage + the `SUBCOMMANDS` table, same style as
  `%workspace help`.

No subcommand (bare `%job`) defaults to `list`, matching `%workspace`'s
default-to-`status` behavior.

### Completion

New `_match_job` in `SciQLop/user_api/magics/completions.py`, registered in
`register_all_magics` alongside the other `_match_*` completers:
- First token after `%job `: complete subcommand names from `SUBCOMMANDS`
  (same logic as `_match_workspace`'s subcommand branch).
- Second token, when subcommand is `status` or `cancel`: complete job ids
  from `user_api.jobs.list_jobs()`.

### Registration

One addition to `register_all_magics` in
`SciQLop/user_api/magics/__init__.py`:
```python
shell.register_magic_function(job_magic, magic_kind="line", magic_name="job")
...
shell.Completer.custom_matchers.append(_match_job)
```

### Testing

New `tests/test_magics/test_job_magic.py`, matching
`tests/test_magics/test_workspace_magic.py`'s style: monkeypatch the
`user_api.jobs` functions the magic calls, assert dispatch to the right
handler, printed output shape, and `UsageError` on unknown subcommand /
missing command / unknown job id. A small completion test in
`tests/test_magics/test_completions.py` alongside the existing
`_match_workspace` tests.

## Out of scope

A `%%job` cell-magic variant (running a whole cell's Python as the job body)
— the job runner is shell-command-only by design (see the 2026-07-02 job
runner spec, decision 2); job id tab-completion beyond the two subcommands
that take one; any change to `user_api/jobs.py` or the `JobsBackend` itself.
