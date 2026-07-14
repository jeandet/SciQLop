# tests/test_onboarding_wiring.py
from .fixtures import *
import pytest


def test_tools_menu_has_replay_onboarding_action(main_window):
    actions = [a.text() for a in main_window.toolsMenu.actions()]
    assert "Replay Onboarding Tour" in actions


def test_replay_action_starts_tour_even_if_already_completed(main_window, qtbot):
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button

    with OnboardingSettings() as s:
        s.tour_completed = True

    replay_action = next(
        a for a in main_window.toolsMenu.actions()
        if a.text() == "Replay Onboarding Tour")
    replay_action.trigger()

    qtbot.waitUntil(
        lambda: main_window._onboarding_controller is not None
        and main_window._onboarding_controller._coach_mark.isVisible(),
        timeout=1000)
    main_window._onboarding_controller.abort()


def test_maybe_run_onboarding_tour_skips_when_already_completed(main_window, qtbot):
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.tour_completed = True

    main_window._onboarding_controller = None
    main_window._maybe_run_onboarding_tour(None)
    qtbot.wait(200)
    assert main_window._onboarding_controller is None


def test_maybe_run_onboarding_tour_starts_when_not_completed(main_window, qtbot):
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.tour_completed = False

    main_window._onboarding_controller = None
    main_window._maybe_run_onboarding_tour(None)
    qtbot.waitUntil(lambda: main_window._onboarding_controller is not None, timeout=1000)
    main_window._onboarding_controller.abort()
