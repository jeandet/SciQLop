from typing import ClassVar

from SciQLop.components.settings.backend.entry import ConfigEntry, SettingsCategory


class OnboardingSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Onboarding"

    tour_completed: bool = False
