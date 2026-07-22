from tests.smart_search_benchmark import report
from tests.smart_search_benchmark.cases import BenchmarkCase
from tests.smart_search_benchmark.harness import EvaluationResult


def _result(query, passed, best_rank, top_n=10):
    return EvaluationResult(
        case=BenchmarkCase(query=query, expected_prefixes=["x"], top_n=top_n),
        passed=passed, best_rank=best_rank, total_candidates=100)


def test_format_report_lists_failures_before_passes():
    results = [
        _result("passing query", passed=True, best_rank=1),
        _result("failing query", passed=False, best_rank=47),
    ]
    output = report.format_report(results)
    assert output.index("failing query") < output.index("passing query")


def test_format_report_sorts_failures_by_closeness_to_threshold():
    results = [
        _result("far miss", passed=False, best_rank=500),
        _result("near miss", passed=False, best_rank=15),
    ]
    output = report.format_report(results)
    assert output.index("near miss") < output.index("far miss")


def test_format_report_handles_never_found_case():
    results = [_result("nowhere", passed=False, best_rank=None)]
    output = report.format_report(results)
    assert "nowhere" in output


def test_format_report_includes_pass_count_summary():
    results = [
        _result("a", passed=True, best_rank=1),
        _result("b", passed=False, best_rank=99),
    ]
    output = report.format_report(results)
    assert "1/2 cases passing" in output


def test_main_reports_missing_cache_cleanly(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(report, "CACHE_PATH", tmp_path / "missing.pkl")

    exit_code = report.main()

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "no real product corpus cache" in captured.out.lower()
