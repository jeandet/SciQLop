"""Public facade for the smart-search component. Wraps a lazily-constructed
SmartSearchRegistry singleton -- see docs/superpowers/specs/
2026-07-17-smart-search-component-design.md."""
from SciQLop.components.smart_search.domain import SearchDomain
from SciQLop.components.smart_search.registry import SmartSearchRegistry
from SciQLop.components.smart_search.settings import AVAILABLE_MODELS, SmartSearchSettings

_registry = None


def _jobs_backend_instance():
    from SciQLop.components.jobs.backend.jobs_backend import jobs_backend_instance
    return jobs_backend_instance()


def _cache_dir() -> str:
    from platformdirs import user_cache_dir
    return user_cache_dir(appname="sciqlop", appauthor="LPP", ensure_exists=True) + "/smart_search_models"


def _get_registry() -> SmartSearchRegistry:
    global _registry
    if _registry is None:
        with SmartSearchSettings() as settings:
            model_name = settings.model
        _registry = SmartSearchRegistry(_jobs_backend_instance(), model_name=model_name, cache_dir=_cache_dir())
    return _registry


def register_domain(domain: SearchDomain) -> None:
    _get_registry().register_domain(domain)


def unregister_domain(name: str) -> None:
    _get_registry().unregister_domain(name)


def notify_changed(domain_name: str) -> None:
    _get_registry().notify_changed(domain_name)


def query(domain_name: str, text: str) -> dict:
    return _get_registry().query(domain_name, text)


def is_available() -> bool:
    try:
        import fastembed  # noqa: F401
    except ImportError:
        return False
    return True


def is_enabled() -> bool:
    return _get_registry().is_enabled()


def set_enabled(enabled: bool, on_ready=None, on_error=None) -> None:
    _get_registry().set_enabled(enabled, on_ready=on_ready, on_error=on_error)
    with SmartSearchSettings() as settings:
        settings.enabled = enabled


def available_models() -> list:
    return list(AVAILABLE_MODELS)


def get_model() -> str:
    with SmartSearchSettings() as settings:
        return settings.model


def set_model(name: str) -> None:
    if name not in AVAILABLE_MODELS:
        raise ValueError(f"Unknown smart-search model: {name!r}. Available: {AVAILABLE_MODELS}")
    with SmartSearchSettings() as settings:
        settings.model = name
