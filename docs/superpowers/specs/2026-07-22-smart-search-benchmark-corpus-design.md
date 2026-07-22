# Smart search benchmark corpus — design

**Date**: 2026-07-22
**Status**: approved, not yet planned/implemented

## Problem

Every real ranking bug found in smart search so far (the MMS/REACH score-merge
tie, the BM25F-favors-REACH reality check, the MMS1-Search-Coil vocabulary
gap) was found the same way: the user types a query into the running app,
notices a bad result, screenshots it, and someone reverse-engineers the cause
with one-off scripts against the real corpus cache. This only catches
problems someone happens to type and notice, and gives no way to tell whether
a ranking change helped or hurt without repeating the whole cycle.

This design replaces that cycle with a growing, repeatable corpus of
`(query, expected result)` cases, checked automatically against the real
product corpus.

## Decisions (from brainstorming)

- **Real corpus, not a synthetic fixture.** Every case is checked against the
  actual `~/.cache/sciqlop/smart_search_index/products.pkl` cache (77k+ real
  entries as of 2026-07-22) — the same data every real bug so far was
  diagnosed against. No hand-built corpus to keep in sync with reality.
- **Runs as a pytest suite, skipped where the real cache doesn't exist.**
  Since the cache lives in a per-machine cache directory (never checked into
  git, never built in CI — CI never runs the app against a live speasy
  inventory), the suite is gated with `pytest.mark.skipif`. In practice this
  means: always skipped in CI, always runs on a dev machine that has used
  smart search for real. This *is* "disabling it in CI for a good reason" —
  the reason is structural (no real corpus there), not a manual toggle.
