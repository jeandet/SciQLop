def test_getting_started_has_five_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    assert [s.step_id for s in GETTING_STARTED.steps] == [
        "create_panel", "open_products", "plot_product",
        "overlay_vs_new_subplot", "shortcut_tip",
    ]


def test_only_plot_product_step_polls_with_timeout():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    assert by_id["plot_product"].poll is True
    assert by_id["plot_product"].timeout_s == 10.0
    assert by_id["plot_product"].timeout_message is not None
    for step_id in ("create_panel", "open_products",
                     "overlay_vs_new_subplot", "shortcut_tip"):
        assert by_id[step_id].poll is False
        assert by_id[step_id].timeout_s is None


def test_tip_only_steps_have_no_completion():
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    by_id = {s.step_id: s for s in GETTING_STARTED.steps}
    assert by_id["overlay_vs_new_subplot"].completion is None
    assert by_id["shortcut_tip"].completion is None
    assert by_id["create_panel"].completion is not None
    assert by_id["open_products"].completion is not None
    assert by_id["plot_product"].completion is not None


def test_getting_started_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_getting_started import GETTING_STARTED
    registry.register_builtin_tours()
    assert registry.get_tour("getting_started") is GETTING_STARTED
