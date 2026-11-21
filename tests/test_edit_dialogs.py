import pytest
import sys
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from test_tabs import browser


@pytest.mark.parametrize("language,expected", [
    ("zh", ["儲存", "不儲存", "取消"]), ("en", ["Save", "Discard", "Cancel"]),
])
def test_unsaved_dialog_buttons_follow_app_language(browser, monkeypatch, language, expected):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    while window.lang != language: window.toggle_lang()
    def inspect(dialog):
        standards = [QMessageBox.StandardButton.Save, QMessageBox.StandardButton.Discard, QMessageBox.StandardButton.Cancel]
        assert [dialog.button(button).text() for button in standards] == expected
        assert dialog.defaultButton() is dialog.button(QMessageBox.StandardButton.Save)
        assert dialog.escapeButton() is dialog.button(QMessageBox.StandardButton.Cancel)
        assert dialog.textFormat() == Qt.TextFormat.PlainText
        assert pane.path.name in dialog.text()
        # macOS message boxes omit window titles by platform convention.
        if sys.platform != "darwin":
            assert dialog.windowTitle() == window.t["unsaved_title"]
        return QMessageBox.StandardButton.Cancel
    monkeypatch.setattr(QMessageBox, "exec", inspect)
    assert pane.ask_unsaved_changes() == QMessageBox.StandardButton.Cancel


@pytest.mark.parametrize("language", ["zh", "en"])
@pytest.mark.parametrize("standards,keys", [
    ([QMessageBox.StandardButton.Yes, QMessageBox.StandardButton.No], ["dialog_yes", "dialog_no"]),
    ([QMessageBox.StandardButton.Ok, QMessageBox.StandardButton.Cancel], ["dialog_ok", "dialog_cancel"]),
    ([QMessageBox.StandardButton.Ok], ["dialog_ok"]),
])
def test_save_dialog_buttons_follow_app_language(browser, monkeypatch, language, standards, keys):
    window, folders = browser
    pane = window.open_folder(folders[0]).image
    while window.lang != language: window.toggle_lang()
    def inspect(dialog):
        assert [dialog.button(button).text() for button in standards] == [window.t[key] for key in keys]
        return standards[-1]
    monkeypatch.setattr(QMessageBox, "exec", inspect)
    buttons = QMessageBox.StandardButton.NoButton
    for standard in standards: buttons |= standard
    assert pane.message_box(QMessageBox.Icon.Warning, "test", "test", buttons, standards[-1]) == standards[-1]
