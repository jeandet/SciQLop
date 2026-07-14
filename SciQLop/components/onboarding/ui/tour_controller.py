import shiboken6
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from SciQLop.components.onboarding.backend.tour import TOUR_STEPS, TourStep
from SciQLop.components.onboarding.backend.targets import RESOLVERS
from SciQLop.components.onboarding.backend.settings import OnboardingSettings
from SciQLop.components.onboarding.ui.coach_mark import CoachMark
from SciQLop.components.sciqlop_logging import getLogger

log = getLogger(__name__)

_POLL_INTERVAL_S = 0.25


class TourController(QObject):
    """Walks TOUR_STEPS against a live SciQLopMainWindow, one CoachMark at a
    time, advancing on each step's completion signal or on the coach mark's
    own dismiss/skip actions.

    Every step's completion connection is torn down as soon as that step is
    left (advance, abort, or replaced by a new step) — main_window and its
    dock widgets/panels outlive any single tour run, so a stale connection
    left dangling past its step would keep firing into a finished
    controller on a later, unrelated replay (see
    test_replaying_after_completion_does_not_double_fire_on_stale_connections).
    """

    _SHORT_TIMEOUT_FOR_TESTS: float | None = None

    def __init__(self, main_window):
        super().__init__(main_window)
        self._main_window = main_window
        self._coach_mark = CoachMark(main_window)
        self._coach_mark.skip_requested.connect(self._on_skip)
        self._coach_mark.dismiss_clicked.connect(self._on_dismiss)
        self._coach_mark.target_destroyed.connect(self._on_target_gone)
        self._step_index = 0
        self._poll_timer: QTimer | None = None
        self._poll_deadline_s = 0.0
        self._panel_from_step_1 = None
        self._active_signal = None
        self._active_slot = None
        self._finished = False

    @property
    def is_finished(self) -> bool:
        return self._finished

    def _current_step(self) -> TourStep:
        return TOUR_STEPS[self._step_index]

    def start(self) -> None:
        self._step_index = 0
        self._enter_current_step()

    def abort(self, message: str | None = None) -> None:
        self._stop_polling()
        self._disconnect_active_completion()
        self._finish()
        if message:
            log.info(message)

    def _finish(self) -> None:
        """Mark the tour as over and detach the controller from CoachMark's
        own signals — main_window and its child widgets (including this
        controller's CoachMark) outlive any single tour run, so a finished
        controller left listening for target_destroyed/skip_requested/
        dismiss_clicked would still react to unrelated later widget teardown
        (e.g. main_window.close() destroying whatever this controller's last
        target happened to be), which is exactly the trap this method closes
        off. Idempotent: safe to call from multiple exit paths."""
        if self._finished:
            return
        self._finished = True
        self._detach_coach_mark_signals()
        self._coach_mark.hide()
        with OnboardingSettings() as s:
            s.tour_completed = True
        self._dispose()

    def _dispose(self) -> None:
        coach_mark = self._coach_mark

        def _cleanup():
            if shiboken6.isValid(coach_mark):
                coach_mark.dispose()
                coach_mark.deleteLater()
            if shiboken6.isValid(self):
                self.deleteLater()

        QTimer.singleShot(0, _cleanup)

    def _detach_coach_mark_signals(self) -> None:
        for signal, slot in (
                (self._coach_mark.skip_requested, self._on_skip),
                (self._coach_mark.dismiss_clicked, self._on_dismiss),
                (self._coach_mark.target_destroyed, self._on_target_gone)):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                pass

    def _effective_timeout(self, step: TourStep) -> float | None:
        if self._SHORT_TIMEOUT_FOR_TESTS is not None:
            return self._SHORT_TIMEOUT_FOR_TESTS
        return step.timeout_s

    def _resolve_target(self, step: TourStep):
        resolver = RESOLVERS[step.resolver_id]
        if step.step_id == "overlay_vs_new_subplot":
            return resolver(self._main_window, self._panel_from_step_1)
        return resolver(self._main_window)

    def _enter_current_step(self) -> None:
        step = self._current_step()
        target = self._resolve_target(step)

        if target is None and not step.poll:
            # Non-poll targets (e.g. the add-panel button) are core mainwindow
            # widgets that are created via a deferred QTimer.singleShot(0, ...)
            # right after their dock area is set up — on a just-constructed
            # main_window, entering a step before that tick has run would
            # otherwise abort the whole tour on a pure startup race. Flushing
            # pending events once gives that deferred creation a chance to run
            # before we decide the target is really missing.
            QApplication.processEvents()
            target = self._resolve_target(step)

        if step.poll and target is None:
            self._start_polling(step)
            return

        if target is None:
            log.warning(f"Onboarding step {step.step_id!r}: target not found, aborting tour")
            self.abort()
            return

        self._show_step(step, target)

    def _start_polling(self, step: TourStep) -> None:
        import time
        self._poll_deadline_s = time.monotonic() + (self._effective_timeout(step) or 0.0)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(int(_POLL_INTERVAL_S * 1000))
        self._poll_timer.timeout.connect(lambda: self._poll_step(step))
        self._poll_timer.start()

    def _poll_step(self, step: TourStep) -> None:
        import time
        target = self._resolve_target(step)
        if target is not None:
            self._stop_polling()
            self._show_step(step, target)
            return
        if time.monotonic() >= self._poll_deadline_s:
            self._stop_polling()
            self.abort(step.timeout_message)

    def _stop_polling(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer.deleteLater()
            self._poll_timer = None

    def _disconnect_active_completion(self) -> None:
        if self._active_signal is not None and self._active_slot is not None:
            try:
                self._active_signal.disconnect(self._active_slot)
            except (RuntimeError, TypeError):
                pass
        self._active_signal = None
        self._active_slot = None

    def _show_step(self, step: TourStep, target) -> None:
        if step.step_id == "plot_product":
            widget, local_rect = target
        else:
            widget, local_rect = target, None

        show_dismiss = step.completion_signal_id is None
        self._coach_mark.show_for(widget, step.title, step.body,
                                  rect=local_rect, show_dismiss=show_dismiss)

        self._disconnect_active_completion()
        if step.completion_signal_id == "panel_created":
            self._active_signal = self._main_window.panel_added
            self._active_slot = self._on_panel_created
        elif step.completion_signal_id == "products_visible":
            dw = self._main_window.dock_manager.findDockWidget("Products")
            self._active_signal = dw.visibilityChanged if dw is not None else None
            self._active_slot = self._on_products_visible
        elif step.completion_signal_id == "plot_added":
            self._active_signal = self._panel_from_step_1.plot_added
            self._active_slot = self._on_plot_added
        else:
            self._active_signal = None
            self._active_slot = None

        if self._active_signal is not None:
            self._active_signal.connect(self._active_slot)

    def _on_panel_created(self, panel) -> None:
        self._panel_from_step_1 = panel
        self._advance()

    def _on_products_visible(self, visible: bool) -> None:
        if visible:
            self._advance()

    def _on_plot_added(self, *_args) -> None:
        self._advance()

    def _on_dismiss(self) -> None:
        self._advance()

    def _on_skip(self) -> None:
        self.abort()

    def _on_target_gone(self) -> None:
        log.info("Onboarding tour target was destroyed mid-step; aborting")
        self.abort()

    def _advance(self) -> None:
        self._disconnect_active_completion()
        self._coach_mark.hide()
        self._step_index += 1
        if self._step_index >= len(TOUR_STEPS):
            self._finish()
            return
        self._enter_current_step()


def run_tour(main_window) -> TourController:
    controller = TourController(main_window)
    controller.start()
    return controller
