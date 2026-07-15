def test_getting_started_has_eleven_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    assert [s.step_id for s in GETTING_STARTED.steps] == [
        "create_panel", "open_products", "plot_product",
        "overlay_vs_new_subplot", "shortcut_tip",
        "open_catalogs", "create_catalog", "add_event", "overlay_catalog",
        "open_settings", "browse_categories",
    ]


def test_polling_steps_have_timeouts():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    polling_steps = {"plot_product", "overlay_catalog"}
    for step_id, step in by_id.items():
        if step_id in polling_steps:
            assert step.poll is True
            assert step.timeout_s is not None
            assert step.timeout_message is not None
        else:
            assert step.poll is False
            assert step.timeout_s is None


def test_only_plot_product_step_opts_out_of_blocking_input():
    """plot_product's completion needs a real drag from the highlighted
    product row to wherever the user's empty panel actually is -- the
    coach mark must not block input outside its own cutout for this step,
    or the drop can never land. Every other step keeps the default
    (block input outside the cutout)."""
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    assert by_id["plot_product"].block_input is False
    for step_id, step in by_id.items():
        if step_id != "plot_product":
            assert step.block_input is True


def test_tip_only_steps_have_no_completion():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    no_completion_steps = {
        "overlay_vs_new_subplot", "shortcut_tip",
        "create_catalog", "add_event", "overlay_catalog", "browse_categories",
    }
    has_completion_steps = {
        "create_panel", "open_products", "plot_product",
        "open_catalogs", "open_settings",
    }
    for step_id in no_completion_steps:
        assert by_id[step_id].completion is None
    for step_id in has_completion_steps:
        assert by_id[step_id].completion is not None


def test_getting_started_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    registry.register_builtin_tours()
    assert registry.get_tour("getting_started") is GETTING_STARTED


def test_only_getting_started_is_registered_as_a_builtin_tour():
    from SciQLop.components.onboarding.backend import registry
    registry.register_builtin_tours()
    assert {t.id for t in registry.all_tours()} == {"getting_started"}
