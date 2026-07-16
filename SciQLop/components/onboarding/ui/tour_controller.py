import shiboken6
from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from SciQLop.components.onboarding.backend.tour import Tour, TourStep
from SciQLop.components.onboarding.backend.registry import get_tour
from SciQLop.components.onboarding.backend.settings import OnboardingSettings
from SciQLop.components.onboarding.ui.coach_mark import CoachMark
from SciQLop.components.sciqlop_logging import getLogger

log = getLogger(__name__)

_POLL_INTERVAL_S = 0.25


def _log_safely(message: str, level: str = "info") -> None:
    """Logging must never crash the app. The module-level logger's Qt
    signal can itself already be torn down if this fires from deep inside
    an interpreter/QApplication shutdown cascade -- swallow that one,
    narrow failure mode rather than let a diagnostic log call bring down
    shutdown."""
    try:
        getattr(log, level)(message)
    except RuntimeError:
        pass


def _normalize_completion(result):
    """A step's completion callable returns a bare Signal, a
    (Signal, predicate) tuple, or None. Normalize to (Signal, predicate)
    so the controller has one shape to connect."""
    if result is None:
        return None
    if isinstance(result, tuple):
        return result
    return result, (lambda *args: True)


def _store_completion_args(context: dict, step_id: str, args: tuple) -> None:
    if len(args) == 0:
        context[step_id] = True
    elif len(args) == 1:
        context[step_id] = args[0]
    else:
        context[step_id] = args


