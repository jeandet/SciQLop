# Full-review backlog — 2026-06-09

Findings from the 2026-06-09 full code review. Workflow per item:
- **Bugs**: confirm real → failing reproducer test → fix → test passes.
- **Performance**: measure baseline → fix → measure gain.
- **API inconsistencies**: fix without breaking the published `user_api` surface.

Status: ☐ todo / ◐ in progress / ☑ done / ✗ withdrawn (not a real bug)

## Bugs

| # | Status | Item |
|---|--------|------|
| B1 | ☑ | `CatalogService._persist` never persists *modified* events (same uuid, changed times/meta); `_set_events` swap severs TscatEvent persistence path (`user_api/catalogs/_service.py`) — fixed: in-place updates via cached event setters + set/remove_event_meta; cache keeps provider-wired objects. Tests: `test_catalog_user_api.py::test_save_persists_*` |
| B2 | ☑ | `PlotPanel.plot(x, y, plot_index=N)` drops `plot_index` in the static-data branch (`user_api/plot/_panel.py`); breaks fluent overlay-on-same-subplot — fixed + `tests/test_plot_panel_plot_args.py` |
| B3 | ☑ | `PlotPanel.plot(product=...)` / `plot(callback=...)` kwargs collision → `TypeError: multiple values` / `callback` leaks into impl kwargs — fixed (consumed kwarg popped) |
| B4 | ☑ | `CatalogProvider.events(catalog, start, stop)` filtered by event *start* only → overlapping long events excluded; lazy overlay hid them. Naive-datetime args raised TypeError — fixed: overlap semantics + `make_utc_datetime` normalization. Tests: `test_catalog_provider.py::test_provider_events_range_query_*` |
| B5 | ☑ | cocat `Client.join_room` during reconnect backoff leaked a second `_run` loop (`if self._connected` missed backoff state); `_run` finally could clobber newer `_task` — fixed: leave on `_task is not None`, guard finally with `current_task()`. Test: `test_cocat_reconnect.py::test_join_room_during_backoff_does_not_leak_previous_loop` |
| B6 | ☑ | `PanelCatalogManager._on_event_clicked` JUMP mode: zero-duration event → zero-width range (silent no-op) — fixed: shared `_jump_to_event` helper with 1h fallback (margin factors preserved: 4.5 table-select, 0.5 span-click). Test: `test_panel_catalog_manager.py::test_manager_jump_mode_zero_duration_event_click` |
| B7 | ☑ | `user_api/catalogs/_service.py` had no `@on_main_thread` — fixed: all public methods decorated. Test: `test_catalog_user_api.py::test_service_methods_marshal_to_main_thread` |
| B8 | ☑ | **Discovered during B2 verification**: SciQLopPlots 0.27.0 renamed C++ `histogram2d` kwargs `key_bins`/`value_bins` → `x_bins`/`y_bins`; wrapper still passed old names → every histogram2d call raised the Shiboken `SciQLopPlotsBindings` NameError (7 pre-existing test failures). Fixed in `_graphs.py::_create_histogram2d` |

## Performance (measured)

| # | Status | Item |
|---|--------|------|
| P1 | ☑ | `CatalogService._persist` O(N²): per-event `events_changed`. **4001 → 1 emission** for a replace-all save of 2000 events (each emission = full overlay/table refresh). New `CatalogProvider.batch_events_update(catalog)` context manager. Guard: `test_save_emits_events_changed_once` |
| P2 | ☑ | `CatalogOverlay._add_span` QTimer per span: **2000 → 0 timers** for a 2000-event overlay (lazy creation on first range edit). Construction time unchanged within noise (~0.38 s, span creation dominates) |
| P3 | ☑ | cocat sync `httpx` login blocked the qasync loop during reconnects: measured **0.378 s loop stall** per attempt with a 0.3 s login; now `asyncio.to_thread`, stall < 20 ms. Test: `test_run_does_not_block_loop_during_slow_login` (verified failing pre-fix) |
| P4 | ☑ | `_speasy_variable_to_arrays` always copied via `.astype`: **69 → 53 ms** for 5M points, values buffer no longer copied (`ascontiguousarray(dtype=float64)`) |
| P5 | ☑ | lazy overlay `_event_colors` grew unboundedly while panning — now reassigned per refresh (bounded to visible window) |

## API inconsistencies (user_api — kept backward compatible)

