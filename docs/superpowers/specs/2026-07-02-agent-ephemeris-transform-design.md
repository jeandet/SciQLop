# Agent ephemeris & coordinate transforms — `sciqlop_ephemeris` / `sciqlop_transform`

**Date:** 2026-07-02
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — new `SciQLop/components/agents/tools/orbits.py` +
registration in `_builder.py`).

## Problem

SciQLop has no ephemeris or coordinate-transform tooling today. Studies that
need spacecraft position/velocity (e.g. Parker-spiral / aberration
corrections) or need to rotate a field-aligned or mission-frame vector into a
common frame (GSE→HEEQ, etc.) have no in-app way to get exact answers — the
agent either guesses sign conventions or asks the user to hand-derive them.
This is Tier-2 item #2 of the agent-MCP-tooling backlog (all other Tier-1/2/3
items shipped 2026-07-02).

Field-aligned coordinates (FAC/perp/para) stay out of scope — they need local
B-field data and are computed in-kernel via `exec_python`, not sourced from an
ephemeris service.

## Backend research (2026-07-02)

Live-probed `https://3dview.irap.omp.eu/webresources/` (CDPP 3DView REST):

- **No auth, no visible rate limiting.** Plain `GET`, `format=json|csv|cdf`.
- `get_bodies` / `get_frames` — full self-describing lists (247 bodies incl.
  spacecraft/planets/small bodies, 38+ frames incl. mission-specific ones like
  `MSO`/`VSO`) with descriptions. Change rarely.
- `get_trajectory?body=&frame=&start=&stop=&sampling=` → per-sample
  **`position`** (km) **and** `speed` (km/s) — confirmed live for `Solar
  Orbiter`/`HEEQ`. Exactly what aberration correction needs.
- `get_transform_matrices?fromframe=&toframe=&start=&stop=&sampling=` →
  per-sample 3×3 **`matrix`** — confirmed live for `GSE`→`HEEQ`.
- Errors are plain-text bodies, not JSON: HTTP 500 for an unknown body
  (`"Error during orbit files computation: Body NOPE not found"`), HTTP 400
  for a bad frame (`"Frame id not recognized: NOPE"`) or a missing required
  param (`"Missing stop time parameter"`).

**speasy already has an `ssc` provider** (NASA SSCWeb) that returns
trajectory **position only**, for NASA-mission spacecraft only, with no
generic vector-transform capability. 3DView is a strict superset for this
feature (position **and** velocity, spacecraft **and** planets/small bodies,
arbitrary frame-pair rotation matrices) — so **3DView is the only backend**;
speasy's `ssc` provider is not used here.

## Design

Two new **gated** tools (they bind results into the kernel, mutating shared
state — same class as `sciqlop_fetch`) plus one **read-only** discovery tool,
all `thread=True` (blocking network I/O, no Qt affinity). A new pure-logic
module `SciQLop/components/agents/tools/orbits.py` mirrors `fetch.py`: the
HTTP call is injected (`http_get: Callable`) so parsing/binding logic is
unit-tested offline; `_builder.py` wires in `speasy.core.http.get` — the same
client `literature.py`/`fulltext.py` already use, no new dependency. Every
request explicitly passes `format=json` (never relies on the server's
default) for a deterministic response shape.

### `sciqlop_orbit_bodies_and_frames()` — read-only

