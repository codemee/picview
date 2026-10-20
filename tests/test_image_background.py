from PIL import Image
from PySide6.QtCore import QPoint
from PySide6.QtGui import QColor

from picview.qt_app import PALETTE, PicView
from picview.settings import IMAGE_BACKGROUND_COLORS, normalize_tab_state
from test_tabs import browser, wait_until


def test_background_panel_changes_transparent_image_without_modifying_file(browser):
    window, folders = browser
    path = folders[0] / "image0.png"
    Image.new("RGBA", (120, 80), (255, 0, 0, 0)).save(path)
    original = path.read_bytes()
    pane = window.open_folder(folders[0]).image
    window.resize(1100, 780)
    pane.background_button.click()
    wait_until(pane.background_menu.isVisible)
    assert pane.background_choices["default"].isChecked()
    assert len(pane.background_choices) == len(IMAGE_BACKGROUND_COLORS)
    for mode in ("white", "black", "blue"):
        pane.background_choices[mode].click()
        assert not pane.background_menu.isVisible()
        assert pane.background_choices[mode].isChecked()
        assert sum(button.isChecked() for button in pane.background_choices.values()) == 1
        assert pane.background_color() == IMAGE_BACKGROUND_COLORS[mode]
        viewport = pane.scroll.viewport()
        assert viewport.grab().toImage().pixelColor(2, 2) == QColor(pane.background_color())
        point = pane.label.mapTo(viewport, QPoint(10, 10))
        assert viewport.grab().toImage().pixelColor(point) == QColor(pane.background_color())
    assert path.read_bytes() == original
    assert pane.frames[0][0].getpixel((0, 0))[3] == 0
    pane.open_full()
    assert pane.background_color() in pane.full_window.centralWidget().styleSheet()
    pane.set_background("black")
    assert "#000000" in pane.full_window.centralWidget().styleSheet()
    pane.open_full()


def test_default_follows_theme_and_custom_background_stays_fixed(browser):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    window.toggle_theme()
    assert pane.background_color() == PALETTE["pane"]
    pane.set_background("white")
    window.toggle_theme()
    assert pane.background_color() == "#ffffff"
    assert "#ffffff" in pane.scroll.viewport().styleSheet()
    assert PALETTE["pane"] in window.thumbs.scroll.viewport().styleSheet()
    pane.set_background("default")
    assert pane.background_color() == PALETTE["pane"]
    window.toggle_lang()
    assert pane.background_choices["default"].text() == window.t["bg_default"]
    assert pane.background_button.toolTip() == window.t["background"]
    window.toggle_theme()  # Restore the application palette for other tests.


def test_comparison_backgrounds_duplicate_and_restore_independently(browser):
    window, folders = browser
    first = window.open_folder(folders[0])
    first.image.set_background("black")
    window.set_compare(True)
    second = window.duplicate_page(first)
    assert second.image.background_mode == "black"
    second.image.set_background("white")
    assert first.image.background_mode == "black"
    assert first.snapshot()["image_background"] == "black"
    assert second.snapshot()["image_background"] == "white"
    state = normalize_tab_state(second.snapshot())
    restored = window.open_folder(folders[1], state=state)
    assert restored.image.background_mode == "white"
    window.close_tab(window.tabs.indexOf(second))
    window.reopen_closed_tab()
    assert window.image.background_mode == "white"
    expected = [page.image.background_mode for page in window.pages()]
    window.close()
    fresh = PicView()
    try:
        assert [page.image.background_mode for page in fresh.pages()] == expected
    finally:
        fresh.close()
        fresh.deleteLater()


def test_background_panel_is_available_in_overflow(browser):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    window.resize(260, 220)
    controller = pane.toolbar_overflow
    wait_until(lambda: pane.background_button in controller.overflowed)
    controller.populate_menu()
    action = next(a for a in controller.menu.actions() if a.text() == window.t["background"])
    action.trigger()
    wait_until(pane.background_menu.isVisible)
    pane.background_choices["gray"].click()
    assert pane.background_color() == "#808080"


def test_invalid_saved_background_uses_theme_default():
    for invalid in (None, [], {}, "#ffffff", "invalid"):
        state = normalize_tab_state({"folder": "C:/Pictures", "image_background": invalid})
        assert state["image_background"] == "default"