class TourController(QObject):
    """Walks a Tour's steps against a live SciQLopMainWindow, one CoachMark
    at a time, advancing on each step's completion signal or on the coach
    mark's own dismiss/skip actions. Carries no knowledge of which specific
    tour it's running -- every branch is driven by the step's own resolver/
    completion callables.

    Every step's completion connection is torn down as soon as that step is
    left (advance, abort, or replaced by a new step) -- main_window and its
    dock widgets/panels outlive any single tour run, so a stale connection
    left dangling past its step would keep firing into a finished
    controller on a later, unrelated replay.
    """

    _SHORT_TIMEOUT_FOR_TESTS: float | None = None

    def __init__(self, main_window, tour: Tour):
        super().__init__(main_window)
        self._main_window = main_window
        self._tour = tour
        self._coach_mark = CoachMark(main_window)
        self._coach_mark.skip_requested.connect(self._on_skip)
        self._coach_mark.dismiss_clicked.connect(self._on_dismiss)
        self._coach_mark.target_destroyed.connect(self._on_target_gone)
        self._step_index = 0
        self._poll_timer: QTimer | None = None
        self._poll_deadline_s = 0.0
        self._context: dict = {}
        self._active_signal = None
        self._active_slot = None
        self._finished = False

    @property
    def is_finished(self) -> bool:
        return self._finished

    def _current_step(self) -> TourStep:
        return self._tour.steps[self._step_index]

    def start(self) -> None:
        self._step_index = 0
        self._enter_current_step()

    def abort(self, message: str | None = None) -> None:
        print(f"[ONBOARDING DIAG] abort(): step_index={self._step_index}, "
              f"message={message!r}", flush=True)
        self._stop_polling()
        self._disconnect_active_completion()
        self._finish()
        if message:
            _log_safely(message)

    def _finish(self) -> None:
        """Mark the tour as over and detach the controller from CoachMark's
        own signals. Idempotent: safe to call from multiple exit paths."""
        if self._finished:
            return
        self._finished = True
        self._detach_coach_mark_signals()
        self._coach_mark.hide()
        with OnboardingSettings() as s:
            s.completed_tours[self._tour.id] = True
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
        return step.resolver(self._main_window, self._context)

    def _enter_current_step(self) -> None:
        print(f"[ONBOARDING DIAG] _enter_current_step(): step_index={self._step_index}, "
              f"finished={self._finished}", flush=True)
        if self._finished:
            # _advance() defers here via QTimer.singleShot(0, ...); if the
            # tour was aborted/finished in the meantime (e.g. the user hit
            # Skip during that one event-loop turn), there is no next step
            # to enter.
            return
        step = self._current_step()
        target = self._resolve_target(step)
        print(f"[ONBOARDING DIAG]   step_id={step.step_id!r}, target={target!r}", flush=True)

        if target is None and not step.poll:
            QApplication.processEvents()
            target = self._resolve_target(step)

        if step.poll and target is None:
            self._start_polling(step)
            return

        if target is None:
            _log_safely(f"Onboarding step {step.step_id!r}: target not found, aborting tour",
                        level="warning")
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
        if isinstance(target, tuple):
            widget, local_rect = target
        else:
            widget, local_rect = target, None

        show_dismiss = step.completion is None
        self._coach_mark.show_for(widget, step.title, step.body,
                                  rect=local_rect, show_dismiss=show_dismiss,
                                  block_input=step.block_input)

        self._disconnect_active_completion()
        raw = step.completion(self._main_window, self._context) if step.completion else None
        normalized = _normalize_completion(raw)
        print(f"[ONBOARDING DIAG] _show_step({step.step_id!r}): completion normalized to "
              f"{normalized!r}", flush=True)
        if normalized is not None:
            signal, predicate = normalized
            self._active_signal = signal

            def _slot(*args, _step=step, _predicate=predicate):
                predicate_result = _predicate(*args)
                print(f"[ONBOARDING DIAG] completion slot fired for {_step.step_id!r}: "
                      f"args={args!r}, predicate={predicate_result!r}", flush=True)
                if predicate_result:
                    _store_completion_args(self._context, _step.step_id, args)
                    self._advance()

            self._active_slot = _slot
            self._active_signal.connect(self._active_slot)
        else:
            self._active_signal = None
            self._active_slot = None

    def _on_dismiss(self) -> None:
        self._advance()

    def _on_skip(self) -> None:
        print("[ONBOARDING DIAG] _on_skip(): skip_requested fired", flush=True)
        self.abort()

    def _on_target_gone(self) -> None:
        print(f"[ONBOARDING DIAG] _on_target_gone(): step_index={self._step_index}, "
              f"step_id={self._current_step().step_id!r}", flush=True)
        # A step's target can be destroyed by something entirely outside
        # this component's control. Advancing to the next step instead of
        # aborting was tried (commit 9062b444) and reverted: it can leave
        # the coach mark's dimmed overlay stuck on screen with input still
        # blocked, because _on_target_gone fires synchronously from deep
        # inside the target's own QObject destructor
        # (target.destroyed -> CoachMark._on_target_destroyed ->
        # target_destroyed.emit() -> here) -- exactly the reentrant
        # context docs/qt-lifetime-patterns.md warns is unsafe for
        # further Qt work, deferred or not. abort() is the safe,
        # well-understood fallback; the actual fix for the observed
        # instability is not retargeting THIS handler but not targeting
        # volatile widgets in the first place (see
        # tour_getting_started.py's overlay_vs_new_subplot step, which
        # now targets the stable panel instead of the plot that was
        # observed dying).
        _log_safely("Onboarding tour target was destroyed mid-step; aborting")
        self.abort()

    def _advance(self) -> None:
        print(f"[ONBOARDING DIAG] _advance(): from step_index={self._step_index}", flush=True)
        self._disconnect_active_completion()
        self._coach_mark.hide()
        self._step_index += 1
        if self._step_index >= len(self._tour.steps):
            print("[ONBOARDING DIAG]   -> last step, finishing tour", flush=True)
            self._finish()
            return
        print(f"[ONBOARDING DIAG]   -> scheduling deferred entry into "
              f"step_index={self._step_index}", flush=True)
        # A completion signal can fire from deep inside another
        # framework's own nested/reentrant call stack -- a native
        # drag-and-drop's QDrag::exec() runs its own local event loop,
        # and the drop handler that creates the real plot and emits
        # plot_added executes from within it. Entering the next step
        # (resolving its target, showing/raising/focusing a CoachMark)
        # synchronously in that same call stack risks fighting with
        # whatever cleanup the nested loop still has to do once it
        # returns. Defer to a real event-loop turn instead -- the same
        # reentrancy guard mainwindow.py's _on_dock_area_created already
        # uses for dockAreaCreated firing from inside CDockAreaWidget's
        # constructor.
        QTimer.singleShot(0, self._enter_current_step)


def run_tour(main_window, tour_id: str) -> TourController | None:
    tour = get_tour(tour_id)
    if tour is None:
        _log_safely(f"Onboarding: unknown tour {tour_id!r}, not starting", level="warning")
        return None
    controller = TourController(main_window, tour)
    controller.start()
    return controller
