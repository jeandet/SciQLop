from typing import Literal

from SciQLop.components.settings import SettingsCategory
from SciQLop.components.settings.backend import ConfigEntry

AVAILABLE_MODELS = ("minishlab/potion-base-8M", "minishlab/potion-base-32M")


class SmartSearchSettings(ConfigEntry):
    category = SettingsCategory.APPLICATION
    subcategory = "Smart Search"

    enabled: bool = False
    model: Literal["minishlab/potion-base-8M", "minishlab/potion-base-32M"] = AVAILABLE_MODELS[0]
