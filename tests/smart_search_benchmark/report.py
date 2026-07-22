"""Standalone report for the smart-search benchmark corpus: shows each
case's pass/fail and best rank against the real product corpus, for
judging whether a ranking change helped while iterating. Pytest
(tests/test_smart_search_benchmark.py) stays the pass/fail gate; this is
the diagnostic view.

Run: uv run python -m tests.smart_search_benchmark.report
See docs/superpowers/specs/2026-07-22-smart-search-benchmark-corpus-design.md."""
import sys

from tests.smart_search_benchmark.cases import CASES, DEFAULT_TOP_N
from tests.smart_search_benchmark.harness import CACHE_PATH, EvaluationResult, evaluate, load_real_corpus


def _sort_key(result: EvaluationResult):
    if result.passed:
        return (1, 0)
    return (0, result.best_rank if result.best_rank is not None else float("inf"))


def format_report(results: list) -> str:
    ordered = sorted(results, key=_sort_key)
    lines = [f"{'STATUS':6s} {'RANK':>6s} {'N':>4s}  QUERY"]
    for result in ordered:
        status = "PASS" if result.passed else "FAIL"
        rank = str(result.best_rank) if result.best_rank is not None else "-"
        top_n = result.case.top_n if result.case.top_n is not None else DEFAULT_TOP_N
        lines.append(f"{status:6s} {rank:>6s} {top_n:>4d}  {result.case.query}")
    passed = sum(1 for r in results if r.passed)
    lines.append(f"\n{passed}/{len(results)} cases passing")
    return "\n".join(lines)


def main() -> int:
    if not CACHE_PATH.exists():
        print(f"No real product corpus cache found at {CACHE_PATH} -- "
              "run the app with smart search enabled at least once first.")
        return 1
    corpus = load_real_corpus()
    results = [evaluate(case, corpus) for case in CASES]
    print(format_report(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
