# Smart search: Model2Vec engine swap + incremental disk-cached indexing

Date: 2026-07-19
Status: Draft, approved conversationally this session — ready for planning.

## Context

The smart-search component shipped 2026-07-17
(`docs/superpowers/specs/2026-07-17-smart-search-component-design.md`,
`docs/superpowers/plans/2026-07-17-smart-search-component.md`) and was
verified working end-to-end against the real SciQLopPlots 0.30.0 build the
same day. Once exercised against a real products catalog (tens of thousands
of products), reindexing took "several minutes" — unacceptable, especially
for the very first index.

### Root cause investigation (this session, via systematic-debugging)

Every reindex re-embeds the ENTIRE products corpus from scratch —
`index_worker.run` has no notion of "this text was already embedded last
time," so `SmartSearchRegistry._trigger_reindex` pays the full embedding
cost every single reindex cycle, regardless of how small the actual delta
is.

Empirically measured on the reporting user's real hardware (AMD Ryzen 7 PRO
7840U, 16 cores, full AVX-512 including VNNI) with corpus-like synthetic
data (short mission/instrument/parameter strings, matching real SciQLop
product-path shape):

| Configuration | Throughput | 20k-item cost | Notes |
|---|---|---|---|
| `fastembed`/`bge-small-en-v1.5`, default settings | ~285 texts/sec | ~70s | today's shipped config |
| ...+ `parallel=16` | ~450-590 texts/sec | ~35-45s | best tuning found; noisy across runs |
| ...+ `batch_size=512` | ~585 texts/sec | ~34s | no further gain past this; `batch_size=1024` is *worse* (517/s) |
| `fastembed`/`all-MiniLM-L6-v2` (the other bundled model) | ~100-109 texts/sec | ~185-200s | tested as a candidate for "switch to a faster model" — turned out *slower*, ruled out |
| `model2vec`/`potion-base-8M` | **~32,000 texts/sec** | **~0.6s** | see below |
| `model2vec`/`potion-base-32M` | ~20,600 texts/sec | ~1.0s | larger (512-dim vs 256-dim), likely better quality, still dramatically faster than fastembed |

At the shipped throughput, a realistic SciQLop catalog (tens of thousands of
products across AMDA/CDAWeb/SSCWeb/etc. — confirmed as the reporting user's
actual scale) genuinely takes multiple minutes *per reindex*. This is a real
scale limitation, not broken code — nothing in the original design or its
automated tests exercised a corpus anywhere near this size (all tests use
1-2 fake nodes).

### Approaches investigated and ruled out

