from typing import ClassVar, Dict

from pydantic import Field

from SciQLop.components.settings.backend.entry import ConfigEntry, SettingsCategory


class OnboardingSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Onboarding"

    completed_tours: Dict[str, bool] = Field(default={})
