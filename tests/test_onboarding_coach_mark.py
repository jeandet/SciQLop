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
