# Smart search: BM25F primary ranking, semantic as a banded fallback

Date: 2026-07-20
Status: Draft, approved conversationally this session — ready for planning.

## Context

Live user report (screenshot): searching `"MMS1 spacecraft magnetic field"`
returned zero MMS results in the top 15 — Helios, Pioneer, Giotto, Juno,
Cassini, ICON dominated instead. This is a regression of the same class of
bug fixed 2026-07-19 (`docs/superpowers/specs/
2026-07-19-smart-search-model2vec-incremental-indexing-design.md`, commit
`5562f9fb`), on a differently-worded query.

### Root cause investigation (this session, via systematic-debugging)

Reproduced directly against the user's real, live 77k-entry index cache
(`~/.cache/sciqlop/smart_search_index/products.pkl`) — not synthetic data.
Best MMS1/FGM result ranked **#75** for the reported query.

Two compounding factors, both verified empirically, that turned out to be
one underlying defect:

1. **model2vec is a static, mean-pooled embedding** — `StaticModel.encode()`
   is a hard-coded `embeddings.mean(axis=0)` over per-token vectors, with no
   attention or query-dependent weighting (confirmed by reading the
   library source). It has no mechanism to weight a specific,
   load-bearing identifier ("MMS1") higher than generic descriptive words
   ("spacecraft", "magnetic", "field"). Any entry whose text happens to
   contain the generic words scores competitively regardless of mission.
2. **Corpus duplication amplifies it**: 32 near-identical REACH cubesat
   entries all share the same CATDESC — "Minimum magnetic field on field
   line intersecting **spacecraft**" — which literally contains both
   "spacecraft" and "magnetic field". With ~32 near-duplicates all scoring
   54-70%, they flood the top of the results by sheer redundancy.

A deeper cause, found while investigating why re-weighting model2vec's own
pooling doesn't fix this: model2vec's tokenizer fragments `"MMS1"` into
three generic WordPiece subwords (`['mm', '##s', '##1']`), none of which
individually carries "this is a specific spacecraft" meaning, while
`"spacecraft"` and `"magnetic"` stay whole tokens. There is no coherent
"MMS1" vector to weight up in the first place — this is an architectural
limitation, not a tuning problem.

### Approaches investigated and ruled out

All tested against the real 77k-entry corpus/cache, not toy examples.

- **Flat per-word path-token boost** (reward a query token if it appears
  literally in the corpus path text): made it *worse* — rewards missions
  that happen to spell out `"magnetic_field"` as a literal folder name
  (Pioneer, ISEE, Cassini) over MMS1, whose path uses the abbreviated
  instrument code `FGM` instead.
- **Leaf-level and dataset-group-level IDF-weighted path boost**: same
  failure mode — "magnetic" + "field" together (2 medium-rare words, both
  literal path segments for 3 other missions) out-scored "mms1" alone (1
  more-specific but lower-combined-IDF word).
- **Reciprocal rank fusion** (old fuzzy `SubsequenceMatcher` scorer +
  semantic, combined by rank position): still broken — lets an entry that's
  "good enough on both signals" (REACH) beat one that's "excellent on one,
  mediocre on the other" (the true match).
- **Weighted score blend** (normalized BM25 + semantic, various weights up
  to 85% BM25): REACH still wins, because its semantic score alone is
  enough to tip a near-tied BM25 score.
- **Reranking only BM25's own top-K by semantic score**: same failure the
  moment K is wide enough to matter (≥20) — REACH is already inside BM25's
  own near-tie band for descriptive queries, so any semantic-based
  tie-break inside that band favors it.
- **Larger model2vec variant** (`potion-base-32M`, 4x params): identical
  failure pattern on every test query. Confirms this is architectural
  (static/mean-pooled), not a capacity limit — a bigger model in the same
  family doesn't help.
