# Smart search: a core SciQLop component with a multi-domain registry

Date: 2026-07-17
Status: Draft, approved conversationally this session — ready for planning.

## Context

`SciQLopPlots/docs/superpowers/specs/2026-07-16-smart-search-relocation-design.md`
(companion repo) established the direction: SciQLopPlots keeps only the
generic C++ primitive (`ExternalScoreOverlay`, the three hook methods on
`ProductsTreeFilterModel`/`ProductsFlatFilterModel`, and
`ProductsFlatFilterModel::corpus_snapshot()`), and everything else — the four
Python modules implementing the original single-domain `SmartSearchController`
— relocates into SciQLop as a new core component, generalized into a
multi-domain registry.

Investigation at the start of this session found the relocation isn't a pure
code move:

- **No SciQLop UI currently uses any of this.** The only existing product
  search surface, `components/plotting/ui/product_search_overlay.py`, talks
  to `ProductsFlatFilterModel` directly with plain fuzzy matching — it never
  calls `SmartSearchController` or touches `ProductsTreeFilterModel`. The
  SciQLopPlots-side feature shipped fully tested but never wired into the
  app.
- **`ProductsModel` is a shared singleton**, populated by `speasy_provider`,
  virtual products, and any other plugin via `ProductsModel.instance().add_node(...)`
  — not speasy-specific. `components/products/` already exists as the core,
  always-loaded component for "the app's products" (today just a
  context-menu stub), making it the natural owner of a Products search
  adapter.
- **SciQLop plugins don't hot-reload at runtime today** — `settings.plugins[name].enabled`
  is only read once, at `load_all()` startup. This resolves one of the
  original doc's open questions for free: there's no live "domain unloads
  while the app is running" event to design around yet.
- Two existing subprocess patterns in SciQLop were considered and rejected as
  a fit for indexing: `components/plotting/backend/remote/`'s `RemoteWorker`
  is a persistent *keep-alive channel* to a live data source (wrong
  category — indexing is an on-demand task, not a channel that stays up);
  `components/jobs/`'s `JobsBackend` is shaped for detached, disk-tracked
  shell commands that survive the app closing (right conceptual home, wrong
  current implementation — it only knows text commands and log-tail
  status, not structured payloads).

## Decisions reached this session

1. **Build the multi-domain registry now**, not a single hardcoded Products
   consumer — even though there is exactly one real consumer today. A second
   domain is not being designed here (see Non-goals), but the registry shape
   is worth getting right up front since it's the one part of this move that
   isn't a pure relocation.
2. **This design also covers wiring smart search into real SciQLop UI**
   (`product_search_overlay.py`), not just moving the component — otherwise
   the feature ships dark a second time.
3. **A "domain" is a topic/corpus, not a plugin.** `SearchDomain` describes
   *what's searchable* (e.g. "products"); any number of independent client
   modules (the search overlay today, a future tree view, command palette,
   agent tools) can query the same registered domain. Domain registration is
   decoupled from domain consumption.
4. **Domain enablement is the domain owner's decision, not one global
   feature flag.** The registry's global enable/model setting is a *resource
   gate* — is the shared embedding model loaded at all — not a per-domain
   opt-in switch. Whether a given domain's corpus gets semantic scoring is
   up to whoever registers that domain.
5. **Queries are independent, per-caller request/response** — `query(domain, text)`
   returns scores directly to whoever called it, rather than the old
   broadcast-to-a-fixed-target-list shape. Two different modules can query
   the same domain with different text at the same time without cross-talk.
6. **One shared embedding model for all domains.** The model is a real
   resource (download + memory footprint); no domain needs a different one
   today, so there's exactly one app-wide model choice in Settings.
7. **Only indexing is offloaded to a subprocess. Querying stays in-process.**
   Embedding one query string is cheap; bulk-embedding a whole corpus is the
   part worth keeping off the main process. This also means the main process
   still needs `fastembed` loaded (for query embedding) — consistent with it
   being a mandatory dependency, not something process-isolation lets us avoid
   importing.
