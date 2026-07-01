# Agent fetch tools — fetch-into-kernel, friendlier errors, inline figures

**Date:** 2026-07-01
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — tools live in `SciQLop/components/agents/tools/`, wrapped by both the Claude and Opencode backends via `build_sciqlop_tools()`).

## Problem

Feedback from a Claude session that ran a real multi-day study inside SciQLop:
the single most-repeated boilerplate was always the same shape — *fetch N
products → scrub fills → resample to a common grid → align → compute*. Today the
agent does all of this by hand through `sciqlop_exec_python`, which (a) burns
context on repeated fetch/align scaffolding, (b) forces the model to juggle two
product-identifier namespaces, and (c) invited a class of provenance bugs when
the model bounced between the embedded kernel and a standalone venv
(cross-version pandas pickles, missing cache, speasy proxy/WS fallbacks).

Two smaller pains rode along: enormous pandas tracebacks (hundreds of lines)
cost real context on every failure, and viewing a computed result meant
save-PNG-then-Read.

This is the **Tier-1 slice** of a larger agent-MCP-tooling backlog (see
`memory/backlog.md` → Agents → "Agent MCP tooling"). Tiers 2–3
(`sciqlop_describe_product`, ephemeris/transform via 3DView, DOI full-text, file
inspector, background-job runner) are scoped separately.

## Design principle (non-negotiable)

`sciqlop_fetch` loads results **into the shared kernel** under a caller-chosen
name and returns only a compact **handle + summary** — never raw arrays as JSON
(that would blow up context on any real fetch). Compute happens afterward on the
handle via `sciqlop_exec_python`. These tools remove boilerplate; they do **not**
replace `exec_python`.

The tools reuse the existing persistent kernel
(`workspaces_manager_instance()._kernel_manager`, shared with JupyterLab), the
same one `sciqlop_exec_python` / `sciqlop_kernel_vars` / `sciqlop_inspect`
already run against. Running the fetch in-process (warm cache, one env, no
WS/proxy juggling) is what collapses the provenance-bug class to a single code
path.

## Components

Three tools added to `build_sciqlop_tools()` in
`SciQLop/components/agents/tools/_builder.py`, each backed by a small handler
module under `tools/`. All follow the existing `{name, description,
input_schema, handler, gated}` dict convention and return the `{"content":
[...]}` tool shape.

### Component 1 — `sciqlop_fetch` (new: `tools/fetch.py`) — gated

Gated like `sciqlop_exec_python` (it mutates the kernel namespace); available
only when `allow_writes=True` and the user approves the call.

**Input schema**

| param | type | required | default | notes |
|-------|------|----------|---------|-------|
| `products` | array[string] | yes | — | each item is a ProductsModel `//`-path **or** a speasy `spz_uid`; auto-detected per item |
| `start` | string \| number | yes | — | ISO-8601 string or POSIX seconds; parsed via speasy's datetime coercion |
| `stop` | string \| number | yes | — | same |
| `name` | string | yes | — | kernel binding name for the result |
| `cadence` | string | no | `None` | e.g. `"1min"`, `"5s"`; `None` → raw native cadence, no resample |
| `overwrite` | bool | no | `false` | rebind `name` even if it already exists |
| `preview` | bool | no | `false` | append one small multi-panel PNG image block to the summary |

**Flow** (one level of abstraction — orchestration only):
`resolve → fetch → (scrub + grid + align) → bind → summarize`.

1. **Resolve (auto-detect, per item).** An id containing `//` is a ProductsModel
   path, resolved through the same registry `plot_product` uses — extracting the
   data rather than plotting it. Otherwise it is a speasy `spz_uid` fetched via
   `speasy.get_data`.
   *Open implementation question for planning:* confirm the `//`-path → data
   resolver is cleanly separable from the plot pipeline. Fallback if not: read
   the ProductsModel leaf's underlying `spz_uid` and fetch via speasy.

