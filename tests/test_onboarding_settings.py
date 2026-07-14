import os
import pytest


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "SciQLop.components.settings.backend.entry.SCIQLOP_CONFIG_DIR",
        str(tmp_path))


def test_tour_completed_defaults_to_false():
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    assert OnboardingSettings().tour_completed is False


def test_tour_completed_persists_across_instances():
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings
    with OnboardingSettings() as s:
        s.tour_completed = True
    assert OnboardingSettings().tour_completed is True
