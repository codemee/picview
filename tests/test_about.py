import ctypes
import sys
from pathlib import Path

import pytest
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QLabel

from picview import __version__
from picview.about import LICENSE_ID, PROJECT_URL, license_text
from picview.system_menu import ABOUT_COMMAND, install_about_item, is_about_message
from test_tabs import browser


def test_about_shows_version_complete_license_and_links(browser):
    window, _ = browser
    window.show_about()
    dialog = window.about_dialog
    assert dialog.isVisible()
    assert dialog.windowTitle() == window.t["about"]
    assert LICENSE_ID in dialog.license_label.text()
    assert dialog.license_view.toPlainText() == Path("LICENSE").read_text(encoding="utf-8")
    assert dialog.license_view.isReadOnly()
    assert PROJECT_URL in dialog.links.text()
    assert "https://www.gnu.org/licenses/gpl-3.0.html" in dialog.links.text()
    assert any(f"v{__version__}" in label.text() for label in dialog.findChildren(QLabel))
    window.show_about()
    assert window.about_dialog is dialog
    dialog.close()
    assert window.about_dialog is None
    window.toggle_lang()
    window.show_about()
    assert window.about_dialog.windowTitle() == window.t["about"]
    window.about_dialog.close()


def test_license_text_reads_frozen_app_license(tmp_path, monkeypatch):
    directory = tmp_path / "licenses"
    directory.mkdir()
    (directory / "LICENSE").write_text("Bundled GPL license", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert license_text() == "Bundled GPL license"


def test_application_menu_about_role_opens_dialog_and_follows_language(browser):
    window, _ = browser
    window.setup_application_menu()
    action = window.about_action
    assert action.menuRole() == QAction.MenuRole.AboutRole
    assert action.text() == window.t["about"]
    window.setup_application_menu()
    assert window.application_menu.actions() == [action]
    action.trigger()
    assert window.about_dialog.isVisible()
    window.about_dialog.close()
    window.toggle_lang()
    assert action.text() == window.t["about"]
    action.trigger()
    assert window.about_dialog.windowTitle() == window.t["about"]
    window.about_dialog.close()


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS native application menu")
def test_macos_creates_native_about_entry_automatically(browser):
    window, _ = browser
    assert window.about_action is not None
    assert window.about_action.menuRole() == QAction.MenuRole.AboutRole


@pytest.mark.skipif(sys.platform != "win32", reason="Windows native message")
def test_only_own_about_system_command_is_handled():
    from ctypes import wintypes
    message = wintypes.MSG()
    message.hWnd = 123
    message.message = 0x0112
    message.wParam = ABOUT_COMMAND | 3
    pointer = ctypes.addressof(message)
    assert is_about_message(b"windows_generic_MSG", pointer, 123)
    assert not is_about_message(b"windows_generic_MSG", pointer, 456)
    message.wParam = 0xF060
    assert not is_about_message(b"windows_generic_MSG", pointer, 123)
    message.wParam = ABOUT_COMMAND
    message.message = 0x0111
    assert not is_about_message(b"windows_generic_MSG", pointer, 123)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows system menu")
def test_native_about_menu_install_and_language_update_do_not_duplicate_items():
    from ctypes import wintypes
    user = ctypes.WinDLL("user32", use_last_error=True)
    user.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p]
    user.CreateWindowExW.restype = wintypes.HWND
    user.GetSystemMenu.argtypes = [wintypes.HWND, wintypes.BOOL]
    user.GetSystemMenu.restype = wintypes.HMENU
    user.GetMenuItemCount.argtypes = [wintypes.HMENU]
    user.GetMenuItemCount.restype = ctypes.c_int
    user.GetMenuStringW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.LPWSTR, ctypes.c_int, wintypes.UINT]
    user.DestroyWindow.argtypes = [wintypes.HWND]
    window = user.CreateWindowExW(0, "STATIC", "PicView system menu test", 0x00CF0000,
                                  0, 0, 100, 100, None, None, None, None)
    assert window
    try:
        menu = user.GetSystemMenu(window, False)
        count = user.GetMenuItemCount(menu)
        for title in ("About PicView…", "關於 PicView…"):
            assert install_about_item(window, title)
            assert user.GetMenuItemCount(menu) == count + 2
            text = ctypes.create_unicode_buffer(100)
            user.GetMenuStringW(menu, ABOUT_COMMAND, text, len(text), 0)
            assert text.value == title
    finally:
        user.DestroyWindow(window)
