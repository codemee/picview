from PySide6.QtCore import QPoint, Qt

from picview.settings import normalize_tab_state
from test_tabs import browser


def test_docking_each_pane_at_each_edge_preserves_order_and_comparison_direction(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.tabs.setCurrentWidget(first)
    window.set_compare(True)
    window.check_compare_page(second, True)
    for kind, edge, expected_orientation, expected_first in (
        ("thumb", "left", Qt.Orientation.Horizontal, first.thumbs),
        ("image", "top", Qt.Orientation.Vertical, first.image_slot),
        ("thumb", "right", Qt.Orientation.Horizontal, first.image_slot),
        ("image", "bottom", Qt.Orientation.Vertical, first.thumbs),
    ):
        first.dock_pane(kind, edge)
        assert first.split.orientation() == expected_orientation
        assert first.split.widget(0) is expected_first
        assert window.comparison_area.split.orientation() != expected_orientation
        assert first.thumbs.isVisible() and first.image_slot.isVisible()
        assert first.snapshot()["thumbnail_first"] == (expected_first is first.thumbs)


def test_docked_order_survives_tab_restore_and_edge_detection(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    page.dock_pane("image", "left")
    state = normalize_tab_state(page.snapshot())
    assert state["orientation"] == "horizontal" and not state["thumbnail_first"]
    copy = window.open_folder(folders[0], state=state, restoring=True)
    assert copy.split.orientation() == Qt.Orientation.Horizontal
    assert copy.split.widget(0) is copy.image_slot
    assert page.dock_edge(QPoint(2, page.height() // 2)) == "left"
    assert page.dock_edge(QPoint(page.width() - 3, page.height() // 2)) == "right"
    assert page.dock_edge(QPoint(page.width() // 2, 2)) == "top"
    assert page.dock_edge(QPoint(page.width() // 2, 0)) == "top"
    # macOS's offscreen native menu can occupy space above the central widget.
    outside_window = page.mapFrom(window, QPoint(window.width() // 2, -10))
    assert page.dock_edge(outside_window) is None
    assert page.dock_edge(QPoint(page.width() // 2, page.height() - 3)) == "bottom"
    assert page.dock_edge(QPoint(page.width() // 2, page.height() // 2)) is None
