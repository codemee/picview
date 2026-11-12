from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtTest import QTest

from test_tabs import browser, wait_until
from test_compare import add


def test_status_tracks_image_dimensions_and_notifications(browser):
    window, folders = browser
    image = folders[0] / "details.png"
    Image.new("RGB", (123, 87), "red").save(image)
    page = window.open_folder(folders[0], image)
    wait_until(lambda: "123 × 87 px" in window.image_status.details)
    assert "details.png" in window.image_status.details
    assert "PNG" in window.image_status.details
    assert " B" in window.image_status.details
    assert str(image) in window.image_status.toolTip()
    assert window.notification_bar.isVisible()
    window.notification_bar.showMessage("notice")
    window.notification_bar.clearMessage()
    assert window.image_status.isVisible()
    page.thumbs.select(page.files[-1])
    assert page.image.path.name in window.image_status.details


def test_comparison_status_tracks_selected_pane_and_last_image(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    second.thumbs.select(second.files[1])
    add(window, first, second)
    assert window.notification_bar.parentWidget() is window.comparison_area
    window.focus_compare_page(first)
    assert first.image.path.name in window.image_status.details
    assert str(first.folder) in window.image_status.toolTip()
    window.focus_compare_page(second)
    assert second.image.path.name in window.image_status.details
    window.remove_comparison_page(first)
    assert window.notification_bar.parentWidget() is second.image
    assert second.image.path.name in window.image_status.details


def test_status_updates_on_reload_and_clears_for_empty_folder(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    path = page.image.path
    Image.new("RGB", (65, 43), "green").save(path)
    page.refresh_folder()
    wait_until(lambda: "65 × 43 px" in window.image_status.details)
    empty = folders[0].parent / "empty"
    empty.mkdir()
    window.open_folder(empty)
    assert window.image_status.details == ""


def test_status_background_and_text_stay_inside_pane_margins(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    for width in (1100, 260):
        window.resize(width, 500)
        QTest.qWait(50)
        bar, label = window.notification_bar, window.image_status
        assert bar.parentWidget() is page.image
        assert bar.x() == page.image.layout().contentsMargins().left()
        assert bar.width() == page.image.width() - 20
        assert bar.rect().contains(label.geometry())
        assert label.height() >= label.fontMetrics().height()
        assert bar.y() + bar.height() <= page.image.height() - 8
