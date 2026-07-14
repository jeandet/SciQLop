from PySide6.QtWidgets import QPushButton, QMainWindow
from PySide6.QtCore import Qt


def test_show_for_positions_bubble_near_target(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    target = QPushButton("target", host)
    target.setGeometry(100, 100, 40, 20)
    host.resize(800, 600)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body text")

    assert mark.isVisible()
    assert mark.geometry() == host.geometry() or mark.size() == host.size()


def test_esc_emits_skip_requested(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    target = QPushButton("target", host)
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body")

    with qtbot.waitSignal(mark.skip_requested, timeout=1000):
        qtbot.keyClick(mark, Qt.Key.Key_Escape)


def test_dismiss_button_emits_dismiss_clicked(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    target = QPushButton("target", host)
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body")

    with qtbot.waitSignal(mark.dismiss_clicked, timeout=1000):
        mark._dismiss_button.click()


def test_show_dismiss_false_hides_dismiss_button(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    target = QPushButton("target", host)
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body", show_dismiss=False)

    assert not mark._dismiss_button.isVisible()


def test_show_for_with_rect_highlights_subregion(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark
    from PySide6.QtCore import QRect

    host = QMainWindow()
    target = QPushButton("target", host)
    target.setGeometry(0, 0, 200, 200)
    host.resize(800, 600)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    sub_rect = QRect(10, 10, 20, 20)
    mark.show_for(target, "Title", "Body", rect=sub_rect)

    assert mark._target_rect().size() == sub_rect.size()


def test_target_destroyed_emits_signal_and_hides(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    target = QPushButton("target", host)
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body")

    with qtbot.waitSignal(mark.target_destroyed, timeout=1000):
        target.deleteLater()

    assert not mark.isVisible()


def test_cutout_rect_is_padded_target_rect(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark
    from PySide6.QtCore import QRect

    host = QMainWindow()
    target = QPushButton("target", host)
    target.setGeometry(100, 100, 40, 20)
    host.resize(800, 600)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body")

    assert mark._cutout_rect() == mark._target_rect().adjusted(-4, -4, 4, 4)


def test_cutout_rect_follows_partial_highlight_rect(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark
    from PySide6.QtCore import QRect

    host = QMainWindow()
    target = QPushButton("target", host)
    target.setGeometry(0, 0, 200, 200)
    host.resize(800, 600)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    sub_rect = QRect(10, 10, 20, 20)
    mark.show_for(target, "Title", "Body", rect=sub_rect)

    assert mark._cutout_rect() == mark._target_rect().adjusted(-4, -4, 4, 4)


def test_paint_draws_a_highlight_ring_around_the_cutout(qtbot):
    """Real pixel check, not just geometry: the ring must actually be
    painted in the palette's highlight color, not just computed."""
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark
    from PySide6.QtGui import QImage

    host = QMainWindow()
    target = QPushButton("target", host)
    target.setGeometry(300, 300, 40, 20)
    host.resize(800, 600)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body")

    image = QImage(mark.size(), QImage.Format.Format_ARGB32)
    image.fill(0)
    mark.render(image)

    cutout = mark._cutout_rect()
    # The ring is drawn 1px outside cutout_rect (see paintEvent) so its
    # full width stays clear of the click-through mask -- sample there,
    # not on cutout_rect's own boundary.
    ring_point = (cutout.left() - 1, cutout.center().y())
    highlight = mark.palette().highlight().color()

    pixel = image.pixelColor(*ring_point)
    assert (pixel.red(), pixel.green(), pixel.blue()) == \
        (highlight.red(), highlight.green(), highlight.blue())


def test_clicking_the_spotlighted_target_reaches_the_target(qtbot):
    """Real mouse clicks are hit-tested by position (QWidget.childAt), unlike
    calling .click() directly on the target which bypasses the overlay
    entirely. The coach mark dims everything except a spotlight cutout
    around the target -- a click inside that cutout must actually reach the
    target, not the coach mark sitting on top of it."""
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    target = QPushButton("target", host)
    target.setGeometry(100, 100, 40, 20)
    host.resize(800, 600)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body")

    center = target.mapTo(host, target.rect().center())
    assert host.childAt(center) is target


def test_clicking_outside_the_spotlight_still_hits_the_coach_mark(qtbot):
    """The dimmed area (outside the spotlight) must still block interaction
    with whatever's behind it -- only the cutout should pass clicks
    through."""
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    target = QPushButton("target", host)
    target.setGeometry(100, 100, 40, 20)
    decoy = QPushButton("decoy", host)
    decoy.setGeometry(400, 400, 40, 20)
    host.resize(800, 600)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(target, "Title", "Body")

    decoy_center = decoy.mapTo(host, decoy.rect().center())
    assert host.childAt(decoy_center) is mark


def test_stale_target_destroyed_does_not_abort_current_step(qtbot):
    from SciQLop.components.onboarding.ui.coach_mark import CoachMark

    host = QMainWindow()
    first_target = QPushButton("first", host)
    second_target = QPushButton("second", host)
    host.resize(400, 300)
    qtbot.addWidget(host)
    host.show()

    mark = CoachMark(host)
    qtbot.addWidget(mark)
    mark.show_for(first_target, "Title", "Body")
    mark.show_for(second_target, "Title 2", "Body 2")

    target_destroyed_spy = []
    mark.target_destroyed.connect(lambda: target_destroyed_spy.append(True))

    first_target.deleteLater()
    qtbot.wait(50)

    assert target_destroyed_spy == []
    assert mark._target is second_target
    assert mark.isVisible()
