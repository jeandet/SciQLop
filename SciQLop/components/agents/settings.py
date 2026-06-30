"""Persisted settings for the agent chat dock."""
from typing import ClassVar, Dict

from pydantic import BaseModel, Field

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
    sessions_pane_visible: bool = Field(default=True, json_schema_extra={"widget": "hidden"})
    sessions_pane_width: int = Field(default=280, json_schema_extra={"widget": "hidden"})


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


def _session_key(backend: str, session_id: str) -> str:
    return f"{backend}/{session_id}"


class SessionMetaEntry(BaseModel):
    name: str = ""
    pinned: bool = False


class AgentSessionMeta(ConfigEntry):
    category: ClassVar[str] = SettingsCategory.APPLICATION
    subcategory: ClassVar[str] = "Agent chat"
    entries: Dict[str, SessionMetaEntry] = Field(
        default_factory=dict, json_schema_extra={"widget": "hidden"})

    def get(self, backend: str, session_id: str) -> SessionMetaEntry:
        return self.entries.get(_session_key(backend, session_id), SessionMetaEntry())

    def set_name(self, backend: str, session_id: str, name: str) -> None:
        entry = self.entries.setdefault(_session_key(backend, session_id), SessionMetaEntry())
        entry.name = name
        self.save()

    def set_pinned(self, backend: str, session_id: str, pinned: bool) -> None:
        entry = self.entries.setdefault(_session_key(backend, session_id), SessionMetaEntry())
        entry.pinned = pinned
        self.save()
