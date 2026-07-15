from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QListWidget, QListWidgetItem, QPushButton

from SciQLop.components.onboarding.backend.registry import all_tours
from SciQLop.components.onboarding.backend.settings import OnboardingSettings


class TourPicker(QDialog):
    """Lists every registered tour (built-in and plugin-contributed) and
    starts whichever one the user picks. Non-modal by design: it must not
    block the app's event loop, and its "Start" action just hands off to
    main_window._start_tour and closes."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.setWindowTitle("Take a Tour")
        self._main_window = main_window
        self._items_by_tour_id: dict[str, QListWidgetItem] = {}

        layout = QVBoxLayout(self)
        self._list = QListWidget(self)
        layout.addWidget(self._list)
        self._list.itemDoubleClicked.connect(lambda _item: self._start_selected())

        start_button = QPushButton("Start", self)
        start_button.clicked.connect(self._start_selected)
        layout.addWidget(start_button)

        self._populate()

    def _populate(self) -> None:
        completed = OnboardingSettings().completed_tours
        for tour in all_tours():
            suffix = " (Completed)" if completed.get(tour.id, False) else ""
            item = QListWidgetItem(f"{tour.title}{suffix} — {tour.description}")
            item.setData(Qt.ItemDataRole.UserRole, tour.id)
            self._list.addItem(item)
            self._items_by_tour_id[tour.id] = item

    def _start_selected(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        tour_id = item.data(Qt.ItemDataRole.UserRole)
        self.close()
        self._main_window._start_tour(tour_id)
