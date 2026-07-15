def test_settings_has_two_steps_in_order():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS
    assert [s.step_id for s in SETTINGS.steps] == ["open_settings", "browse_categories"]


def test_only_open_settings_step_has_completion():
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS
    by_id = {s.step_id: s for s in SETTINGS.steps}
    assert by_id["open_settings"].completion is not None
    assert by_id["browse_categories"].completion is None


def test_settings_is_registered():
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.tour_settings import SETTINGS
    registry.register_builtin_tours()
    assert registry.get_tour("settings") is SETTINGS