8. **Indexing reuses `JobsBackend`, extended with a second job kind** —
   `submit_function(fn, args, name)` built on `concurrent.futures.ProcessPoolExecutor`
   (forced `spawn` context), returning a `job_id`; `job_result(job_id)`
   blocks/returns/re-raises via the underlying `Future`, mirroring
   `Future.result()` semantics exactly. This is additive: today's
   `submit_job(command, name)` (detached shell command, TOML-tracked,
   survives a restart) is untouched and serves a genuinely different need
   (long user-facing batch jobs). Both share `JobsBackend`'s existing
   `_jobs` tracking and `job_added`/`job_status_changed` signals.
9. **Model download uses `fastembed`/`huggingface_hub`'s own `snapshot_download`
   caching, not a hand-rolled fetch.** Originally planned to route model-file
   downloads through `speasy.core.any_files.any_loc_open` for proxy-aware
   caching, but verified (by installing `fastembed==0.8.0` and reading
   `fastembed/common/model_management.py`) that `TextEmbedding(model_name,
   cache_dir=..., local_files_only=...)` is real and delegates to
   `huggingface_hub.snapshot_download(repo_id, cache_dir, local_files_only)`
   — which writes HF's own content-addressed snapshot layout
   (`models--<org>--<repo>/snapshots/<rev>/...`). Reimplementing that layout
   by hand via `any_loc_open` would mean faithfully reproducing an internal
   `huggingface_hub` cache format that can change across versions, for no
   real gain: the proxy-awareness `any_loc_open` was chasing is already
   covered, since `huggingface_hub` (via `requests`) honors standard
   `HTTP_PROXY`/`HTTPS_PROXY` env vars, and `sciqlop_app.py` already calls
   `apply_qt_application_proxy()` before anything else runs. So `model_fetch.py`
   is a thin wrapper: `TextEmbedding(model_name, cache_dir=<our dir>)` once
   (the download job), then `TextEmbedding(model_name, cache_dir=<same dir>,
   local_files_only=True)` for every subsequent load (query embedding,
   indexing subprocess).
10. **The Products domain adapter lives in `components/products/`**, not
    `speasy_provider` — `ProductsModel` is core infrastructure fed by
    multiple sources, not speasy-specific.
11. **Public API is a module-level facade** (`from SciQLop.components.smart_search import register_domain, query, ...`),
    matching existing SciQLop conventions (`theming.register_icon/get_icon`,
    `core.models.products`) rather than a fetched singleton object.
12. **Reindex debouncing is built in from the start**, given each reindex now
    spawns a real subprocess + model load, not just a thread: `notify_changed(domain)`
    coalesces bursts (~200ms) before submitting a job. If a domain's corpus
    changes again while its reindex job is still running, the in-flight job
    is left to finish (not cancelled) and exactly one more reindex is queued
    immediately after with the latest snapshot.

## Target architecture

### Repo boundary (unchanged from the companion SciQLopPlots doc)

| Stays in SciQLopPlots (C++, no new deps) | Moves to SciQLop (Python, `fastembed` mandatory) |
|---|---|
| `ExternalScoreOverlay` (include/src) | All four Python modules, generalized per this doc |
| `ProductsTreeFilterModel`/`ProductsFlatFilterModel` hook methods | New `components/smart_search/` component |
| `ProductsFlatFilterModel::corpus_snapshot()` | New Products domain adapter in `components/products/` |
| | Extension to `components/jobs/backend/jobs_backend.py` |
| | `components/smart_search/settings.py` (Settings UI) |
| | Wiring into `components/plotting/ui/product_search_overlay.py` |

### Module layout

```
components/smart_search/
├── __init__.py          # public facade: register_domain, unregister_domain,
│                         #   notify_changed, query, is_available, is_enabled,
│                         #   set_enabled, available_models, get_model, set_model
├── domain.py             # SearchDomain protocol, NodeSnapshot (moved from
│                         #   smart_search_method.py)
├── registry.py           # SmartSearchRegistry (internal singleton) — owns
│                         #   one vector table per domain, the shared
│                         #   embedding model, reindex debouncing
├── index_worker.py        # run(snapshot, model_name) -> dict[str, np.ndarray],
│                         #   the function submitted via JobsBackend
├── semantic_method.py     # SemanticSearchMethod (fastembed), moved from
│                         #   smart_search_semantic.py
├── model_fetch.py         # thin wrapper around TextEmbedding's own
│                         #   cache_dir/local_files_only caching
└── settings.py            # SmartSearchSettings ConfigEntry
```

