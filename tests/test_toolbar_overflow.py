import pytest
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QToolButton
from PIL import Image

from test_tabs import browser, wait_until


def action_for(controller, control):
    controller.populate_menu()
    return controller.panel_controls[control]


def trigger_control(controller, control):
    if control in controller.overflowed: action_for(controller, control).click()
    else: control.click()


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
        if controller is window.toolbar_overflow:
            assert window.settings_button.isVisible() or controller.more_button.isVisible()
        else:
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
        assert controller.more_button.isVisible() == bool(controller.extra_controls)
        assert all(not widget.isHidden() for widget in controller.hide_order
                   if widget.property("toolbar_available") is not False)


def test_main_menu_keeps_theme_and_language_controls_live(browser):
    window, folders = browser
    page = window.open_folder(folders[0])
    window.resize(260, 350)
    QTest.qWait(100)
    controller = window.toolbar_overflow
    assert window.theme_button.isHidden() and window.language_button.isHidden()
    window.populate_settings_menu()
    assert window.modified_button in controller.panel_controls
    old_mode = window.theme_mode
    controller.panel_controls[window.theme_button].click()
    assert window.theme_mode != old_mode
    old_language = window.language_mode
    window.populate_settings_menu()
    controller.panel_controls[window.language_button].click()
    assert window.language_mode != old_language
    assert window.current_tab() is page
    assert window.width() == 260


def test_settings_ellipsis_repaints_with_theme(browser):
    from picview.qt_app import IconButton
    window, _ = browser
    for _ in range(3):
        window.toggle_theme()
        expected = IconButton("more", "")
        actual_image = window.settings_button.icon().pixmap(20, 20).toImage()
        expected_image = expected.icon().pixmap(20, 20).toImage()
        assert actual_image == expected_image
        expected.deleteLater()


def test_overlay_zoom_and_thumbnail_size_editors(browser):
    window, folders = browser
    window.open_folder(folders[0])
    window.resize(260, 350)
    QTest.qWait(100)
    image = window.image
    image.toolbar_overflow.populate_menu()
    assert image.slider not in image.toolbar_overflow.panel_controls
    image.slider.setValue(1750)
    assert image.zoom == 1.75
    assert not image.fit_to_pane
    thumbs = window.thumbs
    thumbs.toolbar_overflow.populate_menu()
    assert thumbs.slider not in thumbs.toolbar_overflow.panel_controls
    thumbs.slider.setValue(200)
    assert thumbs.size == 200


def test_thumbnail_has_one_ellipsis_and_live_hover_slider(browser):
    from picview.qt_app import IconButton
    window, folders = browser
    window.open_folder(folders[0])
    window.resize(260, 350)
    QTest.qWait(100)
    thumbs = window.thumbs
    assert window.toolbar_overflow is thumbs.toolbar_overflow
    ellipses = [button for button in thumbs.findChildren(IconButton)
                if button.kind == "more" and button.isVisible()]
    assert ellipses == [window.settings_button]
    window.settings_menu.popup(window.settings_button.mapToGlobal(window.settings_button.rect().bottomLeft()))
    wait_until(window.settings_menu.isVisible)
    assert thumbs.slider not in thumbs.toolbar_overflow.panel_controls
    window.settings_menu.hide()
    QTest.qWait(50)
    window.resize(1100, 780)
    QTest.qWait(50)
    QTest.mouseMove(window.image.scroll.viewport(), QPoint(10, 10))
    QTest.mouseMove(thumbs.scroll.viewport(), QPoint(20, 20))
    QTest.mouseMove(window.image.scroll.viewport(), QPoint(30, 30))
    wait_until(lambda: not thumbs.size_panel.isVisible())
    QTest.mouseMove(thumbs.scroll.viewport(), QPoint(10, 10))
    wait_until(thumbs.size_panel.isVisible)
    slider = thumbs.slider
    value_button = thumbs.size_label
    assert slider.isVisible() and value_button.isVisible()
    assert not value_button.spin.isVisible()
    assert not value_button.reset_button.isVisible()
    assert not value_button.editor_menu.isVisible()
    slider.setValue(180)
    assert thumbs.size == 180 and value_button.text() == "180px"
    thumbs.slider.setValue(190)
    assert slider.value() == 190 and value_button.text() == "190px"
    value_button.click()
    wait_until(value_button.editor_menu.isVisible)
    assert value_button.spin.isVisible() and value_button.reset_button.isVisible()
    value_button.spin.setValue(200)
    value_button.apply_value()
    assert thumbs.size == 200 and slider.value() == 200
    value_button.click()
    value_button.reset_button.click()
    assert thumbs.size == 140 and slider.value() == 140
    QTest.mouseMove(window.image.scroll.viewport(), QPoint(10, 10))
    wait_until(lambda: not thumbs.size_panel.isVisible())


