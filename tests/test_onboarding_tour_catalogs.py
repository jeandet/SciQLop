def test_catalogs_has_four_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    assert [s.step_id for s in CATALOGS_STEPS] == [
        "open_catalogs", "create_catalog", "add_event", "overlay_catalog",
    ]


def test_overlay_catalog_polls_with_timeout():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["overlay_catalog"].poll is True
    assert by_id["overlay_catalog"].timeout_s is not None
    assert by_id["overlay_catalog"].timeout_message is not None
    for step_id in ("open_catalogs", "create_catalog", "add_event"):
        assert by_id[step_id].poll is False
        assert by_id[step_id].timeout_s is None


def test_only_open_catalogs_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["open_catalogs"].completion is not None
    for step_id in ("create_catalog", "add_event", "overlay_catalog"):
        assert by_id[step_id].completion is None


def test_add_event_resolver_is_unconditional_like_create_catalog():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    from SciQLop.components.onboarding.backend import targets
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["add_event"].resolver is targets.resolve_catalog_tree
    assert by_id["add_event"].resolver is by_id["create_catalog"].resolver
