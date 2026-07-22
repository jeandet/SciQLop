from tests.smart_search_benchmark.cases import CASES, BenchmarkCase, DEFAULT_TOP_N


def test_default_top_n_is_ten():
    assert DEFAULT_TOP_N == 10


def test_benchmark_case_top_n_defaults_to_none():
    case = BenchmarkCase(query="q", expected_prefixes=["p"])
    assert case.top_n is None


def test_every_seed_case_has_at_least_one_expected_prefix():
    for case in CASES:
        assert case.expected_prefixes, f"{case.query!r} has no expected_prefixes"


def test_seed_case_queries_are_unique():
    queries = [case.query for case in CASES]
    assert len(queries) == len(set(queries))


def test_seed_corpus_has_at_least_the_known_cases():
    queries = {case.query for case in CASES}
    assert {
        "MMS spacecraft 1 magnetic field",
        "MMS1 spacecraft magnetic field",
        "MMS1 Search Coil",
    } <= queries