2. **Fetch.** In-process against the workspace's speasy (warm cache, configured
   proxy). Network/parse errors for one product are captured, not raised (see
   partial success).

3. **Scrub + grid — only when `cadence` is given.** Replace each variable's
   `FILLVAL` (and documented invalid sentinels) with `NaN` using its metadata,
   then **linearly interpolate** every product onto a common time grid spanning
   `[start, stop]` at `cadence`. Gaps remain `NaN` (no extrapolation across
   them). Linear is the sole method for v1; alternate resample methods are a
   documented future extension (YAGNI now). With no `cadence`, products are bound
   at native cadence with no resample.

4. **Bind.** `name` is bound in the kernel namespace to a **dict of
   `SpeasyVariable`s keyed by short-name** (a single product still yields a
   1-entry dict, for a uniform shape). When `cadence` is given, every variable in
   the dict shares the common time axis. **If `name` already exists and
   `overwrite` is false, the tool errors** (`name 'X' already bound (type …);
   pass overwrite=True`) and binds nothing.

5. **Summarize (text always).** Markdown:
   - header: binding name, entry count, and — when gridded — cadence, point
     count, and time range;
   - per variable: short-name, units, shape, coverage % with gap ranges,
     `min`/`mean`/`max`, fill count;
   - footer: the bridges — ``NAME['<short>'].to_dataframe()`` and
     ``.to_dataarray()`` — so the model can drop into pandas/xarray on demand.
   With `preview=true`, append one small multi-panel PNG (one panel per entry) as
   an image content block.

6. **Partial success.** A product that fails to resolve or fetch is reported in
   the summary (one line per failure with the reason); successfully fetched
   products still bind. One bad id does not sink the batch. If *every* product
   fails, nothing binds and the summary is all failure lines.

### Component 2 — `sciqlop_exec_python` traceback truncation (modify existing handler in `_builder.py`)

When a submitted cell raises and the rendered traceback exceeds a threshold
(~60 lines or ~4000 chars), return **head (~20 lines) + an elision marker +
tail (~20 lines)**; shorter tracebacks pass through unchanged. `stdout`,
`stderr`, and `result` handling are untouched. Always-on (no new param): the
tail carries the actual exception, which is what matters, and the model can
re-run for the full trace if it needs it.

### Component 3 — `sciqlop_show_figure` (new: `tools/figure.py`) — read-only

A tiny, ungated tool that keeps `sciqlop_exec_python` pure. It grabs the current
matplotlib figure from the kernel — `plt.gcf()` when `plt.get_fignums()` is
non-empty — renders it to PNG, and returns it as an image content block. If
there is no active figure it returns a clean message (never raises). Sibling to
the existing `sciqlop_screenshot_*` tools, but for matplotlib rather than
SciQLop panels.

## Testing (TDD, offline)

Stub the data provider (monkeypatched speasy fetch returning fake
`SpeasyVariable`s) and a fake kernel namespace so the suite stays network-free
and fast. Cases:

- raw single-product fetch → 1-entry dict bound, summary fields correct;
- multi-product + `cadence` → all entries share one time axis, coverage/gap
  reporting correct;
- `//`-path resolution routes to the ProductsModel resolver; bare uid routes to
  speasy;
- name collision → error when `overwrite=false`; rebinds when `overwrite=true`;
- `preview=true` → an image content block is present; default → text only;
- partial failure → good products bind, failed ones reported; all-fail → nothing
  bound;
- `exec_python` long traceback → head+tail with elision; short traceback →
  unchanged;
- `show_figure` with an active figure → image block; with none → clean message.

## Out of scope (tracked in backlog)

`sciqlop_describe_product`; ephemeris + coordinate transforms (3DView CDPP REST
— `get_trajectory`, `get_transform_matrices`); DOI/bibcode full-text via ADS;
generic CDF/netCDF/HDF5 file inspector; background-job runner. Field-aligned
coordinates stay in-kernel via `exec_python` (data-dependent, not a 3DView
concern).
