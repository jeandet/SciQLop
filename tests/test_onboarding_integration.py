from .fixtures import *


def test_full_tour_completes_through_all_five_steps_or_aborts_cleanly(main_window, qtbot):
    """Drives steps 1-2 for real (deterministic, no network). Step 3 depends
    on a real product provider being registered — in CI/offline test runs
    that's typically not the case, so this test accepts either a full
    completion (if a provider happens to be loaded) or the documented
    step-3 abort, and asserts both leave the app in a clean, consistent
    state either way."""
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    from SciQLop.components.onboarding.backend.targets import (
        resolve_add_panel_button, resolve_products_side_tab)
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    with OnboardingSettings() as s:
        s.tour_completed = False

    controller = TourController(main_window)
    controller._SHORT_TIMEOUT_FOR_TESTS = 1.0
    controller.start()

    try:
        qtbot.waitUntil(lambda: resolve_add_panel_button(main_window) is not None, timeout=1000)
        assert controller._current_step().step_id == "create_panel"
        resolve_add_panel_button(main_window).click()

        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "open_products",
            timeout=2000)

        resolve_products_side_tab(main_window).click()
        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "plot_product"
            or not controller._coach_mark.isVisible(),
            timeout=2000)

        # Step 3 polls silently (no coach mark shown) while waiting for a
        # real product to resolve, so `not coach_mark.isVisible()` is
        # already true the instant polling starts -- it can't distinguish
        # "still polling" from "tour actually finished". Wait on the
        # `tour_completed` flag itself instead: it's set exactly once, by
        # `_finish()`, on both the full-completion and the step-3-abort path.
        qtbot.waitUntil(lambda: OnboardingSettings().tour_completed is True, timeout=3000)
        assert not controller._coach_mark.isVisible()
    finally:
        controller.abort()
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))