No params. Calls `get_bodies` + `get_frames`, renders two flat name lists
(`### bodies (N)` / `### frames (N)`, comma-joined, frame entries include
their `desc`). Wrapped in `speasy.core.cache.CacheCall` (same pattern as
`literature.py`'s ADS/arXiv search caching) with a multi-day retention, since
these lists change rarely — avoids a round-trip on every session.

### `sciqlop_ephemeris(body, frame, start, stop, sampling, name, overwrite=False)` — gated

- `frame` defaults server-side to `J2000` if omitted (matches 3DView's own
  default); `sampling` defaults to 3600 s.
- Same existing-name guard as `sciqlop_fetch`: refuses to clobber `name` in
  the kernel namespace unless `overwrite=True`.
- Calls `get_trajectory`; on success, parses the JSON into **two**
  `SpeasyVariable`s (via `speasy.products.variable`, the same construction
  the `ssc` provider uses internally): `position` (columns `X,Y,Z`, unit
  `km`) and `speed` (columns `Vx,Vy,Vz`, unit `km/s`), sharing one time axis.
  Binds `shell_ns[name] = {"position": ..., "speed": ...}` — a
  `Dict[str, SpeasyVariable]`, the exact same shape `sciqlop_fetch` binds, so
  `name["position"].to_dataframe()` etc. already works.
- Returns a text summary reusing `fetch.py`'s existing pure `_var_line`
  helper per component (coverage/shape/min-mean-max line) rather than
  duplicating that rendering logic — a targeted, in-scope reuse, not a new
  abstraction.
- On a non-2xx response, returns the response body text verbatim as the
  tool's error content (3DView's messages are already human-readable) — no
  retry, no per-status special-casing.

### `sciqlop_transform(from_frame, to_frame, start, stop, sampling, name, overwrite=False)` — gated

- `from_frame`/`to_frame` default to 3DView's own defaults (`J2000`/
  `ECLIPJ2000`) if omitted; `sampling` defaults to 3600 s, same as
  `sciqlop_ephemeris`.
- Calls `get_transform_matrices`; parses into a single `SpeasyVariable` of
  shape `(N, 3, 3)` (values = the per-sample rotation matrices, one time
  axis). Binds `shell_ns[name] = matrix_var` (not a dict — one variable, no
  ambiguity about component naming for a matrix).
- **Matrices only** — does not apply the rotation to any existing kernel
  variable. The agent applies it itself via `exec_python`
  (`np.einsum('nij,nj->ni', R, B)` after interpolating the matrix time axis
  onto the target variable's time axis). Keeps the tool simple and avoids
  baking in assumptions about the caller's data shape/cadence.
- Same overwrite guard and error-passthrough behavior as `sciqlop_ephemeris`.

### Error handling

`speasy.core.http.get(...).ok` gate (`True` for 200/304) on every call; on
failure, `response.text` becomes the tool's sole content string. This mirrors
`describe.py`'s probe-failure-degrades-to-a-note philosophy but simpler here
since there's no metadata-only fallback to degrade to — ephemeris/transform
have nothing useful to return without a successful fetch.

### Testing (offline)

Following `test_fetch_tool_registration.py`'s pattern (inject a fake
`http_get`, no network):

- `sciqlop_ephemeris`: happy-path parse (position + speed, correct
  units/columns/shapes), bad-body 500 → error text passthrough, bad-frame 400
  → error text passthrough, missing-param 400 → error text passthrough,
  existing-name-without-overwrite guard, overwrite=True replaces.
- `sciqlop_transform`: happy-path parse (matrix shape `(N,3,3)`), same
  error/overwrite cases as above.
- `sciqlop_orbit_bodies_and_frames`: parses a fake bodies/frames JSON into
  the two rendered lists; a second call within the cache window does not
  re-invoke `http_get` (cache hit).
- **Registration:** `qtbot`; both data tools registered **gated**, listing
  tool registered **read-only**; schemas match the params above (required vs
  optional, defaults). Importing `agents.tools.*` needs a `QApplication`, so
  tests take `qtbot` and import inside the test function (existing project
  constraint, see `agent-tool-surface` memory).

## Out of scope (tracked in backlog)

Applying a transform directly to a named kernel vector (deferred — matrices
are enough for now, revisit if this becomes a repeated agent pattern);
field-aligned coordinates (needs local B, stays in-kernel); generic file
inspector (CDF/netCDF/HDF5, separate backlog item).
