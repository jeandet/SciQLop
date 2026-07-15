from SciQLop.components.onboarding.backend.tour import Tour

_registry: dict[str, Tour] = {}


def register_tour(tour: Tour) -> None:
    if tour.id in _registry:
        raise ValueError(f"Tour {tour.id!r} is already registered")
    if not tour.steps:
        raise ValueError(f"Tour {tour.id!r} has no steps")
    _registry[tour.id] = tour


def get_tour(tour_id: str) -> Tour | None:
    return _registry.get(tour_id)


def all_tours() -> list[Tour]:
    return list(_registry.values())


def register_builtin_tours() -> None:
    """Import every built-in tour module -- each registers itself as a
    module-level side effect. Safe to call more than once: Python only
    executes a module body on its first import."""
    from SciQLop.components.onboarding.backend import tour_getting_started  # noqa: F401


def _forget_tour_for_tests(tour_id: str) -> None:
    _registry.pop(tour_id, None)


def _reset_registry_for_tests() -> None:
    _registry.clear()
