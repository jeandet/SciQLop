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


def test_add_event_resolver_targets_the_whole_catalog_browser_unconditionally():
    """add_event's tip spans two widgets that sit side by side in the
    browser -- the catalog tree (select a catalog) and the Add Event
    button, part of the event table's toolbar on the other side (click
    it). Targeting just the tree (matching create_catalog, the original
    fix for 72a61c53's abort-the-whole-tour bug -- the tree is
    unconditional, the button is hidden until a catalog is selected)
    spotlighted only half of what the tip describes, leaving the Add
    Event button dimmed and unreachable behind the coach mark's
    block-everything-outside-the-cutout behavior. The whole browser
    widget is just as unconditional (constructed once in mainwindow.py)
    but its cutout covers both halves."""
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    from SciQLop.components.onboarding.backend import targets
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["add_event"].resolver is targets.resolve_catalogs_browser_widget