### The `SearchDomain` contract

```python
class SearchDomain(Protocol):
    name: str
    def snapshot(self) -> Iterable[NodeSnapshot]: ...   # full corpus, called on reindex
```

No `push_scores`/target list — since queries are independent per-caller
request/response, a domain only describes *what's in it*. Consumers apply
returned scores to their own view themselves (e.g.
`filter_model.set_external_scores(...)`).

### Public API

```python
def register_domain(domain: SearchDomain) -> None: ...
def unregister_domain(name: str) -> None: ...
def notify_changed(domain_name: str) -> None: ...
def query(domain_name: str, text: str) -> dict[str, float]: ...   # blocks the
                                                                    # calling
                                                                    # thread —
                                                                    # never
                                                                    # call from
                                                                    # the Qt
                                                                    # main thread
def is_available() -> bool: ...
def is_enabled() -> bool: ...                # resource gate: is the shared
                                              # model loaded at all
def set_enabled(enabled: bool, on_ready=None, on_error=None) -> None: ...
def available_models() -> list[str]: ...
def get_model() -> str: ...
def set_model(name: str) -> None: ...
```

Per-domain opt-in lives on the domain object itself, not the registry. If the
resource gate (`is_enabled()`) is off, `query()` returns `{}` regardless of
domain.

### Indexing: `JobsBackend` extension

```python
# components/jobs/backend/jobs_backend.py additions
def submit_function(self, fn: Callable, args: tuple, name: str) -> str:
    """fn must be a real importable module-level function (spawn re-imports
    it in the child) — not a closure. Not TOML-persisted/reconciled across a
    restart, unlike submit_job: if SciQLop closes mid-index there's nothing
    to resume, which is the desired behavior here."""

def job_result(self, job_id: str) -> Any:
    """Future.result() under the hood: blocks if not done, returns fn's
    return value, re-raises fn's exception if it crashed. Safe to call
    repeatedly once done."""
```

Built on `concurrent.futures.ProcessPoolExecutor(mp_context=multiprocessing.get_context("spawn"))`
— forcing `spawn` (not Linux's default `fork`, unsafe in a multi-threaded Qt
process, and what Windows/macOS require anyway) gives one code path on every
platform. `Future.add_done_callback` fires on an executor management thread;
the callback relays into `job_status_changed.emit(job_id, status)`, which Qt
auto-queues onto the main thread since `JobsBackend` lives there. `job_status(job_id)`
keeps its existing cheap, payload-free shape for both job kinds; the
(possibly large) result is fetched separately via `job_result()`, only when
actually wanted. `Future.cancel()` only works pre-start, which is fine — an
in-flight reindex job is deliberately left to finish rather than killed (see
decision 12).

Both indexing (`ProductsDomain.snapshot()` → `submit_function(index_worker.run, ...)`)
and the existing shell-command jobs share `JobsBackend`'s tracking/signals —
one unified job list.

### Query: stays in-process

`query(domain, text)` embeds the single query string with the shared model —
loaded lazily in the main process on first use, since a single short string
is cheap enough not to warrant a subprocess — and compares it against that
domain's current in-memory vector table (whatever the last completed
indexing job produced) via plain numpy. Runs on a background thread, off the
Qt main thread, returns synchronously to the caller.

### Model download

`components/smart_search/model_fetch.py` is a thin wrapper around
`fastembed.TextEmbedding`'s own caching rather than a hand-rolled fetch
(verified against the real `fastembed==0.8.0` API — see decision 9):