def test_zoom_panel_stays_in_viewport_and_out_of_toolbar_overflow(browser):
    window, folders = browser
    window.open_folder(folders[0])
    for width in (1100, 800, 650, 420, 260):
        window.resize(width, 400)
        QTest.qWait(50)
        pane = window.image
        thumbs = window.thumbs
        assert thumbs.slider not in thumbs.toolbar_overflow.widgets
        assert thumbs.size_label not in thumbs.toolbar_overflow.widgets
        assert thumbs.scroll.viewport().rect().contains(thumbs.size_panel.geometry())
        assert pane.slider not in pane.toolbar_overflow.widgets
        assert pane.zoom_label not in pane.toolbar_overflow.widgets
        assert pane.scroll.viewport().rect().contains(pane.zoom_panel.geometry())


def test_comparison_uses_one_shared_zoom_panel_and_restores_single_pane_controls(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.set_compare(True)
    window.check_compare_page(first, True)
    window.resize(1100, 780)
    QTest.qWait(100)
    window.focus_compare_page(first)
    area = window.comparison_area
    QTest.mouseMove(first.image.scroll.viewport(), QPoint(15, 15))
    wait_until(lambda: area.zoom_panel is first.image.zoom_panel and area.zoom_panel.isVisible())
    assert area.zoom_panel.parentWidget() is area
    assert area.rect().contains(area.zoom_panel.geometry())
    assert area.zoom_panel.geometry().right() == area.width() - 9
    assert area.zoom_panel.geometry().bottom() == area.height() - 9
    assert not second.image.zoom_panel.isVisible()
    QTest.mouseMove(first.image.slider, first.image.slider.rect().center())
    assert first.image.zoom_panel.isVisible()
    first.image.slider.setValue(1750)
    assert first.image.zoom == 1.75
    assert second.image.zoom != 1.75
    window.focus_compare_page(second)
    QTest.mouseMove(second.image.scroll.viewport(), QPoint(15, 15))
    wait_until(lambda: area.zoom_panel is second.image.zoom_panel and area.zoom_panel.isVisible())
    assert area.zoom_panel.parentWidget() is area
    assert not first.image.zoom_panel.isVisible()
    window.set_sync(True)
    area.zoom_panel.slider.setValue(1500)
    assert first.image.zoom == second.image.zoom == 1.5
    QTest.mouseMove(window.thumbs.scroll.viewport(), QPoint(15, 15))
    wait_until(lambda: not area.zoom_panel.isVisible())
    window.set_compare(False)
    assert area.zoom_panel is None
    for page in (first, second):
        assert page.image.zoom_panel.parentWidget() is page.image.scroll.viewport()
        assert page.image.zoom_panel.available


def test_leaving_comparison_restores_hover_panel_without_moving_mouse(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    second = window.open_folder(folders[1])
    window.set_compare(True)
    window.check_compare_page(first, True)
    window.focus_compare_page(second)
    window.resize(1100, 780)
    QTest.qWait(100)
    QTest.mouseMove(second.image.scroll.viewport(), QPoint(20, 20))
    wait_until(lambda: window.comparison_area.zoom_panel.isVisible())
    window.set_compare(False)
    pane = window.image
    wait_until(pane.zoom_panel.isVisible)
    QTest.mouseMove(window.thumbs.scroll.viewport(), QPoint(20, 20))
    wait_until(lambda: not pane.zoom_panel.isVisible())
    assert window.thumbs.size_panel.isVisible()


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
    trigger_control(controller, first.image.rotate_b)
    assert first.image.rotation == 90 and second.image.rotation == 0
    trigger_control(controller, first.image.full)
    assert window.compare_full_window is not None
    first.image.open_full()
    window.focus_compare_page(second)
    QTest.qWait(50)
    trigger_control(second.image.toolbar_overflow, second.image.mh)
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
    action.click()
    assert page.image.fit_to_pane != before
    assert action_for(controller, page.image.fit_b).isChecked() == page.image.fit_to_pane
