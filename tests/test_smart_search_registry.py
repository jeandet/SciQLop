import time
from unittest.mock import patch, MagicMock
import numpy as np
import pytest

from SciQLop.components.smart_search.registry import SmartSearchRegistry
from SciQLop.components.smart_search.domain import NodeSnapshot
from SciQLop.components.smart_search import model_fetch, index_worker


class _FakeDomain:
    def __init__(self, name, nodes):
        self.name = name
        self._nodes = nodes

    def snapshot(self):
        return list(self._nodes)


def _delayed_submit(real_submit):
    def submit(fn, *args, **kwargs):
        def wrapped(*a, **kw):
            time.sleep(0.02)
            return fn(*a, **kw)
        return real_submit(wrapped, *args, **kwargs)
    return submit


@pytest.fixture
def jobs_backend(qtbot):
    # `JobsBackend.submit_function` normally runs `fn` in a spawned
    # subprocess, which re-imports every module fresh -- any
    # `unittest.mock.patch.object` applied in this test process (below) is
    # invisible there, and an already-patched MagicMock can't even be
    # pickled to send to the child (confirmed: raises PicklingError).
    # Swapping in an in-process ThreadPoolExecutor lets mocks of
    # model_fetch.download_model/load_model actually take effect.
    # A real subprocess spawn always takes long enough that
    # Future.add_done_callback never fires before submit_function's caller
    # finishes its own bookkeeping (state.job_id = ..., self._pending_enable
    # = ...); a trivial mocked function on a ThreadPoolExecutor can complete
    # so fast that add_done_callback (per concurrent.futures semantics)
    # fires immediately and *synchronously on the submitting thread* --
    # confirmed by tracing -- which would run SmartSearchRegistry's
    # _on_job_status_changed before that bookkeeping exists, silently
    # dropping the signal. The tiny delay below restores genuine asynchrony
    # so this fixture exercises the same ordering guarantees as the real
    # executor instead of a testing artifact.
    from concurrent.futures import ThreadPoolExecutor
    from SciQLop.components.jobs.backend.jobs_backend import JobsBackend
    backend = JobsBackend(workspace_dir_getter=lambda: "/tmp/unused")
    backend._executor.shutdown(wait=False)
    executor = ThreadPoolExecutor()
    executor.submit = _delayed_submit(executor.submit)
    backend._executor = executor
    yield backend
    backend._executor.shutdown(wait=True, cancel_futures=True)


@pytest.fixture
def registry(qtbot, jobs_backend):
    return SmartSearchRegistry(jobs_backend, model_name="fake-model", cache_dir="/tmp/cache", debounce_ms=20)


def test_register_domain_then_notify_changed_submits_no_job_while_disabled(registry, jobs_backend, qtbot):
    domain = _FakeDomain("products", [NodeSnapshot("a", "text a")])
    registry.register_domain(domain)
    registry.notify_changed("products")
    qtbot.wait(50)
    assert jobs_backend.list_jobs() == []


def test_unregister_domain_stops_pending_reindex(registry, jobs_backend, qtbot):
    domain = _FakeDomain("products", [])
    registry.register_domain(domain)
    registry._enabled = True
    registry.notify_changed("products")
    registry.unregister_domain("products")
    qtbot.wait(50)
    assert jobs_backend.list_jobs() == []


def test_enable_success_calls_on_ready_and_flips_enabled(registry, qtbot):
    with patch.object(model_fetch, "download_model", return_value=None), \
         patch.object(model_fetch, "load_model", return_value=MagicMock()) as mock_load:
        ready = []
        registry.set_enabled(True, on_ready=lambda: ready.append(True))
        qtbot.waitUntil(lambda: registry.is_enabled(), timeout=5000)
    assert ready == [True]
    mock_load.assert_called_once_with("fake-model", "/tmp/cache")