```python
def download_model(model_name: str, cache_dir: Path) -> None:
    """Runs inside a JobsBackend submit_function job. Network-capable;
    huggingface_hub honors HTTP_PROXY/HTTPS_PROXY, already set up by
    apply_qt_application_proxy() at startup."""
    from fastembed import TextEmbedding
    TextEmbedding(model_name=model_name, cache_dir=str(cache_dir))

def load_model(model_name: str, cache_dir: Path):
    """Called both from the main process (query embedding) and inside the
    index_worker subprocess (corpus embedding). Never touches the network —
    raises if download_model() hasn't populated cache_dir yet."""
    from fastembed import TextEmbedding
    return TextEmbedding(model_name=model_name, cache_dir=str(cache_dir), local_files_only=True)
```

### Products domain adapter & registration

```python
# components/products/smart_search_domain.py
class ProductsDomain:
    name = "products"

    def __init__(self):
        self._corpus_source = ProductsFlatFilterModel(ProductsModel.instance())
        ProductsModel.instance().rowsInserted.connect(self._on_changed)
        ProductsModel.instance().rowsRemoved.connect(self._on_changed)
        ProductsModel.instance().modelReset.connect(self._on_changed)

    def snapshot(self) -> Iterable[NodeSnapshot]:
        return [NodeSnapshot(k, v) for k, v in self._corpus_source.corpus_snapshot().items()]

    def _on_changed(self, *args) -> None:
        from SciQLop.components.smart_search import notify_changed
        notify_changed(self.name)
```

Registered explicitly in `sciqlop_app.py:start_sciqlop()`, alongside the
other core-component setup calls already there (`apply_qt_application_proxy()`,
`flush_deferred_icons()`, `register_builtin_commands()`):

```python
from SciQLop.components.products import register_smart_search_domain
register_smart_search_domain()
```

### Settings

```python
# components/smart_search/settings.py
class SmartSearchSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Smart Search"
    enabled: bool = False
    model: Literal["BAAI/bge-small-en-v1.5", "sentence-transformers/all-MiniLM-L6-v2"] = "BAAI/bge-small-en-v1.5"
```

`model` gets a combo box for free (the settings delegate registry already
handles `Literal` generically). `enabled` toggling calls `smart_search.set_enabled(...)`,
which submits a "Loading smart-search model..." job through the same
`JobsBackend.submit_function` mechanism as reindexing — one async-work
pattern reused for both, rather than a second bespoke one for settings.

### UI wiring — `product_search_overlay.py`

In `_run_query()`, alongside the existing `self._filter_model.set_query(...)`:
if `smart_search.is_enabled()`, dispatch `smart_search.query("products", text)`
on a background thread, and on completion call
`self._filter_model.set_external_scores(scores)` — the hook already exists on
`ProductsFlatFilterModel` today via the C++ primitive, just unused until now.

### SciQLopPlots side

Delete `smart_search_method.py`, `smart_search_controller.py`,
`smart_search_semantic.py`, `smart_search.py`, and the `fastembed` optional
extra there. `ExternalScoreOverlay` + the three filter-model hook methods +
`corpus_snapshot()` are unchanged — already domain-agnostic.

## Testing strategy

- `SearchDomain`/registry unit tests: register/unregister, `notify_changed`
  debounce/coalescing, query independence across concurrent callers (no
  cross-talk between two simultaneous `query()` calls on the same domain).
- `JobsBackend.submit_function`/`job_result`: success, exception
  re-raising, `job_status_changed` firing on the main thread, non-persistence
  across a simulated restart.
- `ProductsDomain`: `snapshot()` correctness against a populated
  `ProductsModel`, `notify_changed` firing on `rowsInserted`/`rowsRemoved`/`modelReset`.
- `product_search_overlay.py`: scores applied via `set_external_scores`
  without blocking the GUI thread; behaves identically to today when smart
  search is disabled/unavailable.
- Model fetch: `download_model` populates `cache_dir`; `load_model` with
  `local_files_only=True` succeeds afterward and never touches the network.

## Non-goals (explicitly out of scope for this doc)

- A concrete second domain (e.g. a markdown-docs help search) — this doc
  prepares the seam; building one is separate future work.
- Domain lifecycle on plugin unload — moot today since SciQLop plugins don't
  hot-unload at runtime (only via a restart), per this session's
  investigation of `components/plugins/backend/loader/loader.py`.
- Per-domain model override — one shared app-wide model is sufficient until
  a domain actually needs a different one.
