from .fixtures import *


def test_picker_lists_all_registered_tours(main_window):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker
    from SciQLop.components.onboarding.backend.registry import register_builtin_tours, all_tours

    register_builtin_tours()
    picker = TourPicker(main_window)
    try:
        registered_ids = {tour.id for tour in all_tours()}
        assert set(picker._items_by_tour_id.keys()) == registered_ids
        assert registered_ids == {"getting_started"}
    finally:
        picker.close()


def test_picker_marks_completed_tours(main_window):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {"getting_started": True}

    picker = TourPicker(main_window)
    try:
        assert "Completed" in picker._items_by_tour_id["getting_started"].text()
    finally:
        picker.close()
        with OnboardingSettings() as s:
            s.completed_tours = {}


def test_start_selected_starts_the_selected_tour(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}
    main_window._onboarding_controller = None

    picker = TourPicker(main_window)
    picker._list.setCurrentItem(picker._items_by_tour_id["getting_started"])
    picker._start_selected()

    try:
        qtbot.waitUntil(
            lambda: main_window._onboarding_controller is not None
            and main_window._onboarding_controller._tour.id == "getting_started",
            timeout=1000)
    finally:
        main_window._onboarding_controller.abort()


def test_start_selected_with_no_selection_does_nothing(main_window):
    from SciQLop.components.onboarding.ui.tour_picker import TourPicker

    main_window._onboarding_controller = None
    picker = TourPicker(main_window)
    try:
        picker._list.setCurrentItem(None)
        picker._start_selected()
        assert main_window._onboarding_controller is None
    finally:
        picker.close()
