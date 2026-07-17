def test_catalogs_has_five_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    assert [s.step_id for s in CATALOGS_STEPS] == [
        "open_catalogs", "meet_providers", "create_catalog",
        "overlay_catalog", "create_event",
    ]


def test_overlay_catalog_polls_with_timeout():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["overlay_catalog"].poll is True
    assert by_id["overlay_catalog"].timeout_s is not None
    assert by_id["overlay_catalog"].timeout_message is not None
    for step_id in ("open_catalogs", "meet_providers", "create_catalog", "create_event"):
        assert by_id[step_id].poll is False
        assert by_id[step_id].timeout_s is None


def test_only_open_catalogs_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["open_catalogs"].completion is not None
    for step_id in ("meet_providers", "create_catalog", "overlay_catalog", "create_event"):
        assert by_id[step_id].completion is None


def test_meet_providers_targets_the_catalog_tree():
    """The three providers ('My Catalogs', 'Shared', 'Remote') are the
    top-level rows of the same catalog tree create_catalog targets --
    see CatalogTreeModel._add_provider_node."""
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    from SciQLop.components.onboarding.backend import targets
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["meet_providers"].resolver is targets.resolve_catalog_tree
    assert by_id["meet_providers"].resolver is by_id["create_catalog"].resolver


def test_overlay_catalog_precedes_create_event():
    """create_event's tip (draw an event on the overlaid catalog) only
    makes sense once a catalog is actually overlaid on a plot -- the
    panel's edit-mode span creation targets whichever catalog is
    selected/overlaid there (PanelCatalogManager._apply_span_creation_state).
    overlay_catalog must run first."""
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    step_ids = [s.step_id for s in CATALOGS_STEPS]
    assert step_ids.index("overlay_catalog") < step_ids.index("create_event")


def test_create_event_resolver_targets_the_whole_panel():
    """The tip describes switching the panel's mode (bottom chrome
    dropdown) and then drawing on the plot itself -- two separate
    widgets within the same panel. Targeting only one of them would
    dim/block the other, the same class of bug fixed for the old
    add_event step's tree-vs-button split."""
    from SciQLop.components.onboarding.backend.tour_catalogs import CATALOGS_STEPS
    from SciQLop.components.onboarding.backend import targets
    by_id = {s.step_id: s for s in CATALOGS_STEPS}
    assert by_id["create_event"].resolver is targets.resolve_panel_widget
