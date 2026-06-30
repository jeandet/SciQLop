"""Generic multi-backend chat dock."""
from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from SciQLop.components.theming import get_icon

from .backend import AgentBackend, BackendContext
from .chat import (
    ChatInput,
    ChatMessage,
    ImageBlock,
    TextBlock,
    ThinkingBlock,
    ToolActivityBlock,
    TranscriptView,
)
from .chat.session_panel import SessionListPanel
from .chat.sessions_view import ordered_sessions
from .registry import available_backends, create_backend
from .settings import AgentChatSettings, AgentSessionMeta
from .tools import build_sciqlop_tools


@dataclass
class _AgentSession:
    backend: AgentBackend
    messages: List[ChatMessage] = field(default_factory=list)
    resume_id: Optional[str] = None


class AgentChatDock(QWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Agents")
        self.setWindowIcon(get_icon("assistant"))
        self._main_window = main_window
        self._tools = build_sciqlop_tools(main_window)
        self._tempdir = Path(tempfile.mkdtemp(prefix="sciqlop_agents_"))
        self._sessions: Dict[str, _AgentSession] = {}
        self._current: Optional[str] = None
        self._allow_writes = False
        self._turn_task: Optional[asyncio.Task] = None
        self._bg_tasks: set[asyncio.Task] = set()

        self._build_ui()
        self.refresh_backends()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self._reset_btn = QPushButton("New session")
        self._reset_btn.clicked.connect(self._on_reset)
        header.addWidget(self._reset_btn)

        self._export_btn = QPushButton("Export ⤓")
        self._export_btn.setToolTip("Save this transcript as a Markdown file.")
        self._export_btn.clicked.connect(self._on_export)
        header.addWidget(self._export_btn)

        self._interactive: tuple = ()

        self._backend_combo = QComboBox()
        self._backend_combo.setToolTip("Select which agent backend to chat with.")
        self._backend_combo.currentIndexChanged.connect(self._on_backend_changed)
        header.addWidget(self._backend_combo)

        self._sessions_toggle = QPushButton("☰ Sessions")
        self._sessions_toggle.setCheckable(True)
        self._sessions_toggle.setToolTip("Show or hide the session list.")
        self._sessions_toggle.toggled.connect(self._on_sessions_toggled)
        header.addWidget(self._sessions_toggle)

        self._model_combo = QComboBox()
        self._model_combo.currentIndexChanged.connect(self._on_model_changed)
        header.addWidget(self._model_combo)

        self._writes_toggle = QCheckBox("Allow write actions")
        self._writes_toggle.setToolTip(
            "When enabled, the agent can modify SciQLop state "
            "(set time range, create panels, exec Python, edit notebooks)."
        )
        self._writes_toggle.stateChanged.connect(self._on_writes_toggled)
        header.addWidget(self._writes_toggle)

        self._verbosity_combo = QComboBox()
        self._verbosity_combo.addItems(
            ["Activity: minimal", "Activity: + inputs", "Activity: + results"])
        self._verbosity_combo.setToolTip(
            "How much of the agent's tool activity to show in the chat.")
        self._verbosity_combo.currentIndexChanged.connect(self._on_verbosity_changed)
        header.addWidget(self._verbosity_combo)

        self._status_label = QLabel("")
        self._status_label.setStyleSheet("color: gray;")
        header.addWidget(self._status_label, 1)
        layout.addLayout(header)

        self._splitter = QSplitter(Qt.Orientation.Vertical, self)
        self._splitter.setChildrenCollapsible(False)

        self._transcript = TranscriptView(self._splitter)
        self._splitter.addWidget(self._transcript)
        self._init_tool_verbosity()

        input_panel = QWidget(self._splitter)
        input_row = QHBoxLayout(input_panel)
        input_row.setContentsMargins(0, 0, 0, 0)
        self._input = ChatInput(self._tempdir / "pasted", input_panel)
        self._input.setMinimumHeight(60)
        input_row.addWidget(self._input, 1)

        self._send_btn = QPushButton("Send", input_panel)
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)

        self._stop_btn = QPushButton("Stop", input_panel)
        self._stop_btn.setVisible(False)
        self._stop_btn.clicked.connect(self._on_stop)
        input_row.addWidget(self._stop_btn)
        self._splitter.addWidget(input_panel)

        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.setSizes([400, 90])
        self._session_panel = SessionListPanel()
        self._session_panel.session_selected.connect(self._on_session_selected)
        self._session_panel.rename_requested.connect(self._on_session_rename)
        self._session_panel.pin_toggle_requested.connect(self._on_session_pin)
        self._h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._h_splitter.addWidget(self._session_panel)
        self._h_splitter.addWidget(self._splitter)
        self._h_splitter.setCollapsible(0, True)
        self._h_splitter.setStretchFactor(1, 1)
        self._h_splitter.splitterMoved.connect(self._on_splitter_moved)
        layout.addWidget(self._h_splitter, 1)
        self._restore_pane_state()

        QShortcut(QKeySequence("Ctrl+Return"), self._input, activated=self._on_send)
        QShortcut(QKeySequence("Ctrl+Enter"), self._input, activated=self._on_send)

        self._interactive = (
            self._input,
            self._send_btn,
            self._reset_btn,
            self._writes_toggle,
            self._model_combo,
        )

    def refresh_backends(self) -> None:
        names = available_backends()
        current = self._current
        self._backend_combo.blockSignals(True)
        self._backend_combo.clear()
        for name in names:
            self._backend_combo.addItem(name, name)
        self._backend_combo.blockSignals(False)
        if not names:
            self._set_empty(
                "No agent backends registered. Install sciqlop_claude or a "
                "similar plugin to enable the chat."
            )
            return
        self._set_enabled()
        target = current if current in names else names[0]
        idx = names.index(target)
        self._backend_combo.setCurrentIndex(idx)
        self._on_backend_changed(idx)

    def _set_empty(self, reason: str) -> None:
        self._transcript.render_messages(
            [ChatMessage(role="error", blocks=[TextBlock(text=reason)], done=True)]
        )
        for w in self._interactive:
            w.setEnabled(False)

    def _set_enabled(self) -> None:
        for w in self._interactive:
            w.setEnabled(True)

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _on_backend_changed(self, index: int) -> None:
        name = self._backend_combo.itemData(index)
        if not name:
            return
        self._current = name
        session = self._sessions.get(name) or self._create_session(name)
        self._sessions[name] = session
        self._bind_to_session(session)

    def _create_session(self, name: str) -> _AgentSession:
        be_tempdir = self._tempdir / name / "tool_images"
        be_tempdir.mkdir(parents=True, exist_ok=True)
        ctx = BackendContext(
            main_window=self._main_window,
            tools=self._tools,
            tempdir=be_tempdir,
            confirm_cb=self._confirm_tool_call,
            allow_writes=self._allow_writes,
            ask_question_cb=self._ask_question,
        )
        backend = create_backend(name, ctx)
        return _AgentSession(backend=backend)

    def _bind_to_session(self, session: _AgentSession) -> None:
        be = session.backend
        self._transcript.set_assistant_label(be.display_name)
        self._populate_models(be)
        self._populate_session_list(be)
        self._transcript.render_messages(session.messages)
        self._transcript.flush_now()
        self._spawn(self._refresh_completions())
        on_activated = getattr(be, "on_activated", None)
        if on_activated is not None:
            try:
                on_activated()
            except Exception:
                pass

    def reload_backend_models(self) -> None:
        """Re-read `model_choices` from the current backend and repopulate the
        dropdown. Plugins call this after an event that changes the model list
        (e.g. an auth flow that unlocks more models)."""
        if self._current is None:
            return
        session = self._sessions.get(self._current)
        if session is None:
            return
        self._populate_models(session.backend)

    def _populate_models(self, backend: AgentBackend) -> None:
        self._model_combo.blockSignals(True)
        self._model_combo.clear()
        for label, value in backend.model_choices:
            self._model_combo.addItem(label, value)
        self._model_combo.blockSignals(False)

    def _populate_session_list(self, backend: AgentBackend) -> None:
        self._session_panel.setVisible(
            backend.supports_sessions and self._sessions_toggle.isChecked())
        self._sessions_toggle.setEnabled(backend.supports_sessions)
        if not backend.supports_sessions:
            self._session_panel.set_sessions([])
            return
        session = self._sessions.get(self._current)
        current_id = session.resume_id if session else None
        rows = ordered_sessions(backend.list_sessions(), AgentSessionMeta(),
                                backend.display_name)
        self._session_panel.set_sessions(rows, current_id)

    def _on_model_changed(self, index: int) -> None:
        if self._current is None:
            return
        value = self._model_combo.itemData(index)
        backend = self._sessions[self._current].backend
        self._spawn(backend.set_model(value))
        self._set_status(f"Model → {self._model_combo.currentText()}")

    def _on_writes_toggled(self, state: int) -> None:
        self._allow_writes = state == Qt.CheckState.Checked.value
        for session in self._sessions.values():
            session.backend.set_allow_writes(self._allow_writes)
        self._set_status(
            "Write actions enabled." if self._allow_writes else "Write actions disabled."
        )

    def _on_reset(self) -> None:
        if self._current is None:
            return
        session = self._sessions[self._current]
        session.messages = []
        session.resume_id = None
        self._purge_replay_tempdir(self._current)
        self._transcript.render_messages(session.messages)
        self._spawn(self._reset_backend(session))

    async def _reset_backend(self, session: _AgentSession) -> None:
        await session.backend.reset()
        self._populate_session_list(session.backend)

    def _on_session_selected(self, session_id: str) -> None:
        if self._current is None:
            return
        session = self._sessions[self._current]
        backend = session.backend
        if not backend.supports_sessions or session_id == session.resume_id:
            return
        session.resume_id = session_id
        self._purge_replay_tempdir(self._current)
        replay_dir = self._tempdir / self._current / "session_replay"
        session.messages = backend.load_session(session_id, replay_dir)
        self._transcript.render_messages(session.messages)
        self._transcript.flush_now()
        self._set_status(
            f"Resumed session {session_id[:8]} ({len(session.messages)} messages)")
        self._spawn(backend.resume(session_id))

    def _on_session_rename(self, session_id: str) -> None:
        session = self._sessions.get(self._current)
        if session is None:
            return
        from PySide6.QtWidgets import QInputDialog
        meta = AgentSessionMeta()
        current = meta.get(session.backend.display_name, session_id).name
        name, ok = QInputDialog.getText(self, "Rename session", "Name:", text=current)
        if ok:
            meta.set_name(session.backend.display_name, session_id, name.strip())
            self._populate_session_list(session.backend)

    def _on_session_pin(self, session_id: str) -> None:
        session = self._sessions.get(self._current)
        if session is None:
            return
        meta = AgentSessionMeta()
        cur = meta.get(session.backend.display_name, session_id).pinned
        meta.set_pinned(session.backend.display_name, session_id, not cur)
        self._populate_session_list(session.backend)

    def _on_sessions_toggled(self, checked: bool) -> None:
        self._session_panel.setVisible(
            checked and self._current_supports_sessions())
        with AgentChatSettings() as cfg:
            cfg.sessions_pane_visible = checked

    def _on_splitter_moved(self, *_args) -> None:
        sizes = self._h_splitter.sizes()
        if sizes and sizes[0] > 0:
            with AgentChatSettings() as cfg:
                cfg.sessions_pane_width = int(sizes[0])

    def _current_supports_sessions(self) -> bool:
        session = self._sessions.get(self._current)
        return bool(session and session.backend.supports_sessions)

    def _restore_pane_state(self) -> None:
        cfg = AgentChatSettings()
        self._sessions_toggle.blockSignals(True)
        self._sessions_toggle.setChecked(cfg.sessions_pane_visible)
        self._sessions_toggle.blockSignals(False)
        width = max(120, int(cfg.sessions_pane_width))
        self._h_splitter.setSizes([width, max(width, 600)])
        self._session_panel.setVisible(cfg.sessions_pane_visible)

    def _purge_replay_tempdir(self, backend_name: str) -> None:
        shutil.rmtree(self._tempdir / backend_name / "session_replay", ignore_errors=True)

    def _on_send(self) -> None:
        if self._current is None:
            return
        body, image_paths = self._input.take_payload()
        if not body and not image_paths:
            return
        session = self._sessions[self._current]
        user_blocks: list = []
        if body:
            user_blocks.append(TextBlock(text=body))
        for path in image_paths:
            user_blocks.append(ImageBlock(path=path))
        session.messages.append(ChatMessage(role="user", blocks=user_blocks, done=True))
        self._transcript.render_messages(session.messages)
        self._turn_task = asyncio.ensure_future(
            self._run_turn(session, body, image_paths)
        )

    async def _run_turn(
        self, session: _AgentSession, prompt: str, image_paths: list
    ) -> None:
        self._set_running(True)
        self._set_status("Thinking…")
        assistant = ChatMessage(role="assistant", blocks=[], done=False)
        session.messages.append(assistant)
        try:
            async for block in session.backend.ask(prompt, image_paths=image_paths):
                self._append_block(assistant, block)
                if self._is_current(session):
                    self._transcript.render_messages(session.messages)
            assistant.done = True
            if self._is_current(session):
                self._transcript.render_messages(session.messages)
                self._transcript.flush_now()
            self._set_status("Ready.")
        except asyncio.CancelledError:
            session.messages.append(
                ChatMessage(
                    role="error",
                    blocks=[TextBlock(text="(cancelled)")],
                    done=True,
                )
            )
            self._transcript.render_messages(session.messages)
            self._set_status("Cancelled.")
            raise
        except Exception as e:
            session.messages.append(
                ChatMessage(
                    role="error",
                    blocks=[TextBlock(text=f"{type(e).__name__}: {e}")],
                    done=True,
                )
            )
            self._transcript.render_messages(session.messages)
            self._set_status("Error. See history.")
        finally:
            self._set_running(False)
            self._turn_task = None

    def _is_current(self, session: _AgentSession) -> bool:
        return (
            self._current is not None
            and self._sessions.get(self._current) is session
        )

    def _on_stop(self) -> None:
        if self._current is None or self._turn_task is None:
            return
        backend = self._sessions[self._current].backend
        self._spawn(backend.cancel())

    def _set_running(self, running: bool) -> None:
        self._send_btn.setVisible(not running)
        self._stop_btn.setVisible(running)

    @staticmethod
    def _append_block(message: ChatMessage, block) -> None:
        if isinstance(block, (TextBlock, ThinkingBlock)):
            last = message.blocks[-1] if message.blocks else None
            if type(last) is type(block) and not last.complete:
                last.text += block.text
                last.complete = block.complete
            else:
                message.blocks.append(block)
        elif isinstance(block, ImageBlock):
            message.blocks.append(block)
        elif isinstance(block, ToolActivityBlock):
            # a result-only block (tool_use_id set, result filled) merges into the
            # matching tool call; otherwise it's a new call to append.
            if block.result is not None and block.tool_use_id:
                match = next(
                    (b for b in message.blocks
                     if isinstance(b, ToolActivityBlock)
                     and b.tool_use_id == block.tool_use_id), None)
                if match is not None:
                    match.result = block.result
                    return
            message.blocks.append(block)

    async def _confirm_tool_call(self, tool_name: str, tool_input: dict) -> bool:
        box = QMessageBox(self)
        box.setWindowTitle(f"{self._current}: tool call")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Allow <b>{tool_name}</b>?")
        preview = json.dumps(tool_input, indent=2, default=str)
        if len(preview) > 2000:
            preview = preview[:2000] + "…"
        box.setDetailedText(preview)
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        box.setDefaultButton(QMessageBox.StandardButton.No)
        future: asyncio.Future = asyncio.Future()

        def _on_finished(_btn):
            if not future.done():
                future.set_result(
                    box.standardButton(box.clickedButton())
                    == QMessageBox.StandardButton.Yes
                )
            box.deleteLater()

        box.finished.connect(_on_finished)
        box.open()
        return await future

    async def _ask_question(self, questions: list) -> dict:
        """Render the model's AskUserQuestion inline and await the user's answers."""
        from .chat.question_card import QuestionCard

        card = QuestionCard(questions, self)
        future: asyncio.Future = asyncio.Future()

        def _on_answered(answers: dict) -> None:
            if not future.done():
                future.set_result(answers)

        card.answered.connect(_on_answered)
        self.layout().addWidget(card)
        try:
            return await future
        finally:
            card.setParent(None)
            card.deleteLater()

    def _on_export(self) -> None:
        if self._current is None:
            return
        messages = self._sessions[self._current].messages
        if not messages:
            QMessageBox.information(self, "Export transcript", "Nothing to export yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export transcript", f"{self._current}.md", "Markdown (*.md)")
        if not path:
            return
        from .chat.export_md import transcript_to_markdown
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(transcript_to_markdown(messages, title=self._current))
        except OSError as e:
            QMessageBox.warning(self, "Export failed", str(e))

    def _init_tool_verbosity(self) -> None:
        level = AgentChatSettings().tool_verbosity
        self._verbosity_combo.blockSignals(True)
        self._verbosity_combo.setCurrentIndex(max(0, min(2, level - 1)))
        self._verbosity_combo.blockSignals(False)
        self._transcript.set_tool_verbosity(level)

    def _on_verbosity_changed(self, index: int) -> None:
        level = index + 1
        self._transcript.set_tool_verbosity(level)
        with AgentChatSettings() as s:
            s.tool_verbosity = level

    async def _refresh_completions(self) -> None:
        if self._current is None:
            return
        backend = self._sessions[self._current].backend
        try:
            cmds = await backend.list_slash_commands()
        except Exception:
            cmds = []
        self._input.set_completions(cmds)

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.ensure_future(coro)
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)
        return task

    def closeEvent(self, event):
        shutil.rmtree(self._tempdir, ignore_errors=True)
        super().closeEvent(event)


