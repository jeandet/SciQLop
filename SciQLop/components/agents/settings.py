"""Persisted settings for the agent chat dock."""
from typing import ClassVar

from pydantic import Field

from SciQLop.components.settings import SettingsCategory
from SciQLop.components.settings.backend import ConfigEntry
from SciQLop.components.settings.backend.entry import KeyringMapping


class AgentChatSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Agent chat"
    tool_verbosity: int = Field(
        default=1, ge=1, le=3,
        description="How much of the agent's tool activity to show in the chat "
                    "(1 = step names, 2 = + inputs, 3 = + result summaries).",
    )


class AdsCredentialsSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Agent chat"
    _keyring_ = KeyringMapping("service", "username", "token")
    service: str = Field(default="nasa-ads", json_schema_extra={"widget": "hidden"})
    username: str = Field(default="ads_api_token", json_schema_extra={"widget": "hidden"})
    token: str = Field(
        default="",
        description="NASA ADS API token (https://ui.adsabs.harvard.edu/user/settings/token)",
        json_schema_extra={"widget": "password"},
    )