- **Reverting to the pre-migration float32 transformer**
  (`sentence-transformers/all-MiniLM-L6-v2`, real attention-based
  embeddings, tested via `uv run --with fastembed`): ~111 texts/sec
  measured → **~11.6 minutes** to reindex the full corpus (worse than the
  "several minutes" complaint that motivated the 2026-07-19 model2vec
  migration in the first place), and *still* doesn't reliably fix ranking
  — on a curated relevant-only subset it still ranks MMS1's MEC-derived
  field above FGM, and in one case ranked a wrong-mission (MMS1) entry #1
  for an ACE-mission query.
- **Custom IDF-weighted pooling for model2vec** (via `encode_as_sequence()`
  + `tokenize()`, SIF-style): actively worse. Real corpus-wide IDF gives
  `"field"` (present in 71,472/77,157 entries) a weight of ~0.08 — it gets
  almost deleted from the query vector — while `"spacecraft"` (rare,
  IDF=3.67) dominates completely, pulling in Voyager's literal `Spacecraft`
  coordinate-frame field and unrelated `matrix1`/`matrix3` components.

**Common thread**: every attempt to mix or rerank using the semantic score
regresses, because REACH/Voyager/Pioneer-style entries are already a
genuine near-tie with the correct entry on whichever axis is used to decide
"good enough to compete." The fix is not a better weight — it's not
letting the two signals compete for the same ranking slots at all.

### What does work: BM25F, kept separate from semantic

**BM25** (real term-frequency + corpus-wide IDF, hand-rolled — no new
dependency, ~20 lines) already fixes the reported query outright: all top-10
results become MMS1's own products (MEC-derived fields, since their CATDESC
literally says "...spacecraft", which is a legitimate answer — FGM itself
ranks lower only because its own CATDESC doesn't contain the word
"spacecraft", a fact about the corpus text, not a ranking bug). It also
gets `"ACE MAG B_gsm"`, `"MMS1 FGM"`, `"solar wind velocity"`, and
`"electron count rate"` right.

**BM25F** (field-weighted: boost matches inside the clean path/mission/
instrument hierarchy over matches inside the free-text CATDESC prose)
sharpens this further without reintroducing any of the failure modes above,
because the extra weight is applied *inside* BM25's own properly-IDF-
weighted formula, not as a bolt-on additive score:
- `"ACE MAG B_gsm"`: GOES drops from rank #2 to #10, ACE dominates the
  top of the list.
- `"MMS1 spacecraft magnetic field"`: REACH stays pinned around rank #18 —
  well outside any reasonable results view.
- No regressions on any other tested query.
- Cost: index build 1.2-2.4s for the full 77k-entry corpus; queries
  20-40ms. Both comfortably inside the "shouldn't take long" / "should be
  fast" constraints — and dramatically faster than the 15.8s measured for
  running the *old* per-entry fuzzy `SubsequenceMatcher` over the full
  corpus from Python, which was never viable at this scale.

Semantic search still earns its place: on a genuine vocabulary-gap query
("how many particles per second", no literal overlap with any field name),
BM25 finds nothing good while semantic correctly surfaces particle-flux
datasets. So the design keeps both, but stops letting them compete for the
same ranking slots (see below).

## Decisions reached this session

1. **Add a hand-rolled BM25F implementation** (`bm25_index.py`) as the
   primary ranking signal. No new dependency — an inverted index + the
   standard BM25 formula is straightforward and every property needed
   (real IDF, field weighting) was validated by hand this session.
2. **Field-weight path over prose**: each corpus entry's text splits into
   the `path_key` (clean mission/instrument/dataset/variable hierarchy) and
   the remaining metadata prose (CATDESC/FIELDNAM/etc.). Path-field term
   matches get `w_path=6.0`, metadata matches get `w_meta=1.0`. Both
   constants are named/tunable, not magic numbers inline.
3. **Full rebuild every reindex, no incremental caching for the BM25
   index.** Unlike embeddings (which needed the 2026-07-19 incremental-cache
   design because a full re-embed took minutes), a full BM25F rebuild over
   the whole corpus takes ~1-2s — cheap enough that incremental-diff
   complexity isn't worth it. Simpler code, same architecture pattern
   (`index_worker.run`, subprocess-offloaded) already in place.