_DOCK_ATTR = "_sciqlop_agent_dock"
_UI_READY_ATTR = "_sciqlop_agent_ui_ready"
_DOCK_TITLE = "Agents"


def ensure_agent_dock(main_window) -> AgentChatDock:
    """Return the single shared agent chat dock, creating it and registering
    its whole UI (docked panel, toolbar button, Tools-menu entry) on first
    call.

    Backend plugins (sciqlop_claude, sciqlop_albert, sciqlop_copilot,
    sciqlop_opencode, …) must only ``register_agent_backend(...)`` and call
    this — they must NOT register any UI themselves. The chat UI is central
    and owned by core, so it appears exactly once no matter how many backends
    are installed.
    """
    dock = getattr(main_window, _DOCK_ATTR, None)
    if dock is None:
        dock = AgentChatDock(main_window=main_window)
        setattr(main_window, _DOCK_ATTR, dock)
    else:
        dock.refresh_backends()
    _register_agent_ui(main_window, dock)
    return dock


def _register_agent_ui(main_window, dock) -> None:
    """Register the shared chat UI exactly once, idempotently across repeated
    ``ensure_agent_dock`` calls from every installed backend plugin."""
    if getattr(main_window, _UI_READY_ATTR, False):
        return
    if _dock_agent_panel(main_window, dock) is None:
        return
    setattr(main_window, _UI_READY_ATTR, True)


def _dock_agent_panel(main_window, dock):
    """Add the chat panel as a left auto-hide side panel — wired exactly like
    the product tree, catalogs, settings and plot-properties panels (a left
    sidebar tab plus a View-menu toggle). The ``assistant`` window icon set on
    the panel becomes the tab icon."""
    dock_manager = getattr(main_window, "dock_manager", None)
    if dock_manager is None:
        return None
    main_window.add_side_pan(dock)
    return dock_manager.findDockWidget(_DOCK_TITLE)
