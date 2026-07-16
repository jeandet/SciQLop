from .fixtures import *
import pytest


def _make_step(step_id, resolver, completion=None, **kwargs):
    from SciQLop.components.onboarding.backend.tour import TourStep
    return TourStep(
        step_id=step_id, title=f"{step_id} title", body=f"{step_id} body",
        resolver=resolver, completion=completion, **kwargs,
    )


def _make_tour(tour_id, steps):
    from SciQLop.components.onboarding.backend.tour import Tour
    return Tour(id=tour_id, title=tour_id, description="test tour", steps=steps)


def test_start_shows_coach_mark_for_first_step(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    tour = _make_tour("t1", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        assert controller._current_step().step_id == "only"
    finally:
        controller.abort()


def test_dismiss_only_step_advances_on_got_it(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    tour = _make_tour("t2", [
        _make_step("first", lambda mw, ctx: main_window.productTree),
        _make_step("second", lambda mw, ctx: main_window.productTree),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        controller._coach_mark.dismiss_clicked.emit()
        qtbot.waitUntil(lambda: controller._current_step().step_id == "second", timeout=1000)
    finally:
        controller.abort()


def test_completion_signal_advances_and_stores_single_arg_in_context(main_window, qtbot):
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    class _Emitter(QObject):
        fired = Signal(str)

    emitter = _Emitter()
    tour = _make_tour("t3", [
        _make_step("wait_for_it", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: emitter.fired),
        _make_step("after", lambda mw, ctx: main_window.productTree),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        emitter.fired.emit("payload")
        qtbot.waitUntil(lambda: controller._current_step().step_id == "after", timeout=1000)
        assert controller._context["wait_for_it"] == "payload"
    finally:
        controller.abort()


def test_completion_predicate_filters_signal_args(main_window, qtbot):
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    class _Emitter(QObject):
        fired = Signal(bool)

    emitter = _Emitter()
    tour = _make_tour("t4", [
        _make_step("wait_true", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: (emitter.fired, lambda v: v)),
        _make_step("after", lambda mw, ctx: main_window.productTree),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        emitter.fired.emit(False)
        qtbot.wait(100)
        assert controller._current_step().step_id == "wait_true"

        emitter.fired.emit(True)
        qtbot.waitUntil(lambda: controller._current_step().step_id == "after", timeout=1000)
    finally:
        controller.abort()


def test_advance_defers_next_step_entry_to_the_next_event_loop_turn(main_window, qtbot):
    """Completion signals can fire from deep inside another framework's own
    nested/reentrant call stack -- a native drag-and-drop's QDrag::exec()
    runs its own local event loop, and the drop handler that creates the
    real plot and emits plot_added executes from within it. Showing a new
    CoachMark synchronously in that same call stack risks fighting with
    whatever cleanup that nested loop still has to do once it returns.
    _advance() must defer entering the next step to a real event-loop
    turn, not do it synchronously inside the completion slot -- matching
    the same reentrancy guard mainwindow.py's _on_dock_area_created
    already uses for dockAreaCreated firing from inside
    CDockAreaWidget's constructor."""
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    class _Emitter(QObject):
        fired = Signal()

    emitter = _Emitter()
    tour = _make_tour("t_defer", [
        _make_step("first", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: emitter.fired),
        _make_step("second", lambda mw, ctx: main_window.productTree),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        emitter.fired.emit()
        assert not controller._coach_mark.isVisible(), (
            "the next step's coach mark must not be shown synchronously "
            "inside the completion slot's own call stack -- _advance() "
            "hides the coach mark immediately but must defer showing it "
            "again for the next step to a real event-loop turn")
        qtbot.waitUntil(lambda: controller._current_step().step_id == "second", timeout=1000)
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
    finally:
        controller.abort()


def test_tuple_target_unpacks_widget_and_rect(main_window, qtbot):
    from PySide6.QtCore import QRect
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    rect = QRect(1, 2, 3, 4)
    tour = _make_tour("t5", [
        _make_step("with_rect", lambda mw, ctx: (main_window.productTree, rect)),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        assert controller._coach_mark._target_local_rect == rect
    finally:
        controller.abort()


def test_later_step_resolver_reads_earlier_step_context(main_window, qtbot):
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    class _Emitter(QObject):
        fired = Signal(str)

    emitter = _Emitter()

    def _second_resolver(mw, ctx):
        assert ctx["first"] == "stored"
        return main_window.productTree

    tour = _make_tour("t6", [
        _make_step("first", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: (emitter.fired, lambda *a: True)),
        _make_step("second", _second_resolver),
    ])
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)
        emitter.fired.emit("stored")
        qtbot.waitUntil(lambda: controller._current_step().step_id == "second", timeout=1000)
    finally:
        controller.abort()


def test_poll_step_times_out_and_aborts_with_message(main_window, qtbot):
    import shiboken6
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    tour = _make_tour("t7", [
        _make_step("never_resolves", lambda mw, ctx: None,
                   poll=True, timeout_message="gave up"),
    ])
    controller = TourController(main_window, tour)
    controller._SHORT_TIMEOUT_FOR_TESTS = 0.2
    controller.start()
    qtbot.waitUntil(lambda: OnboardingSettings().completed_tours.get("t7") is True, timeout=2000)
    # qtbot.waitUntil pumps the event loop, which may already have run the
    # deferred cleanup (_dispose()'s QTimer.singleShot(0, ...)) that deletes
    # the coach mark's C++ object -- isVisible() on an already-deleted
    # Shiboken object raises, so "not visible" must also accept "gone".
    coach_mark = controller._coach_mark
    assert not shiboken6.isValid(coach_mark) or not coach_mark.isVisible()


def test_skip_sets_completed_and_hides_overlay(main_window, qtbot):
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    tour = _make_tour("t8", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

    controller._coach_mark.skip_requested.emit()

    assert not controller._coach_mark.isVisible()
    assert OnboardingSettings().completed_tours.get("t8") is True


def test_replaying_after_completion_does_not_double_fire_on_stale_connections(main_window, qtbot):
    """Regression guard: a finished/aborted controller must disconnect its
    per-step completion signal, or a second (replay) controller's own state
    gets corrupted by the first controller's dead handler still reacting to
    the shared signal both controllers' 'first' step is wired to."""
    from PySide6.QtCore import QObject, Signal
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    class _Emitter(QObject):
        fired = Signal(object)

    emitter = _Emitter()
    tour = _make_tour("t9", [
        _make_step("first", lambda mw, ctx: main_window.productTree,
                   completion=lambda mw, ctx: emitter.fired),
        _make_step("second", lambda mw, ctx: main_window.productTree),
    ])

    first = TourController(main_window, tour)
    first.start()
    qtbot.waitUntil(lambda: first._coach_mark.isVisible(), timeout=1000)
    first.abort()
    assert first.is_finished is True

    second = TourController(main_window, tour)
    second.start()
    try:
        qtbot.waitUntil(lambda: second._coach_mark.isVisible(), timeout=1000)
        emitter.fired.emit(object())
        qtbot.waitUntil(lambda: second._current_step().step_id == "second", timeout=1000)
        assert second._step_index == 1
    finally:
        second.abort()


def test_finish_sets_is_finished_and_disposes_coach_mark_and_controller(main_window, qtbot):
    import shiboken6
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    tour = _make_tour("t10", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

    coach_mark = controller._coach_mark
    assert controller.is_finished is False

    controller.abort()

    assert controller.is_finished is True
    qtbot.waitUntil(lambda: not shiboken6.isValid(coach_mark), timeout=1000)
    qtbot.waitUntil(lambda: not shiboken6.isValid(controller), timeout=1000)


def test_deferred_cleanup_tolerates_coach_mark_and_controller_already_destroyed(
        main_window, qtbot, monkeypatch):
    import shiboken6
    from SciQLop.components.onboarding.ui import tour_controller as tc_mod
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    captured = {}

    def capture_single_shot(_delay, fn):
        captured["fn"] = fn

    monkeypatch.setattr(tc_mod.QTimer, "singleShot", capture_single_shot)

    tour = _make_tour("t11", [_make_step("only", lambda mw, ctx: main_window.productTree)])
    controller = TourController(main_window, tour)
    controller.start()
    qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=1000)

    coach_mark = controller._coach_mark
    controller.abort()
    assert "fn" in captured

    coach_mark.deleteLater()
    controller.deleteLater()
    qtbot.waitUntil(lambda: not shiboken6.isValid(coach_mark), timeout=1000)
    qtbot.waitUntil(lambda: not shiboken6.isValid(controller), timeout=1000)

    captured["fn"]()  # must not raise RuntimeError: Internal C++ object already deleted


def test_target_destroyed_mid_step_aborts_tour_without_crash(qapp, sciqlop_resources, qtbot):
    """A step's target can be destroyed by something entirely outside the
    tour's control. Advancing to the next step instead of aborting was
    tried and reverted: it can leave the coach mark's dimmed overlay
    stuck on screen with input still blocked, because this fires
    synchronously from deep inside the target's own QObject destructor --
    exactly the reentrant context docs/qt-lifetime-patterns.md warns is
    unsafe for further Qt work. abort() is the safe, well-understood
    fallback. Uses a disposable, per-test main window (not the shared
    session-scoped `main_window` fixture) because this test destroys a
    widget that fixture is expected to keep alive for every other test in
    the suite."""
    import shiboken6
    from SciQLop.core.ui.mainwindow import SciQLopMainWindow
    from SciQLop.components.onboarding.ui.tour_controller import TourController
    from SciQLop.components.onboarding.backend.settings import OnboardingSettings

    with OnboardingSettings() as s:
        s.completed_tours = {}

    mw = SciQLopMainWindow()
    mw.show()
    try:
        target = mw.productTree
        tour = _make_tour("t12", [_make_step("only", lambda mw_, ctx: target)])
        controller = TourController(mw, tour)
        controller.start()
        qtbot.waitUntil(lambda: controller._coach_mark.isVisible(), timeout=2000)

        target.deleteLater()
        qtbot.waitUntil(lambda: OnboardingSettings().completed_tours.get("t12") is True, timeout=2000)
        # Same event-loop-pumped-past-deferred-cleanup race as
        # test_poll_step_times_out_and_aborts_with_message -- see comment there.
        coach_mark = controller._coach_mark
        assert not shiboken6.isValid(coach_mark) or not coach_mark.isVisible()
    finally:
        mw.close()


def test_real_getting_started_tour_advances_on_real_panel_creation(main_window, qtbot):
    """One true end-to-end smoke test against the real, registered
    Getting Started tour -- proves the ported content actually works
    through the generalized controller, not just fabricated test tours."""
    from SciQLop.components.onboarding.backend import registry
    from SciQLop.components.onboarding.backend.targets import resolve_add_panel_button
    from SciQLop.components.onboarding.ui.tour_controller import TourController

    registry.register_builtin_tours()
    tour = registry.get_tour("getting_started")
    controller = TourController(main_window, tour)
    controller.start()
    try:
        qtbot.waitUntil(lambda: resolve_add_panel_button(main_window, {}) is not None, timeout=1000)
        resolve_add_panel_button(main_window, {}).click()
        qtbot.waitUntil(
            lambda: controller._current_step().step_id == "open_products", timeout=2000)
        assert controller._context["create_panel"] is not None
    finally:
        controller.abort()
        for name in main_window.plot_panels():
            main_window.remove_panel(main_window.plot_panel(name))
