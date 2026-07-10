import json

from SciQLop.core import tracing


def test_current_path_reflects_enable_and_disable(tmp_path):
    path = str(tmp_path / "trace.json")
    assert tracing.current_path() is None
    tracing.enable(path)
    try:
        # Only assert the path bookkeeping -- is_enabled() may be False if
        # the installed SciQLopPlots build predates the Python tracing
        # module, but current_path() must still reflect our own call.
        assert tracing.current_path() == path
    finally:
        tracing.disable()
    assert tracing.current_path() is None


def _write_trace(path, pid, events):
    path.write_text(json.dumps({
        "traceEvents": [
            {"ph": "M", "name": "process_name", "pid": pid, "tid": 0, "args": {"name": "x"}},
            *events,
        ],
    }))


def test_merge_worker_traces_concatenates_events(tmp_path):
    main_path = tmp_path / "main.json"
    _write_trace(main_path, 100, [{"ph": "X", "name": "main.zone", "pid": 100, "tid": 100,
                                    "ts": 0, "dur": 10}])
    worker_path = tmp_path / "main.worker-radio-200.json"
    _write_trace(worker_path, 200, [{"ph": "X", "name": "worker.zone", "pid": 200, "tid": 200,
                                      "ts": 0, "dur": 5}])

    merged_count = tracing.merge_worker_traces(str(main_path), [str(worker_path)])

    assert merged_count == 1
    data = json.loads(main_path.read_text())
    names = {e.get("name") for e in data["traceEvents"]}
    assert "main.zone" in names
    assert "worker.zone" in names
    pids = {e.get("pid") for e in data["traceEvents"] if e.get("ph") == "X"}
    assert pids == {100, 200}


def test_merge_worker_traces_skips_missing_files(tmp_path):
    main_path = tmp_path / "main.json"
    _write_trace(main_path, 100, [])
    merged_count = tracing.merge_worker_traces(str(main_path), [str(tmp_path / "nope.json")])
    assert merged_count == 0
    # main file untouched (still valid, still just the one process_name event)
    data = json.loads(main_path.read_text())
    assert len(data["traceEvents"]) == 1


def test_merge_worker_traces_returns_zero_when_main_file_missing(tmp_path):
    merged_count = tracing.merge_worker_traces(str(tmp_path / "gone.json"), [])
    assert merged_count == 0
