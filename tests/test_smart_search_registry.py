from unittest.mock import MagicMock
import numpy as np
import pytest

from SciQLop.components.smart_search.registry import SmartSearchRegistry
from SciQLop.components.smart_search.domain import NodeSnapshot


class _FakeDomain:
    def __init__(self, name, nodes):
        self.name = name
        self._nodes = nodes

    def snapshot(self):
        return list(self._nodes)


@pytest.fixture
def jobs_backend(qtbot):
    from SciQLop.components.jobs.backend.jobs_backend import JobsBackend
    return JobsBackend(workspace_dir_getter=lambda: "/tmp/unused")


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