4. **Combine BM25F and semantic by score band, never by blend or rerank.**
   `query()` computes both. BM25F matches within 50% of that query's own
   top BM25F score are "confident" and mapped into a high band (`50-100`,
   linear in `bm25_score/max_bm25_score`). Everything else — including
   every candidate BM25F found nothing confident for — falls back to a
   low band (`0-50`, linear in semantic cosine similarity). A confident
   BM25F match can therefore never be outranked by a semantic one; a
   semantic-only match can still surface when BM25F has nothing.
   `50%`/confident-threshold is a named, tunable constant, chosen as a
   reasonable starting point from this session's testing — not derived
   from a formal calibration.
5. **`query()`'s return shape doesn't change**: still `dict[path_key,
   score]` on a 0-100 scale. `ProductsFlatFilterModel.set_external_scores`
   and its `max(free_text_score, external_score)` combination in
   SciQLopPlots (C++) are untouched — the fix is entirely inside
   `SmartSearchRegistry.query()`'s scoring, which already feeds that same
   contract. **No SciQLopPlots changes.**

## Non-goals (explicitly ruled out this session, not to be re-litigated without new evidence)

- **Dropping semantic search entirely**: tested directly — BM25 alone
  regresses genuine vocabulary-gap/paraphrase queries with zero
  replacement. Keep it as the fallback tier.
- **Perfectly distinguishing "many mediocre-but-real BM25 matches" from
  "coincidental matches on filler words"** for the confident-band gate: no
  score-based threshold (relative-to-max or absolute) cleanly separated
  these in testing — `"how many particles per second"`'s top BM25 scores
  (~18.1-18.2) sit in the same numeric range as clearly-good matches for
  other queries (14-24). This is a real ranking-research problem, not a
  quick fix. Accepted as a known v1 limitation: such queries are no worse
  than today's (already-broken) behavior, and this search tool is used by
  domain experts searching mission/instrument/field jargon far more often
  than full natural-language questions. Revisit only with real usage
  evidence that this matters in practice.
- **Any semantic blending/reranking of BM25F's own top results** — five
  independent variants tried this session, all regressed. Not worth a
  sixth attempt without a fundamentally different idea.
