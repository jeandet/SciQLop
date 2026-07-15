import pytest


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "SciQLop.components.settings.backend.entry.SCIQLOP_CONFIG_DIR",
        str(tmp_path))


def test_completed_tours_defaults_to_empty():
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    assert OnboardingSettings().completed_tours == {}


def test_completed_tours_persists_across_instances():
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    with OnboardingSettings() as s:
        s.completed_tours = {"getting_started": True}
    assert OnboardingSettings().completed_tours == {"getting_started": True}