| # | Status | Item |
|---|--------|------|
| A1 | ☑ | `Ellipse.line_color`/`fill_color` getters returned int rgba → now `QColor` like `Text`/`CurvedLine`/`HorizontalLine`. (Type change on the getter; setters unchanged) |
| A2 | ☑ | `remove()` now on all items via shared `_PlotItem` base. **`visible` raises `NotImplementedError`**: introspection showed `SciQLopItemInterface::visible()/set_visible()` are unimplemented pure-virtual stubs in SciQLopPlots ≤ 0.27 for ALL item classes (getter always False, setter no-op) — the old `Pixmap.visible`/`Ellipse.visible` were silent lies. **→ upstream SciQLopPlots fix needed**, then delegate again |
| A3 | ☑ | `Graph`/`ColorMap`/`Histogram2D` now wire `destroyed` and raise friendly ValueError on stale handles; `XYPlot`/`TimeSeriesPlot` bare `self._impl` routed through `_get_impl_or_raise()` |
| A4 | ☑ | Docstrings fixed: `XYPlot.plot` (no product paths), `TimeSeriesPlot.plot` (kwargs forwarded), `plot_index` (-1 appends a new subplot, not "last plot") |
| A5 | ☑ | Negative indices supported uniformly in `remove_plot`/`add_layer` (`_normalize_plot_index`); `PlotPanel.plot` now raises `ValueError` on unrecognized args (user-approved behavior change 2026-06-10). Test: `test_plot_unrecognized_args_raise` |
| A6 | ☑ | `_to_sqp_graph_type` annotation `[GraphType, _GraphType]` → `Union[...]` |
| A7 | ☑ | `create_virtual_product` asserts → `ValueError` with messages |

## VP dependencies robustness

| # | Status | Item |
|---|--------|------|
| V1 | ☑ | `get_type_hints` failure now logs a warning naming the callback (was: deps silently dropped → confusing TypeError at fetch time); `signature(eval_str=True)` guarded with fallback |
| V2 | ☑ | `EasyProvider.__init__` no longer mutates the caller's `metadata` dict |
| V3 | ☑ | `ensure_dt64` accepts any `datetime64` unit (converts to ns), error names the dtype; `validation.py` `_check_time_dtype` kept in sync |

Guard tests for A/V items: `tests/test_api_consistency.py`.

## Pre-existing failures — root-caused and FIXED 2026-06-10

The suite-ordering failures all traced back to ONE root cause plus three local bugs:

**Root cause — plugin dual import.** `load_module` spec-loaded bundled plugins
as top-level `<name>` while tests/notebooks import them as
`SciQLop.plugins.<name>` → two module objects per plugin, two copies of every
class. Consequences observed:
- tscat: the plugin's provider saw the test provider's `GetOrphanEventsAction`
  (other class identity) → `isinstance` exclusion failed → "external DB change"
  path wiped its event cache → the 4 `*_after_event_loop` failures.
- speasy: canonical import re-executed `settings.py` → `ValueError: Duplicate
  entry name: SpeasyAmdaSettings` → the graph_context_integration flakes.

Fixed (all verified by re-running the polluting combinations):
1. `loader.py::load_module` — bundled plugins now `importlib.import_module(f"SciQLop.plugins.{name}")` (idempotent); path-based spec loading kept for user plugin folders.
2. Defense in depth: orphan actions carry `is_orphan_query`/`is_orphan_delete` tags checked via `getattr` instead of `isinstance` (still matters for user-folder plugin copies).
3. `test_catalog_tscat_integration` fixture reuses the registered "My Catalogs" provider instead of creating a racing duplicate.
4. `fuzzing/test_ui_fuzzing.py` ScopeMismatch (module-scoped fixture × function-scoped qtbot) → function scope. This unmasked two real fuzzer bugs, also fixed: targetless hypothesis rules returned dicts (health-check failure), and `remove_panel` didn't `consumes()` its bundle draw so deleted panel names were re-drawn.
5. Session-teardown ERROR (blamed on the last test, e.g. `test_reopen_last_workspace_defaults_true`): `SciQLopMainWindow.closeEvent` assumed a usable asyncio loop (`asyncio.ensure_future` raised at pytest teardown where the loop never runs / was unset). Now `_usable_event_loop()` gates the async path with a synchronous plugin-close fallback. Tests: `tests/test_mainwindow_close.py`.
6. `test_provider_snippets.py` extended_metadata tests built `EasyProvider` via `__new__` without the new `_dependency_specs` (broken by VP-deps commit `bf60ef73`) — fixtures updated.
7. `test_graph_context_integration::test_inspector_tree_tooltip_renders_on_graph_row` (the long-standing flake): plot/graph display names are unique-suffixed **process-wide** ("Line", "Line2", …), so under suite ordering the panel's graph is not named 'Line'. Test now matches `graph.name` and scopes its tree search to its own panel row (the shared `PlotsModel` holds other tests' rows).
8. `zoom_panel` fuzzer rule verified raw drawn ranges against the app, but the app reorders swapped bounds, drops zero-width ranges, and center-clips spans beyond the 1-day zoom limit — the rule now normalizes its range and feeds the normalized values to model/verify.

**Fuzzer observation (not a bug, watch it):** panels removed via `main_window.remove_panel` leave their `PlotsModel` rows visible until `deleteLater` + queued cleanup is processed (~hundreds of ms with dozens of panels). Self-heals; would only matter if something iterated the model synchronously after a mass delete.

## Left open (needs decisions / upstream)

- **SciQLopPlots: implement `SciQLopItemInterface::visible()/set_visible()`** for Pixmap/Ellipse/Text/CurvedLine items (currently abstract stubs) — logged as **M9** in `SciQLopPlots/docs/backlog-2026-06-10.md`. Once done, revert `_PlotItem.visible` to delegate.
- `XYPlot.plot` could *gain* product-path support for parity with `TimeSeriesPlot.plot` (feature, not fixed here).
