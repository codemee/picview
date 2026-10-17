import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolButton
from PIL import Image

from test_tabs import browser, wait_until


def action_for(controller, control):
    controller.populate_menu()
    return next(action for action in controller.menu.actions() if action.text().startswith(control.toolTip()))


@pytest.mark.parametrize("orientation", [Qt.Orientation.Vertical, Qt.Orientation.Horizontal])
def test_narrow_and_short_window_overflows_and_restores(browser, orientation):
    window, folders = browser
    Image.new("RGB", (1800, 1200), "blue").save(folders[0] / "image0.png")
    window.open_folder(folders[0])
    window.set_orientation(orientation)
    window.resize(260, 220)
    QTest.qWait(150)
    assert window.width() == 260 and window.height() == 220
    controllers = (window.toolbar_overflow, window.thumbs.toolbar_overflow, window.image.toolbar_overflow)
    for controller in controllers:
        assert controller.overflowed and controller.more_button.isVisible()
        assert controller.more_button.geometry().right() < controller.host.width()
        controller.populate_menu()
        assert controller.menu.actions()
        for widget in controller.widgets:
            if isinstance(widget, QToolButton) and not widget.isHidden():
                assert widget.geometry().left() >= 0
                assert widget.geometry().right() < controller.host.width()
    window.resize(1100, 780)
    window.set_orientation(Qt.Orientation.Vertical)
    QTest.qWait(150)
    for controller in controllers:
        assert not controller.overflowed
        assert controller.more_button.isHidden()
        assert all(not widget.isHidden() for widget in controller.hide_order)


def test_main_menu_keeps_theme_and_language_controls_live(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    window.resize(260, 350)
    QTest.qWait(100)
    controller = window.toolbar_overflow
    assert window.theme_button in controller.overflowed
    old_mode = window.theme_mode
    action_for(controller, window.theme_button).trigger()
    assert window.theme_mode != old_mode
    old_language = window.language_mode
    action_for(controller, window.language_button).trigger()
    assert window.language_mode != old_language
    assert window.current_tab() is page
    assert window.width() == 260


def test_hidden_zoom_and_thumbnail_size_editors(browser):
    window, folders = browser
    window.open_folder(folders[0])
    window.resize(260, 350)
    QTest.qWait(100)
    image = window.image
    action_for(image.toolbar_overflow, image.zoom_label).trigger()
    wait_until(image.zoom_label.editor_menu.isVisible)
    image.zoom_label.spin.setValue(175)
    image.zoom_label.apply_value()
    assert image.zoom == 1.75
    assert not image.fit_to_pane
    thumbs = window.thumbs
    action_for(thumbs.toolbar_overflow, thumbs.size_label).trigger()
    wait_until(thumbs.size_label.editor_menu.isVisible)
    thumbs.size_label.spin.setValue(200)
    thumbs.size_label.apply_value()
    assert thumbs.size == 200


def test_compared_pane_actions_still_target_own_image(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.set_compare(True)
    window.check_compare_page(first, True)
    window.set_orientation(Qt.Orientation.Horizontal)
    window.resize(260, 350)
    QTest.qWait(150)
    window.focus_compare_page(first)
    QTest.qWait(50)
    controller = first.image.toolbar_overflow
    assert first.image.rotate_b in controller.overflowed
    action_for(controller, first.image.rotate_b).trigger()
    assert first.image.rotation == 90 and second.image.rotation == 0
    action_for(controller, first.image.full).trigger()
    assert first.image.full_window is not None
    first.image.open_full()
    window.focus_compare_page(second)
    QTest.qWait(50)
    action_for(second.image.toolbar_overflow, second.image.mh).trigger()
    assert second.image.fh and not first.image.fh
    window.set_compare(False)
    window.resize(1100, 780)
    window.set_orientation(Qt.Orientation.Vertical)
    QTest.qWait(100)
    assert not window.image.toolbar_overflow.overflowed


def test_overflow_preserves_fit_check_state_in_smallest_pane(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    window.set_orientation(Qt.Orientation.Horizontal)
    window.resize(260, 220)
    QTest.qWait(100)
    page.split.setSizes([200, 54])
    QTest.qWait(100)
    controller = page.image.toolbar_overflow
    assert page.image.fit_b in controller.overflowed
    assert controller.more_button.geometry().right() < controller.host.width()
    action = action_for(controller, page.image.fit_b)
    assert action.isCheckable() and action.isChecked() == page.image.fit_to_pane
    before = page.image.fit_to_pane
    action.trigger()
    assert page.image.fit_to_pane != before
    assert action_for(controller, page.image.fit_b).isChecked() == page.image.fit_to_pane