- **AVX-512/VNNI quantization of the existing model** (via Hugging Face
  Optimum's `export_dynamic_quantized_onnx_model(...,
  quantization_config="avx512_vnni")`): a genuine, documented technique with
  real speedups (3-6x on VNNI hardware per published benchmarks), but (a)
  tops out far short of what's needed (~1000-1800 texts/sec at best, still
  minutes for very large corpora), (b) is not universally a win — at least
  one reported case of INT8 quantization being *slower* than FP32 on ONNX
  Runtime CPU depending on op support, meaning it would need its own
  empirical verification before trusting it, (c) adds a build/tooling
  dependency (Optimum) for a partial win. Ruled out once Model2Vec's much
  larger margin made it moot.
- **AMD NPU (XDNA) acceleration**: the kernel driver is present on this
  machine (`amdxdna` loaded, `/dev/accel/accel0` exists), but
  `onnxruntime`'s only available execution providers are
  `CPUExecutionProvider`/`AzureExecutionProvider` — no NPU-capable provider
  is installed, and AMD's Vitis AI / Ryzen AI software stack for actually
  targeting the NPU is not a simple pip dependency on Linux; that stack is
  still immature there. Ruled out as a large, platform-risky effort for an
  uncertain gain, especially given Model2Vec makes it unnecessary.
- **Chunked/progressive indexing** (split a large reindex into sequential
  jobs, merge results into the live index as each chunk lands, so partial
  results become searchable within seconds instead of waiting for the whole
  corpus): a real, buildable answer to "the first index feels unacceptably
  slow" that would have added meaningful complexity to `registry.py` (chunk
  queue, sequential submission, incremental merge, careful interaction with
  the existing debounce/dirty-flag retrigger state machine) while
  respecting the earlier explicit "indexing is a one-shot job, not a
  persistent channel" decision. Superseded by Model2Vec: a full reindex is
  now fast enough (well under 5 seconds even scaled to 100k+ items) that
  progressive delivery isn't needed to make the experience acceptable.

## Decisions reached this session

1. **Switch the embedding engine from `fastembed` to `model2vec`**
   (`minishlab/potion-base-8M`, MIT licensed — GPL-compatible — whose only
   real dependency is `numpy`, already a mandatory SciQLop dependency, so
   this is actually a *lighter* footprint than the
   `fastembed`/`onnxruntime`/`huggingface_hub` stack it replaces). Real
   trade-off acknowledged: `potion-base-8M` is a static (non-transformer)
   distillation of `bge-base-en-v1.5` (a different, larger parent than the
   shipped `bge-small`), scoring ~92% of `all-MiniLM-L6-v2` on general MTEB
   benchmarks — a genuine semantic-quality cost, not free, and not
   perfectly predictive of how well it matches short technical labels
   (SciQLop's actual use case), which general retrieval benchmarks don't
   directly measure. Accepted as the right trade for a ~60-100x throughput
   gain that eliminates the underlying problem rather than mitigating it.
2. **Keep both `JobsBackend.submit_function` subprocess offloading and
   disk-persisted incremental caching**, even though Model2Vec's raw speed
   alone would likely make the problem tolerable without either. Deliberate
   choice: keeps the existing, already-reviewed subprocess-offload
   architecture exercised and provides a resilience margin if a future
   model/corpus-size combination reintroduces slowness, rather than ripping
   out working infrastructure to chase a simplicity gain that isn't
   currently needed.
3. **Incremental caching lives entirely inside `index_worker.run`**
   (not a registry-side diff): `_trigger_reindex` keeps submitting the
   domain's full current snapshot on every reindex (cheap — it's just
   text). The job function loads an on-disk cache, keeps entries whose text
   hasn't changed, computes embeddings only for new/changed text, drops
   entries no longer present in the current snapshot (removals handled as a
   side effect of the merge, no special-case code), persists the merged
   cache back to disk, and returns the same `dict[path_key, vector]` shape
   it already returns today. `registry.py`'s `_handle_reindex_job` requires
   **zero changes**.
4. **Cache invalidation is whole-file, keyed on model name**: if the
   persisted cache's stored `model_name` doesn't match the currently
   configured model, the entire cache is discarded (nothing reused) rather
   than maintaining one cache per model ever used. Simpler, and consistent
   with the already-accepted "no live model swap without restart"
   limitation.
5. **Model download switches from `fastembed`'s own downloader to
   `huggingface_hub.snapshot_download` directly**, since
   `model2vec.StaticModel.from_pretrained` doesn't expose a `cache_dir`
   parameter the way `fastembed.TextEmbedding` did. Verified empirically:
   `snapshot_download(repo_id, cache_dir=...)` followed by
   `StaticModel.from_pretrained(<local snapshot path>, force_download=False)`
   loads with zero network access (confirmed via `HF_HUB_OFFLINE=1`).

## Target architecture

### Module changes

```
components/smart_search/model_fetch.py    MODIFY: download_model/load_model → model2vec + huggingface_hub.snapshot_download
components/smart_search/index_worker.py    MODIFY: model.encode() instead of model.embed(); add cache load/diff/merge/persist
components/smart_search/registry.py        MODIFY: query() uses model.encode([text])[0]; _trigger_reindex passes an index_cache_path; constructor gains index_cache_dir
components/smart_search/settings.py        MODIFY: AVAILABLE_MODELS → model2vec model names
components/smart_search/__init__.py        MODIFY: facade computes and passes index_cache_dir alongside cache_dir when constructing the registry
pyproject.toml                              MODIFY: drop fastembed, add model2vec
```

Everything else (`domain.py`, `components/products/smart_search_domain.py`,
`product_search_overlay.py`, `JobsBackend`) is untouched.

### `model_fetch.py`

```python
"""Wraps model2vec's StaticModel, fetching model files via
huggingface_hub.snapshot_download (model2vec's own from_pretrained has no
cache_dir parameter) and loading from the resulting local path with
force_download=False, verified to touch no network."""


