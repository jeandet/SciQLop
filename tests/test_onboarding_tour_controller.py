from .fixtures import *
import pytest


def test_start_shows_coach_mark_for_first_step(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    controller = TourController(main_window)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        assert controller._current_step().step_id == "create_panel"
    finally:
        controller.abort()


def test_clicking_add_panel_button_advances_to_open_products_step(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button

    controller = TourController(main_window)
    controller.start()
    try:
        qtbot.waitUntil(
            lambda: resolve_add_panel_button(main_window) is not None, timeout=1000)
        button = resolve_add_panel_button(main_window)
        button.click()
        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "open_products",
            timeout=2000)
    finally:
        controller.abort()
        panel_names = main_window.plot_panels()
        for name in panel_names:
            main_window.remove_panel(main_window.plot_panel(name))


def test_skip_sets_tour_completed_and_hides_overlay(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.tour_completed = False

    controller = TourController(main_window)
    controller.start()
    qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

    controller._coach_mark.skip_requested.emit()

    assert not controller._coach_mark.isVisible()
    assert OnboardingSettings().tour_completed is True


def test_step_3_timeout_aborts_whole_tour(main_window, qtbot, monkeypatch):
    from SciQLop.components.onboarding.ui import tour_controller as tc_mod
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    from SciQLop.components.onboarding.backend.targets import (
        resolve_add_panel_button, resolve_products_side_tab)

    # Make the step-3 resolver always return None so its poll times out —
    # steps 1 and 2 are still driven for real (cheap, deterministic).
    monkeypatch.setitem(tc_mod.RESOLVERS, "first_candidate_product", lambda mw: None)

    controller = tc_mod.TourController(main_window)
    controller._SHORT_TIMEOUT_FOR_TESTS = 0.2  # see Step 3 implementation note
    controller.start()
    try:
        qtbot.waitUntil(lambda: resolve_add_panel_button(main_window) is not None, timeout=1000)
        resolve_add_panel_button(main_window).click()
        qtbot.waitUntil(lambda: controller._current_step().step_id == "open_products", timeout=2000)

        resolve_products_side_tab(main_window).click()
        qtbot.waitUntil(lambda: controller._current_step().step_id == "plot_product", timeout=2000)

        # Step 3 polls silently (no coach mark shown) while waiting for its
        # target to resolve, so `not coach_mark.isVisible()` is already true
        # the instant polling starts -- it can't distinguish "still polling"
        # from "tour actually timed out and aborted". Wait on the
        # `tour_completed` flag itself instead: it's set exactly once, by
        # `_finish()`, on both the full-completion and the step-3-abort path.
        qtbot.waitUntil(lambda: OnboardingSettings().tour_completed is True, timeout=3000)
        assert not controller._coach_mark.isVisible()
    finally:
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))


def test_replaying_after_completion_does_not_double_fire_on_stale_connections(main_window, qtbot):
    """Regression guard: a finished/aborted controller must disconnect its
    per-step completion signal, or a second (replay) controller's own count
    gets corrupted by the first controller's dead handler still reacting to
    panel_added/plot_added on the shared, long-lived main_window."""
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button

    first = TourController(main_window)
    first.start()
    qtbot.waitUntil(lambda: resolve_add_panel_button(main_window) is not None, timeout=1000)
    first.abort()

    second = TourController(main_window)
    second.start()
    try:
        qtbot.waitUntil(lambda: resolve_add_panel_button(main_window) is not None, timeout=1000)
        resolve_add_panel_button(main_window).click()
        qtbot.waitUntil(lambda: second._current_step().step_id == "open_products", timeout=2000)
        assert second._step_index == 1
    finally:
        second.abort()
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))


def test_target_destroyed_mid_step_aborts_tour_without_crash(qapp, sciqlop_resources, qtbot):
    """Regression guard for the design spec's 'any target destroyed mid-tour
    aborts gracefully' requirement: destroying step 2's own target widget
    (the Products side-tab) while it's active must not crash and must still
    mark the tour completed (not leave it stuck forever).

    Uses a disposable, per-test main window (not the shared session-scoped
    `main_window` fixture) because this test destroys a widget that fixture
    is expected to keep alive for every other test in the suite."""
    from SciQLop.core.ui.mainwindow import SciQLopMainWindow
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button

    with OnboardingSettings() as s:
        s.tour_completed = False

    mw = SciQLopMainWindow()
    try:
        controller = TourController(mw)
        controller.start()
        qtbot.waitUntil(lambda: resolve_add_panel_button(mw) is not None, timeout=1000)
        resolve_add_panel_button(mw).click()
        qtbot.waitUntil(lambda: controller._current_step().step_id == "open_products", timeout=2000)

        controller._coach_mark._target.deleteLater()
        qtbot.waitUntil(lambda: OnboardingSettings().tour_completed is True, timeout=2000)
        assert not controller._coach_mark.isVisible()
    finally:
        for name in mw.plot_panels():
            mw.remove_panel(mw.plot_panel(name))
        mw.close()