- **A bigger/different embedding model** — tested `potion-base-32M` (same
  architecture, 4x params: no improvement) and float32
  `all-MiniLM-L6-v2` (different architecture: ~11.6min reindex, still
  doesn't reliably fix ranking). Neither is worth the cost.
- **Custom IDF-weighted pooling for model2vec** — tested, actively worse
  (see above). Not a viable lever.
- **Incremental caching for the BM25F index** — full rebuild is already
  fast enough (~1-2s at 77k entries) that the added complexity isn't
  justified. Revisit only if corpus size grows by another order of
  magnitude.
- **SciQLopPlots changes** — the entire fix lives in
  `SciQLop/components/smart_search/`, consuming the existing
  `set_external_scores` contract. Out of scope for this repo's changes.

## Target architecture

### Module changes

```
components/smart_search/bm25_index.py     NEW: tokenize, build per-field inverted index, BM25F score
components/smart_search/index_worker.py    MODIFY: run() also builds a BM25Index from the snapshot, returns it alongside embeddings
components/smart_search/registry.py        MODIFY: _DomainState gains bm25_index; _handle_reindex_job unpacks it; query() combines BM25F + semantic by score band
```

`domain.py`, `components/products/smart_search_domain.py`,
`product_search_overlay.py`, `model_fetch.py`, `settings.py`, and the
SciQLopPlots side are untouched.

### `bm25_index.py` — new module

Pure functions + one small immutable result type. No I/O, no Qt, easy to
unit test in isolation.

```python
"""Hand-rolled field-weighted BM25 (BM25F) over a search domain's corpus.
Two fields per entry -- the clean path/mission/instrument hierarchy
(path_key) and the free-text metadata prose that follows it -- so an
identifier match (e.g. a mission name) can be weighted higher than a
prose match, without needing per-word heuristics: see docs/superpowers/
specs/2026-07-20-smart-search-bm25-ranking-design.md for why plain BM25
and every semantic-blending alternative were tried and rejected first."""
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Sequence

from SciQLop.components.smart_search.domain import NodeSnapshot

_TOKEN_RE = re.compile(r'[a-z0-9]+')
_K1 = 1.5
_B = 0.75
_W_PATH = 6.0
_W_META = 1.0


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


@dataclass(frozen=True)
class BM25Index:
    path_keys: list[str]
    path_inverted: dict[str, dict[int, int]]
    meta_inverted: dict[str, dict[int, int]]
    path_len: list[int]
    meta_len: list[int]
    path_avgdl: float
    meta_avgdl: float
    doc_count: int


def build(snapshot: Sequence[NodeSnapshot]) -> BM25Index:
    path_keys = [n.path_key for n in snapshot]
    path_tokens = [_tokenize(n.path_key) for n in snapshot]
    meta_tokens = [_tokenize(n.raw_text[len(n.path_key):]) for n in snapshot]

    def invert(field_tokens: list[list[str]]) -> dict[str, dict[int, int]]:
        inverted: dict[str, dict[int, int]] = defaultdict(dict)
        for doc_id, toks in enumerate(field_tokens):
            for term, count in Counter(toks).items():
                inverted[term][doc_id] = count
        return dict(inverted)

    path_len = [len(t) for t in path_tokens]
    meta_len = [len(t) for t in meta_tokens]
    doc_count = len(path_keys)
    return BM25Index(
        path_keys=path_keys,
        path_inverted=invert(path_tokens),
        meta_inverted=invert(meta_tokens),
        path_len=path_len,
        meta_len=meta_len,
        path_avgdl=(sum(path_len) / doc_count) if doc_count else 1.0,
        meta_avgdl=(sum(meta_len) / doc_count) if doc_count else 1.0,
        doc_count=doc_count,
    )


def _idf(index: BM25Index, term: str) -> float:
    n = len(set(index.path_inverted.get(term, {})) | set(index.meta_inverted.get(term, {})))
    return math.log((index.doc_count - n + 0.5) / (n + 0.5) + 1)


def score(index: BM25Index, query: str) -> dict[str, float]:
    """Returns {path_key: raw_bm25f_score} for every entry with at least
    one matching term. Empty dict if the query has no vocabulary overlap
    with the corpus at all."""
    scores: dict[int, float] = defaultdict(float)
    for term in _tokenize(query):
        idf = _idf(index, term)
        if idf <= 0:
            continue
        path_postings = index.path_inverted.get(term, {})
        meta_postings = index.meta_inverted.get(term, {})
        for doc_id in set(path_postings) | set(meta_postings):
            tf = _W_PATH * path_postings.get(doc_id, 0) + _W_META * meta_postings.get(doc_id, 0)
            doc_len = _W_PATH * index.path_len[doc_id] + _W_META * index.meta_len[doc_id]
            avgdl = _W_PATH * index.path_avgdl + _W_META * index.meta_avgdl
            denom = tf + _K1 * (1 - _B + _B * doc_len / avgdl)
            scores[doc_id] += idf * (tf * (_K1 + 1)) / denom
    return {index.path_keys[doc_id]: s for doc_id, s in scores.items()}
```

### `index_worker.run` — builds the BM25 index alongside embeddings

Same subprocess job, same snapshot, one more cheap step. Return shape
changes from `dict[path_key, vector]` to a small `IndexResult`:

```python
from dataclasses import dataclass

from SciQLop.components.smart_search import bm25_index


@dataclass(frozen=True)
class IndexResult:
    embeddings: dict[str, "np.ndarray"]
    bm25: bm25_index.BM25Index


def run(snapshot, model_name, cache_dir, index_cache_path) -> IndexResult:
    embeddings = _run_embeddings(snapshot, model_name, cache_dir, index_cache_path)  # today's run(), renamed
    return IndexResult(embeddings=embeddings, bm25=bm25_index.build(snapshot))
```

(Today's cache-aware embedding logic is unchanged, just extracted under a
private name and called from the new `run`.)

### `registry.py` changes

`_DomainState` gains one field:

```python
@dataclass
class _DomainState:
    domain: SearchDomain
    reindex_timer: QTimer
    job_id: Optional[str] = None
    dirty: bool = False
    path_keys: list = field(default_factory=list)
    matrix: Optional[np.ndarray] = None
    bm25: Optional[bm25_index.BM25Index] = None
```

`_handle_reindex_job` unpacks the richer result:

```python
        if status == "done":
            result = self._jobs_backend.job_result(job_id)
            state.path_keys = list(result.embeddings.keys())
            state.matrix = np.stack(list(result.embeddings.values())) if result.embeddings else None
            state.bm25 = result.bm25
            self._jobs_backend.forget_job(job_id)
```

`query()` combines BM25F and semantic by score band:

```python
    _BM25_CONFIDENT_FRAC = 0.5
    _CONFIDENT_BAND = (50.0, 100.0)
    _FALLBACK_BAND = (0.0, 50.0)

    def query(self, domain_name: str, text: str) -> dict:
        if not self._enabled or self._query_model is None:
            return {}
        state = self._domains.get(domain_name)
        if state is None or state.matrix is None:
            return {}

        bm25_scores = bm25_index.score(state.bm25, text) if state.bm25 else {}
        max_bm25 = max(bm25_scores.values(), default=0.0)
        confident = {
            path_key: score for path_key, score in bm25_scores.items()
            if max_bm25 > 0 and score >= self._BM25_CONFIDENT_FRAC * max_bm25
        }

        semantic = self._semantic_scores(state, text)  # today's cosine-similarity body, extracted

        _, hi = self._CONFIDENT_BAND
        result = {k: hi * (v / max_bm25) for k, v in confident.items()}
        # v/max_bm25 is confined to [_BM25_CONFIDENT_FRAC, 1.0] for entries
        # that passed the confident filter above, so this lands exactly in
        # [_BM25_CONFIDENT_FRAC * hi, hi] == the announced confident band.
        _, fhi = self._FALLBACK_BAND
        for path_key, sim in semantic.items():
            if path_key not in result:
                result[path_key] = fhi * (sim / 100.0)
        return result
```

## Testing strategy

- **`bm25_index.py`** (pure functions, no mocks needed): tiny synthetic
  corpora (2-5 `NodeSnapshot`s) —
  - IDF: a term in every doc scores 0 contribution; a term in one doc out
    of many scores highly.
  - Field weighting: a term appearing only in `path_key` outscores the
    same term appearing only in the metadata suffix, for otherwise-equal
    documents.
  - Multi-term queries: score is the sum of per-term contributions; a
    query term absent from the whole corpus is silently skipped, not an
    error.
  - Empty snapshot / empty query: no crash, empty result.
- **`index_worker.py`**: existing cache-aware embedding tests unchanged
  (now exercised via the renamed private function); one new test asserts
  `run()`'s returned `IndexResult.bm25` reflects the current snapshot
  (e.g. a term unique to one entry's path resolves to that entry via
  `bm25_index.score`).
- **`registry.py`**: `query()` tests for —
  - a query with a confident BM25 match: that entry's score lands in the
    confident band (`>= 50`), and a semantically-similar-but-lexically-
    unrelated decoy entry (present only via a crafted high semantic
    similarity) does not outscore it — the regression test for this whole
    investigation.
  - a query with zero BM25 vocabulary overlap: falls back entirely to the
    semantic band, no `KeyError`/crash on `max(..., default=0.0)`.
  - `_handle_reindex_job` sets `state.bm25` from `result.bm25` alongside
    the existing `matrix`/`path_keys` assertions.

## Open parameters flagged for tuning during implementation

Per this session's TDD workflow: write the failing regression test for the
originally-reported query first, then implement — these constants are
starting points, not final:

- `_W_PATH = 6.0` / `_W_META = 1.0` (path field weight in BM25F)
- `_K1 = 1.5` / `_B = 0.75` (standard BM25 defaults, not corpus-tuned)
- `_BM25_CONFIDENT_FRAC = 0.5` (confident-band threshold)