- **Expected result = one or more path_key prefixes, ANY of which must
  appear in the top N results.** Matches how the corpus is actually
  structured (mission/instrument hierarchy baked into `path_key`) and how
  bugs are actually described ("MMS1 trajectory should surface MMS1's MEC
  entries"). Not an exact-leaf match (too brittle as ranking evolves) and not
  graded relevance (too much authoring effort per case for the value it adds
  here).
- **Top-N has a suite-wide default, overridable per case.** Default is 10.
- **Query cases grow organically.** Seeded now with the 3 known real queries
  plus a handful more found by browsing the real cache; extended whenever a
  live query produces a bad result, the same trigger as today's bug reports,
  except now the case is captured instead of thrown away.
- **A standalone report CLI, separate from pytest pass/fail.** Iterating on
  ranking needs to see *how close* a failing case is (best rank found, not
  just red/green) to judge whether a change is helping before it fully
  passes. Pytest stays a clean binary gate; the report tool is what you run
  while tuning.

## Engine boundary: extract `score_query()` as a pure function

`registry.py`'s `SmartSearchRegistry.query()` and `_semantic_scores()`
currently only run as methods on a live, fully-wired `SmartSearchRegistry`
(needs a `QObject`, a jobs backend, Qt timers, an enabled/reindexed domain).
The benchmark needs to run this exact scoring logic against data loaded
straight from the pickle cache, with no Qt/job-backend machinery.

Fix: pull the scoring body out into a module-level pure function in
`registry.py`:

```python
def score_query(
    text: str,
    path_keys: list[str],
    matrix: np.ndarray,
    bm25: Optional[bm25_index.BM25Index],
    query_model,
    bm25_confident_frac: float = 0.5,
    confident_band_max: float = 100.0,
    fallback_band_max: float = 50.0,
) -> dict[str, float]:
    ...  # exact logic currently in query()/_semantic_scores()
```

`SmartSearchRegistry.query()` becomes a thin wrapper that pulls
`state.path_keys` / `state.matrix` / `state.bm25` / `self._query_model` and
delegates. `_semantic_scores` folds into `score_query` (or stays a private
free function it calls — implementer's call, no behavior difference).

This is the one piece of production code this design touches, and it's a
refactor, not a behavior change: `SmartSearchRegistry.query()`'s external
contract is unchanged. It matters because the benchmark then exercises the
**actual production scoring path**, not a reimplementation that could
silently drift from what the app really does.

## Data model

```python
class BenchmarkCase(BaseModel):
    query: str
    expected_prefixes: list[str]   # path_key prefixes; ANY hit in top_n = pass
    top_n: int | None = None       # None -> DEFAULT_TOP_N
```

Example (from the known "MMS1 Search Coil" bug):

```python
BenchmarkCase(
    query="MMS1 Search Coil",
    expected_prefixes=["root speasy cda MMS MMS1 SCM"],
)
```

## Real-corpus harness

```python
@dataclass(frozen=True)
class RealCorpus:
    path_keys: list[str]
    matrix: np.ndarray
    bm25: bm25_index.BM25Index
    query_model: object  # model2vec.StaticModel

def load_real_corpus() -> RealCorpus:
    ...
```

`load_real_corpus()`:
1. Reads `{_index_cache_dir()}/products.pkl` (reusing
   `components.smart_search._index_cache_dir()` rather than hardcoding the
   path, so it can't drift from the real app's own cache location).
2. Rebuilds a `BM25Index` from the cached `raw_text` values via
   `bm25_index.build([NodeSnapshot(k, v[0]) for k, v in entries.items()])` —
   deterministic, so it's guaranteed identical to what `index_worker.run`
   would produce for that exact snapshot.
3. Stacks the cached vectors into `matrix`, in the same iteration order used
   for `path_keys`.
4. Loads the model2vec model via `model_fetch.load_model(cache["model_name"],
   cache_dir=_cache_dir())` — the model name comes from the cache itself
   (not from current `SmartSearchSettings`), so a benchmark run stays
   internally consistent even if the configured model has since changed.
   `local_files_only`, no network — the model must already be downloaded,
   since it was necessarily used to build this same cache.

```python
@dataclass(frozen=True)
class EvaluationResult:
    case: BenchmarkCase
    passed: bool
    best_rank: int | None   # None = expected prefix never appears anywhere
    total_candidates: int

def evaluate(case: BenchmarkCase, corpus: RealCorpus) -> EvaluationResult:
    ...
```

`evaluate()` calls `score_query()`, sorts descending, and:
- `passed`: any of the top-N path_keys starts with any `expected_prefixes` entry.
- `best_rank`: the 1-indexed rank of the *first* matching path_key across the
  **entire** ranked list (not just top-N) — lets the report distinguish
  "ranked #47, needed top 10" (a ranking problem) from "not found anywhere"
  (a vocabulary-gap problem, the class of bug the ancestor-description fix
  addressed) even when both currently fail.

## Pytest suite

`tests/test_smart_search_benchmark.py`:

```python
CACHE_PATH = Path(_index_cache_dir()) / "products.pkl"
pytestmark = pytest.mark.skipif(
    not CACHE_PATH.exists(),
    reason="needs the real product corpus cache; not available in CI")

@pytest.fixture(scope="module")
def real_corpus():
    return load_real_corpus()

@pytest.mark.parametrize("case", CASES, ids=[c.query for c in CASES])
def test_benchmark_case(case, real_corpus):
    result = evaluate(case, real_corpus)
    assert result.passed, (
        f"best match at rank {result.best_rank} "
        f"(needed top {case.top_n or DEFAULT_TOP_N})")
```

## Report CLI

`tests/smart_search_benchmark/report.py`, runnable via
`uv run python -m tests.smart_search_benchmark.report`:

- Loads the real corpus once, evaluates every case in `CASES`.
- Prints a table: query, PASS/FAIL, best rank, total candidates, which
  prefix matched (if any).
- Sorted worst-first (failures, then passes ordered by how close their best
  rank is to their threshold) so the least-healthy cases are visible without
  scrolling.
- If the cache doesn't exist, prints a clear one-line message and exits
  non-zero instead of stack-tracing.

## File layout

```
tests/
  smart_search_benchmark/
    __init__.py
    cases.py       # BenchmarkCase, DEFAULT_TOP_N, CASES (data only)
    harness.py      # RealCorpus, load_real_corpus, EvaluationResult, evaluate
    report.py        # CLI entry point (__main__)
  test_smart_search_benchmark.py   # pytest suite
```

## Initial seed cases

- `"MMS spacecraft 1 magnetic field"` → `root speasy cda MMS MMS1 FGM` (the
  still-open query-understanding gap — expected to keep failing until that's
  addressed; kept in the corpus specifically so a future fix is provable)
- `"MMS1 spacecraft magnetic field"` → `root speasy cda MMS MMS1 FGM`
  (contrast case — same intent, currently passes)
- `"MMS1 Search Coil"` → `root speasy cda MMS MMS1 SCM`
- A handful more added by browsing the real cache for other missions and
  instruments (e.g. MMS1 trajectory/ephemeris, MMS1 electrons), to give the
  corpus spread beyond the MMS/REACH incidents that produced the first three.

## Testing this benchmark tooling itself

Per project convention (TDD for new code, not just bug fixes):
- `evaluate()`'s ranking/prefix-matching logic gets unit tests against small
  hand-built `RealCorpus`-shaped fixtures (fake path_keys/scores) — no real
  cache needed, always runs.
- The `score_query()` extraction is a refactor: a test asserting its output
  is unchanged for a fixed input (or reusing/adapting existing
  `registry.py` query tests if any exist) guards against behavior drift
  during the extraction.
- `load_real_corpus()`'s parsing logic (pickle shape → `RealCorpus`) gets a
  unit test against a small temp pickle fixture, not the real cache.
- The skip mechanism itself (`pytest.mark.skipif` on cache-path existence)
  needs no dedicated test — it's a one-line, directly-readable condition.

## Known limitations, explicitly accepted

- This benchmark cannot run in CI. It only ever protects against regressions
  on a machine that has a real corpus cache. Acceptable: it still turns
  every future investigation into a permanent, growing check instead of a
  one-off, which is the actual goal.
- `expected_prefixes` require someone to know the real path_key hierarchy
  for a given case ahead of time (found by browsing the cache once per new
  case). Not automated — deliberately, since deciding what's "correct" for
  a query is a domain judgment call, not something to infer mechanically.
- No negative assertions (e.g. "REACH must not appear in top N") — a
  positive top-N containment check already captures the practical failure
  mode (something wrong crowding out the right answer), and adding a second
  assertion axis per case was scoped out to keep case authoring cheap.
