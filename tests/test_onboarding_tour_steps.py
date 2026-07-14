def test_tour_has_five_steps_in_order():
    from SciQLop.components.onboarding.backend.tour import TOUR_STEPS
    assert [s.step_id for s in TOUR_STEPS] == [
        "create_panel", "open_products", "plot_product",
        "overlay_vs_new_subplot", "shortcut_tip",
    ]


def test_only_plot_product_step_polls_with_timeout():
    from SciQLop.components.onboarding.backend.tour import TOUR_STEPS
    by_id = {s.step_id: s for s in TOUR_STEPS}
    assert by_id["plot_product"].poll is True
    assert by_id["plot_product"].timeout_s == 10.0
    assert by_id["plot_product"].timeout_message is not None
    for step_id in ("create_panel", "open_products",
                    "overlay_vs_new_subplot", "shortcut_tip"):
        assert by_id[step_id].poll is False
        assert by_id[step_id].timeout_s is None


def test_tip_only_steps_have_no_completion_signal():
    from SciQLop.components.onboarding.backend.tour import TOUR_STEPS
    by_id = {s.step_id: s for s in TOUR_STEPS}
    assert by_id["overlay_vs_new_subplot"].completion_signal_id is None
    assert by_id["shortcut_tip"].completion_signal_id is None
    assert by_id["create_panel"].completion_signal_id == "panel_created"
    assert by_id["open_products"].completion_signal_id == "products_visible"
    assert by_id["plot_product"].completion_signal_id == "plot_added"
