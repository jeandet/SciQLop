def test_settings_has_two_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS_STEPS
    assert [s.step_id for s in SETTINGS_STEPS] == ["open_settings", "browse_categories"]


def test_only_open_settings_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS_STEPS
    by_id = {s.step_id: s for s in SETTINGS_STEPS}
    assert by_id["open_settings"].completion is not None
    assert by_id["browse_categories"].completion is None
