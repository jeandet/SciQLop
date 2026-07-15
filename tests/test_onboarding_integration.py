from .fixtures import *


def test_full_tour_completes_through_all_five_steps_or_aborts_cleanly(main_window, qtbot):
    """Drives steps 1-2 for real (deterministic, no network). Step 3 depends
    on a real product provider being registered -- in CI/offline test runs
    that's typically not the case, so this test accepts either a full
    completion (if a provider happens to be loaded) or the documented
    step-3 abort, and asserts both leave the app in a clean, consistent
    state either way."""
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    from SciQLop.components.onboarding.backend.targets import (
        resolve_add_panel_button, side_tab_resolver)
    from SciQLop.components.onboarding.ui.tour_controller import run_tour

    with OnboardingSettings() as s:
        s.completed_tours = {}

    controller = run_tour(main_window, "getting_started")
    controller._SHORT_TIMEOUT_FOR_TESTS = 1.0

    try:
        qtbot.waitUntil(
            lambda: resolve_add_panel_button(main_window, {}) is not None, timeout=1000)
        assert controller._current_step().step_id == "create_panel"
        resolve_add_panel_button(main_window, {}).click()

        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "open_products",
            timeout=2000)

        side_tab_resolver("Products")(main_window, {}).click()
        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "plot_product"
            or not controller._coach_mark.isVisible(),
            timeout=2000)

        qtbot.waitUntil(
            lambda: OnboardingSettings().completed_tours.get("getting_started") is True,
            timeout=3000)
        assert not controller._coach_mark.isVisible()
    finally:
        controller.abort()
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))