def download_model(model_name: str, cache_dir: str) -> None:
    """Runs inside a JobsBackend submit_function job. Network-capable."""
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=model_name, cache_dir=cache_dir)


def load_model(model_name: str, cache_dir: str):
    """Never touches the network -- raises if download_model() hasn't
    populated cache_dir yet. Called both in the main process (query
    embedding) and inside the index_worker subprocess (corpus embedding).
    local_files_only=True on the snapshot_download call is what actually
    enforces "no network" -- resolving the local path still goes through
    snapshot_download, just told not to reach out."""
    from huggingface_hub import snapshot_download
    from model2vec import StaticModel
    local_path = snapshot_download(repo_id=model_name, cache_dir=cache_dir, local_files_only=True)
    return StaticModel.from_pretrained(local_path, force_download=False)
```

### `index_worker.run` — cache-aware incremental embedding

```python
"""The reindex job's entry point -- runs inside a spawned subprocess via
JobsBackend.submit_function. Must stay a real module-level function: the
spawn context re-imports it by dotted path in the child."""
import pickle
from pathlib import Path
from typing import Sequence

from SciQLop.components.smart_search import model_fetch
from SciQLop.components.smart_search.domain import NodeSnapshot


def _load_cache(index_cache_path: str, model_name: str) -> dict:
    path = Path(index_cache_path)
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as f:
            cache = pickle.load(f)
    except Exception:
        return {}
    if cache.get("model_name") != model_name:
        return {}
    return cache.get("entries", {})


def _save_cache(index_cache_path: str, model_name: str, entries: dict) -> None:
    path = Path(index_cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump({"model_name": model_name, "entries": entries}, f)


def run(snapshot: Sequence[NodeSnapshot], model_name: str, cache_dir: str, index_cache_path: str) -> dict:
    current = {n.path_key: n.raw_text for n in snapshot}
    if not current:
        _save_cache(index_cache_path, model_name, {})
        return {}

    cached = _load_cache(index_cache_path, model_name)
    to_embed = [
        NodeSnapshot(path_key, raw_text)
        for path_key, raw_text in current.items()
        if path_key not in cached or cached[path_key][0] != raw_text
    ]

    newly_embedded = {}
    if to_embed:
        model = model_fetch.load_model(model_name, cache_dir)
        vectors = model.encode([n.raw_text for n in to_embed])
        newly_embedded = {n.path_key: (n.raw_text, vectors[i]) for i, n in enumerate(to_embed)}

    merged = {**{k: v for k, v in cached.items() if k in current}, **newly_embedded}
    _save_cache(index_cache_path, model_name, merged)
    return {path_key: vector for path_key, (raw_text, vector) in merged.items()}
```

Correctness notes:
- `merged`'s dict-unpacking order (`{**filtered_cached, **newly_embedded}`)
  means a changed entry's fresh embedding always wins over its stale cached
  counterpart for the same `path_key` — both dicts can legitimately contain
  the same key for a changed entry, and later-wins semantics resolve it
  correctly.
- Removals happen for free: the `if k in current` filter drops any cached
  entry whose `path_key` is no longer in the live snapshot; nothing carries
  it into `merged`.
- The model is only loaded (`model_fetch.load_model`, ~1.2s per earlier
  benchmark) when there's actually something new to embed — a
  fully-cached, no-op reindex (e.g. only removals) skips it entirely.

### `registry.py` changes

Constructor gains one parameter, `index_cache_dir: str`, stored as
`self._index_cache_dir`. `_trigger_reindex` derives the domain's cache
path (`f"{self._index_cache_dir}/{domain_name}.pkl"`) and passes it as the
job's fourth argument:

```python
        job_id = self._jobs_backend.submit_function(
            index_worker.run,
            (snapshot, self._model_name, self._cache_dir, f"{self._index_cache_dir}/{domain_name}.pkl"),
            f"Smart search: reindex {domain_name}")
```

`query()` changes only its embedding call:

```python
    def query(self, domain_name: str, text: str) -> dict:
        if not self._enabled or self._query_model is None:
            return {}
        state = self._domains.get(domain_name)
        if state is None or state.matrix is None:
            return {}
        matrix, path_keys = state.matrix, state.path_keys
        query_vec = self._query_model.encode([text])[0]
        norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec)
        norms[norms == 0] = 1.0
        cosine = (matrix @ query_vec) / norms
        return {path_key: float(max(0.0, sim)) * 100.0
                for path_key, sim in zip(path_keys, cosine)}
