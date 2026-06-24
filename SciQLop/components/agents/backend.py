"""Agent backend protocol — contract a chat-capable plugin implements."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from .chat import ChatMessage, ImageBlock, TextBlock, ThinkingBlock

StreamBlock = TextBlock | ThinkingBlock | ImageBlock
ConfirmCallback = Callable[[str, dict], Awaitable[bool]]
# questions: list of {question, header, options:[{label, description}], multiSelect}
# returns: {question_text: chosen_label | [chosen_labels]}
AskQuestionCallback = Callable[[list], Awaitable[dict]]


@dataclass
class BackendContext:
    main_window: Any
    tools: List[dict]
    tempdir: Path
    confirm_cb: ConfirmCallback
    allow_writes: bool = False
    ask_question_cb: Optional[AskQuestionCallback] = None


@dataclass
class SessionEntry:
    id: str
    label: str
    mtime: float


@runtime_checkable
class AgentBackend(Protocol):
    display_name: str
    model_choices: List[Tuple[str, Optional[str]]]
    supports_sessions: bool

    def ask(
        self, prompt: str, image_paths: Optional[List[str]] = None
    ) -> AsyncIterator[StreamBlock]:
        ...

    async def reset(self) -> None:
        ...

    async def cancel(self) -> None:
        ...

    async def resume(self, session_id: str) -> None:
        ...

    async def set_model(self, model: Optional[str]) -> None:
        ...

    def set_allow_writes(self, allow: bool) -> None:
        ...

    async def list_slash_commands(self) -> List[str]:
        ...

    def list_sessions(self) -> List[SessionEntry]:
        ...

    def load_session(self, session_id: str, image_tempdir: Path) -> List[ChatMessage]:
        ...
