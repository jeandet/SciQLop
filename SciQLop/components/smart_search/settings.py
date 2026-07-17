from typing import Literal

from SciQLop.components.settings import SettingsCategory
from SciQLop.components.settings.backend import ConfigEntry

AVAILABLE_MODELS = ("BAAI/bge-small-en-v1.5", "sentence-transformers/all-MiniLM-L6-v2")


class SmartSearchSettings(ConfigEntry):
    category = SettingsCategory.APPLICATION
    subcategory = "Smart Search"

    enabled: bool = False
    model: Literal["BAAI/bge-small-en-v1.5", "sentence-transformers/all-MiniLM-L6-v2"] = AVAILABLE_MODELS[0]
