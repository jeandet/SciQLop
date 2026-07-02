# Agent product introspection — `sciqlop_describe_product`

**Date:** 2026-07-02
**Status:** Approved (design)
**Repo:** SciQLop (in-tree — new `SciQLop/components/agents/tools/describe.py` + registration in `_builder.py`).

## Problem

From the in-app Claude feedback: discovering a product's variable short-names,
units, coordinate frame, fill value, dimensionality, and actual time coverage
was a repeated round-trip of trial-and-error before every fetch (the FILLVAL
zoo — 99999.9 / −9999 / −1e31; SolO MAG being RTN; DSCOVR plasma ending
2019-06). `sciqlop_products_tree` gives the path; `sciqlop_speasy_inventory`
gives a little more, but neither returns a structured, per-product description.

This is Tier-2 item #1 of the agent-MCP-tooling backlog (Tier-1 shipped
2026-07-02). It composes directly with `sciqlop_fetch`: **describe → fetch**.

## Key finding (grounds the design)

The metadata a `ParameterIndex` exposes **without any fetch** is strongly
provider-dependent:

- **CDA (ISTP/CDF):** rich — `FILLVAL`, `spz_shape`, component labels
  (`LABL_PTR_1`), `CATDESC`, `UNITS`, `cdf_type`, `dataset`, `start_date`,
  `stop_date`.
- **AMDA:** sparser — `dim_1`/`dim_2`/`size`, `units`, `display_type`,
  `sampling_mode`; no `FILLVAL`, often no coverage dates.
- **SSC (orbit):** different again — `Resolution`, `ResourceId`, coverage.

There is no uniform schema, and intra-range **gaps require actual data**. The
design therefore normalizes what it can and passes the rest through verbatim,
and offers an opt-in probe fetch for the provider-uniform ground truth.

## Design

A new **read-only, ungated** tool `sciqlop_describe_product`, `thread=True`
(inventory access / probe fetch do blocking I/O with no Qt affinity), returning
the `{"content": [{"type": "text", ...}]}` markdown shape. Registered in the
read-only `tools` list in `build_sciqlop_tools`.

### Input & resolution

```
sciqlop_describe_product(product, probe=False, start=None, stop=None)
```

- `product` (string, required) — auto-detected per identifier: contains `//`
  → ProductsModel path (resolved via `ProductsModel.instance().node(parts)`,
  then the node's `speasy_id` metadata → its `ParameterIndex`); otherwise a
  speasy identifier — a spz_uid (`provider/uid`) or a dotted inventory path
  (e.g. `cda.AC_H2_CRIS...`) — resolved against `spz.inventories`.
- The resolution normalises to a speasy `ParameterIndex` (the metadata carrier).
  *Plan-time confirmation:* the exact spz_uid → `ParameterIndex` reverse lookup
  (via `spz.inventories.flat_inventories[provider].parameters` or equivalent)
  and the ProductsModel-node → `speasy_id` hop are verified during planning,
  the same way the Tier-1 `//`-resolver was. If a `//`-path cannot be mapped to
  a `ParameterIndex`, the tool falls back to describing the ProductsModel node's
  own metadata (provider, parameter_type, components, tooltip).
- `probe` (bool, default `False`), `start`/`stop` (string ISO-8601 or number
  POSIX seconds, optional) — see Probe.

### Metadata-only output (default)

Normalize what the `ParameterIndex` exposes into a stable envelope, then pass
through the remaining raw attributes so nothing is lost:

- **Normalized fields** (each omitted when the provider lacks it — no fake
  nulls): name, provider, uid/path, units, coverage `{start, stop}` (from
  `start_date`/`stop_date`), shape/dims (`spz_shape`, else `dim_1`/`dim_2`/
  `size`), fill value (`FILLVAL` when present), component labels (`LABL_PTR_1`,
  else `components`), description (`CATDESC`, else `description`).
- **Raw passthrough:** all other non-underscore attributes, values trimmed to a
  short length, so provider-specific keys (`cdf_type`, `ResourceId`, …) still
  surface.
- Rendered as markdown.

### Probe (`probe=True`) — provider-uniform ground truth

Fetch a small sample and augment the envelope with facts read from the returned
`SpeasyVariable`:

- **Window:** `start`/`stop` if given; else a short default span ending at
  `stop_date` (last 24 h of coverage). If coverage `stop_date` is unknown and no
  window is given, report that a window is required and skip the probe (still
  return the metadata-only envelope).
- **Adds:** real `values.shape`; actual fill value (`var.fill_value` / meta);
  coordinate frame from `var.meta` when present (e.g. `COORDINATE_SYSTEM`);
  median cadence (median Δ of `var.time`); and NaN-gap fraction + count **within
  the probed window**.
- **Out of scope:** full-range gap mapping (needs a full fetch — the summary
  points the caller at `sciqlop_fetch` + `sciqlop_inspect`). Read-only; binds
  nothing to the kernel.
- A probe fetch error degrades gracefully: return the metadata-only envelope
  plus a one-line "(probe failed: …)" note; never raise.

### Testing (offline)

- **Pure normalization:** feed a fake `ParameterIndex`-like object in two
  shapes — a CDA-style one (`FILLVAL`, `spz_shape`, `LABL_PTR_1`, `CATDESC`,
  coverage) and an AMDA-style sparse one (`dim_1`/`dim_2`/`size`, `units`, no
  FILLVAL) — and assert the normalized envelope fields, the raw passthrough, and
  that absent fields are omitted.
- **Probe:** inject a fake fetch backend returning a `FakeVar` (numpy
  values/time, `.meta`, `.fill_value`) → assert probe adds real shape, fillval,
  frame, median cadence, and NaN-gap fraction; and that omitting `start`/`stop`
  uses the default end-of-coverage window; and that a probe exception yields the
  metadata-only envelope + a "(probe failed: …)" note.
- **Registration:** `qtbot`; tool present, **ungated**; schema — `product`
  required; `probe`/`start`/`stop` optional. (Importing from `agents.tools.*`
  needs a QApplication, so tests take `qtbot` and import inside the function.)
- **Resolution:** `//`-path vs speasy-id routing exercised via an injected
  resolver so the logic seam is covered offline.

## Out of scope (tracked in backlog)

Full-range gap mapping; ephemeris/coordinate transforms (3DView); DOI/ADS
full-text; file inspector; background-job runner.