def test_enable_failure_calls_on_error_and_stays_disabled(registry, qtbot):
    def _boom_download(model_name, cache_dir):
        raise RuntimeError("no network")

    with patch.object(model_fetch, "download_model", side_effect=_boom_download):
        errors = []
        registry.set_enabled(True, on_error=lambda exc: errors.append(exc))
        qtbot.waitUntil(lambda: len(errors) == 1, timeout=5000)
    assert not registry.is_enabled()
    assert isinstance(errors[0], RuntimeError)


def test_enabling_triggers_reindex_of_already_registered_domains(registry, jobs_backend, qtbot):
    domain = _FakeDomain("products", [NodeSnapshot("a", "hi")])
    registry.register_domain(domain)
    fake_model = MagicMock()
    fake_model.embed.side_effect = lambda texts: iter([np.array([1.0, 0.0]) for _ in texts])
    with patch.object(model_fetch, "download_model", return_value=None), \
         patch.object(model_fetch, "load_model", return_value=fake_model), \
         patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        registry.set_enabled(True)
        qtbot.waitUntil(lambda: registry.is_enabled(), timeout=5000)
        qtbot.waitUntil(lambda: registry._domains["products"].matrix is not None, timeout=5000)
    assert registry._domains["products"].path_keys == ["a"]


def test_corpus_change_during_inflight_reindex_triggers_one_more_after(registry, jobs_backend, qtbot):
    domain = _FakeDomain("products", [NodeSnapshot("a", "hi")])
    registry.register_domain(domain)
    fake_model = MagicMock()
    fake_model.embed.side_effect = lambda texts: iter([np.array([1.0, 0.0]) for _ in texts])
    with patch.object(model_fetch, "download_model", return_value=None), \
         patch.object(model_fetch, "load_model", return_value=fake_model), \
         patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        registry.set_enabled(True)
        qtbot.waitUntil(lambda: registry.is_enabled(), timeout=5000)
        state = registry._domains["products"]
        qtbot.waitUntil(lambda: state.job_id is not None, timeout=5000)
        domain._nodes = [NodeSnapshot("a", "hi"), NodeSnapshot("b", "new")]
        registry.notify_changed("products")
        qtbot.waitUntil(lambda: state.matrix is not None and len(state.path_keys) == 1, timeout=5000)
        qtbot.waitUntil(lambda: state.matrix is not None and len(state.path_keys) == 2, timeout=5000)


def test_query_returns_empty_dict_when_disabled(registry):
    assert registry.query("products", "hi") == {}


def test_rapid_notify_changed_burst_submits_exactly_one_reindex(registry, jobs_backend, qtbot):
    domain = _FakeDomain("products", [NodeSnapshot("a", "hi")])
    registry.register_domain(domain)
    registry._enabled = True
    for _ in range(5):
        registry.notify_changed("products")
        qtbot.wait(5)  # well under the 20ms debounce_ms configured on `registry`
    qtbot.wait(60)  # past the debounce window, no further notify_changed calls
    jobs = [j for j in jobs_backend.list_jobs() if j["name"] == "Smart search: reindex products"]
    assert len(jobs) == 1


def test_query_returns_cosine_scores(registry, qtbot):
    domain = _FakeDomain("products", [NodeSnapshot("a", "hi"), NodeSnapshot("b", "bye")])
    registry.register_domain(domain)
    fake_model = MagicMock()

    def _embed(texts):
        return iter([np.array([1.0, 0.0]) if t in ("hi", "query") else np.array([0.0, 1.0]) for t in texts])
    fake_model.embed.side_effect = _embed

    with patch.object(model_fetch, "download_model", return_value=None), \
         patch.object(model_fetch, "load_model", return_value=fake_model), \
         patch.object(index_worker.model_fetch, "load_model", return_value=fake_model):
        registry.set_enabled(True)
        qtbot.waitUntil(lambda: registry._domains["products"].matrix is not None, timeout=5000)
        scores = registry.query("products", "query")

    assert scores["a"] == pytest.approx(100.0)
    assert scores["b"] == pytest.approx(0.0)