```

(This also carries forward the `state.matrix`/`state.path_keys` local-bind
fix already applied at the previous final review — no separate change
needed, just preserving it correctly through this edit.)

### Facade (`__init__.py`) — one new helper

```python
def _index_cache_dir() -> str:
    from platformdirs import user_cache_dir
    return user_cache_dir(appname="sciqlop", appauthor="LPP", ensure_exists=True) + "/smart_search_index"
```

`_get_registry()` passes both `_cache_dir()` (model files) and
`_index_cache_dir()` (embedding cache) into `SmartSearchRegistry(...)`.

### Settings & dependency

```python
AVAILABLE_MODELS = ("minishlab/potion-base-8M", "minishlab/potion-base-32M")
```

`pyproject.toml`: remove `"fastembed"`, add `"model2vec"`.

## Testing strategy

- `model_fetch.py`: mock `huggingface_hub.snapshot_download`/
  `model2vec.StaticModel.from_pretrained` (patching at their source module,
  matching the pattern already established when the earlier
  fastembed-eager-import fix was made), assert correct
  `cache_dir`/`local_files_only`/`force_download` argument passing.
- `index_worker.py`: new tests specifically for the cache path — (a) empty
  cache: everything gets embedded, cache written; (b) fully-cached, no
  changes: nothing gets embedded (mock the model, assert `encode` is never
  called), cached vectors returned unchanged; (c) partial change: only
  changed/new entries passed to `encode`, unchanged entries carried through
  from cache untouched; (d) removal: a `path_key` present in the old cache
  but absent from the current snapshot doesn't appear in the result; (e)
  model mismatch: a cache with a different `model_name` is discarded
  wholesale, full re-embed happens.
- `registry.py`: existing `query()` tests updated for the `encode([text])[0]`
  call shape (mock target changes from `.embed` to `.encode`), same
  assertions otherwise; `_trigger_reindex` tests updated to assert the
  fourth `index_cache_path` argument is passed to `submit_function`.
- `settings.py`: `AVAILABLE_MODELS`/default-model tests updated to the new
  model names.
- `__init__.py` (facade): `_get_registry()` test updated to assert
  `index_cache_dir` is passed alongside `cache_dir`.

## Non-goals (explicitly ruled out this session, not to be re-litigated without new evidence)

- AVX-512/VNNI INT8 quantization of an ONNX transformer model — real
  technique, real hardware match, but a small fraction of Model2Vec's
  margin and not universally a speed win.
- AMD NPU (XDNA) acceleration — hardware/driver present, but no mature,
  simple software path on Linux today.
- Chunked/progressive reindexing — solves a problem that no longer exists
  at Model2Vec's throughput.
- Per-domain or per-model cache files (multiple caches coexisting) — YAGNI
  given only one model is active at a time today.
