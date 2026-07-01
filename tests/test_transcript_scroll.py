"""TranscriptView auto-scrolls to the newest message after a flush.

The underlying bug (a stale scrollbar maximum right after setDocument) only
manifests on a live on-screen widget where layout is deferred — the offscreen Qt
platform lays out synchronously, so a plain behavioural test cannot reproduce the
*failure*. `test_scroll_to_end_schedules_deferred_scroll` instead pins the fix's
mechanism (the scroll is re-issued on the next event-loop cycle), which fails
against the old immediate-only implementation and passes with the fix.
"""


def _view(qtbot):
    from SciQLop.components.agents.chat.view import TranscriptView
    v = TranscriptView()
    v.resize(400, 200)
    qtbot.addWidget(v)
    v.show()
    return v


def _assistant(i):
    from SciQLop.components.agents.chat.view import ChatMessage, TextBlock
    return ChatMessage(role="assistant",
                       blocks=[TextBlock(text=f"line {i} of the transcript\n", complete=True)],
                       done=True)


def test_scrolls_to_bottom_on_new_output(qtbot):
    v = _view(qtbot)
    v.render_messages([_assistant(i) for i in range(60)])
    v.flush_now()
    qtbot.wait(50)  # let the deferred (singleShot) scroll fire
    bar = v.verticalScrollBar()
    assert bar.maximum() > 0             # content taller than the viewport
    assert bar.value() == bar.maximum()  # parked at the newest message


def test_scroll_to_end_schedules_deferred_scroll(qtbot, monkeypatch):
    """The fix must re-scroll on the next event-loop cycle (singleShot(0, ...)),
    because the scrollbar maximum is stale immediately after setDocument on a live
    widget. The old code scrolled only once, inline — this test fails against it."""
    import SciQLop.components.agents.chat.view as vw
    v = _view(qtbot)  # constructed with the real QTimer

    calls = []

    class _FakeTimer:  # only intercepts the deferred-scroll scheduling in _flush
        @staticmethod
        def singleShot(ms, fn):
            calls.append((ms, fn))

    monkeypatch.setattr(vw, "QTimer", _FakeTimer)
    v.render_messages([_assistant(i) for i in range(60)])
    v.flush_now()

    assert calls, "no deferred scroll was scheduled"
    assert calls[0][0] == 0
    calls[0][1]()  # run the deferred scroll
    bar = v.verticalScrollBar()
    assert bar.value() == bar.maximum() and bar.maximum() > 0
