import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from picview.qt_app import ImagePane


CONFIRM_UNSAVED = ImagePane.confirm_unsaved


@pytest.fixture(autouse=True)
def allow_legacy_edit_navigation(monkeypatch):
    """Existing view tests navigate freely; dialog behavior has dedicated tests."""
    monkeypatch.setattr(ImagePane, "confirm_unsaved", lambda self: True)


@pytest.fixture
def real_unsaved_checks(monkeypatch, allow_legacy_edit_navigation):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(ImagePane, "confirm_unsaved", CONFIRM_UNSAVED)
    monkeypatch.setattr(ImagePane, "ask_unsaved_changes", lambda self: QMessageBox.StandardButton.Discard)
