"""Persisted settings for the agent chat dock."""
from typing import ClassVar

from pydantic import Field

from SciQLop.components.settings import SettingsCategory
from SciQLop.components.settings.backend import ConfigEntry


class AgentChatSettings(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Agent chat"
    tool_verbosity: int = Field(
        default=1, ge=1, le=3,
        description="How much of the agent's tool activity to show in the chat "
                    "(1 = step names, 2 = + inputs, 3 = + result summaries).",
    )
