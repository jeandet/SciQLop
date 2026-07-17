"""SmartSearchRegistry: owns one vector index per registered SearchDomain,
the shared embedding model, and reindex debouncing. See docs/superpowers/
specs/2026-07-17-smart-search-component-design.md."""
from dataclasses import dataclass, field
from typing import Dict, Optional

import numpy as np
from PySide6.QtCore import QObject, QTimer

from SciQLop.components.sciqlop_logging import getLogger
from SciQLop.components.smart_search import index_worker, model_fetch
from SciQLop.components.smart_search.domain import SearchDomain

log = getLogger(__name__)

_DEFAULT_DEBOUNCE_MS = 200


@dataclass
class _DomainState:
    domain: SearchDomain
    reindex_timer: QTimer
    job_id: Optional[str] = None
    dirty: bool = False
    path_keys: list = field(default_factory=list)
    matrix: Optional[np.ndarray] = None


class SmartSearchRegistry(QObject):
    def __init__(self, jobs_backend, model_name: str, cache_dir: str,
                 debounce_ms: int = _DEFAULT_DEBOUNCE_MS, parent=None):
        super().__init__(parent)
        self._jobs_backend = jobs_backend
        self._model_name = model_name
        self._cache_dir = cache_dir
        self._debounce_ms = debounce_ms
        self._domains: Dict[str, _DomainState] = {}
        self._job_to_domain: Dict[str, str] = {}
        self._enabled = False
        self._query_model = None
        self._pending_enable = None
        self._jobs_backend.job_status_changed.connect(self._on_job_status_changed)

    # --- domain registration -------------------------------------------------
    def register_domain(self, domain: SearchDomain) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda name=domain.name: self._trigger_reindex(name))
        self._domains[domain.name] = _DomainState(domain=domain, reindex_timer=timer)

    def unregister_domain(self, name: str) -> None:
        state = self._domains.pop(name, None)
        if state is not None:
            state.reindex_timer.stop()

    # --- reindexing -----------------------------------------------------------
    def notify_changed(self, domain_name: str) -> None:
        state = self._domains.get(domain_name)
        if state is None:
            return
        state.dirty = True
        state.reindex_timer.start(self._debounce_ms)

    def _trigger_reindex(self, domain_name: str) -> None:
        state = self._domains.get(domain_name)
        if state is None or state.job_id is not None or not self._enabled:
            return
        state.dirty = False
        snapshot = list(state.domain.snapshot())
        job_id = self._jobs_backend.submit_function(
            index_worker.run, (snapshot, self._model_name, self._cache_dir),
            f"Smart search: reindex {domain_name}")
        state.job_id = job_id
        self._job_to_domain[job_id] = domain_name

    def _on_job_status_changed(self, job_id: str, status: str) -> None:
        if self._pending_enable is not None and self._pending_enable[0] == job_id:
            self._handle_enable_job(status)
            return
        domain_name = self._job_to_domain.get(job_id)
        if domain_name is not None:
            self._handle_reindex_job(domain_name, job_id, status)

    def _handle_reindex_job(self, domain_name: str, job_id: str, status: str) -> None:
        state = self._domains.get(domain_name)
        if state is None:
            del self._job_to_domain[job_id]
            return
        if status == "done":
            result = self._jobs_backend.job_result(job_id)
            state.path_keys = list(result.keys())
            state.matrix = np.stack(list(result.values())) if result else None
        elif status == "crashed":
            log.error("Smart search reindex failed for domain %r", domain_name)
        state.job_id = None
        del self._job_to_domain[job_id]
        if state.dirty:
            self._trigger_reindex(domain_name)
