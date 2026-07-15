def test_catalogs_has_four_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    assert [s.step_id for s in CATALOGS.steps] == [
        "open_catalogs", "create_catalog", "add_event", "overlay_catalog",
    ]


def test_add_event_and_overlay_steps_poll_with_timeout():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    by_id = {s.step_id: s for s in CATALOGS.steps}
    for step_id in ("add_event", "overlay_catalog"):
        assert by_id[step_id].poll is True
        assert by_id[step_id].timeout_s is not None
        assert by_id[step_id].timeout_message is not None
    for step_id in ("open_catalogs", "create_catalog"):
        assert by_id[step_id].poll is False


def test_only_open_catalogs_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    by_id = {s.step_id: s for s in CATALOGS.steps}
    assert by_id["open_catalogs"].completion is not None
    for step_id in ("create_catalog", "add_event", "overlay_catalog"):
        assert by_id[step_id].completion is None


def test_catalogs_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS
    registry.register_builtin_tours()
    assert registry.get_tour("catalogs") is CATALOGS
