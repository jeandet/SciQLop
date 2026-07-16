from .fixtures import *


def test_full_tour_starts_and_completes_the_first_step_for_real(main_window, qtbot):
    """Drives create_panel for real (deterministic, no network, no
    dock-visibility timing dependency). This is deliberately the only
    step driven through real clicks here: open_products' completion
    (dock visibilityChanged) does not reliably fire from a synthetic
    .click() in headless/Xvfb test runs regardless of anything in this
    tour (confirmed independently -- still stuck after a 1.5s wait), and
    plot_product no longer auto-advances at all (it's dismiss-only, see
    tour_getting_started.py's comment on that step) -- so there is no
    further step in this specific tour that can be reliably driven
    end-to-end through real widget interaction in this environment.
    The generic "dismiss-only step advances on Got It" mechanism
    plot_product now relies on is already covered by
    test_onboarding_tour_controller.py::test_dismiss_only_step_advances_on_got_it,
    and this tour's per-step properties (which are dismiss-only, which
    poll, block_input, etc.) are covered by
    test_onboarding_tour_getting_started.py."""
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button
    from SciQLop.components.onboarding.ui.tour_controller import run_tour

    with OnboardingSettings() as s:
        s.completed_tours = {}

    controller = run_tour(main_window, "getting_started")
    try:
        qtbot.waitUntil(
            lambda: resolve_add_panel_button(main_window, {}) is not None, timeout=1000)
        assert controller._current_step().step_id == "create_panel"
        resolve_add_panel_button(main_window, {}).click()

        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "open_products",
            timeout=2000)
    finally:
        controller.abort()
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))
