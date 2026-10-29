from __future__ import annotations

import sys
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from PySide6.QtCore import Qt, qVersion
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout

from . import __version__

PROJECT_URL = "https://github.com/codemee/picview"
LICENSE_ID = "GPL-3.0-or-later"


def license_text() -> str:
    if getattr(sys, "frozen", False):
        paths = [Path(sys._MEIPASS) / "licenses" / "LICENSE"]
    else:
        paths = [Path(__file__).resolve().parents[2] / "LICENSE"]
    for path in paths:
        try:
            return path.read_text(encoding="utf-8")
        except OSError:
            pass
    try:
        return distribution("picview").read_text("licenses/LICENSE") or ""
    except (PackageNotFoundError, OSError):
        return ""


class AboutDialog(QDialog):
    def __init__(self, labels, parent=None):
        super().__init__(parent)
        self.setWindowTitle(labels["about"])
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.resize(560, 480)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(10)
        header = QHBoxLayout()
        icon = QIcon(str(Path(__file__).parent / "assets" / "picview-icon.png"))
        self.setWindowIcon(icon)
        logo = QLabel()
        logo.setPixmap(icon.pixmap(48, 48))
        header.addWidget(logo)
        title = QLabel(f"PicView v{__version__}")
        font = title.font(); font.setPointSizeF(max(12, font.pointSizeF() * 1.4)); font.setBold(True)
        title.setFont(font)
        title.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        header.addWidget(title, 1)
        layout.addLayout(header)
        description = QLabel(labels["about_description"])
        description.setWordWrap(True)
        layout.addWidget(description)
        self.license_label = QLabel(f"{labels['about_license']}\n{LICENSE_ID}")
        self.license_label.setWordWrap(True)
        self.license_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self.license_label)
        style = QApplication.instance().style().objectName()
        layout.addWidget(QLabel(f"Qt {qVersion()} · {labels['about_style']}: {style}"))
        self.links = QLabel(
            f'<a href="{PROJECT_URL}">{labels["about_home"]}</a> · '
            f'<a href="{PROJECT_URL}/releases">{labels["about_releases"]}</a> · '
            f'<a href="https://www.gnu.org/licenses/gpl-3.0.html">GNU GPL</a>')
        self.links.setOpenExternalLinks(True)
        self.links.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        layout.addWidget(self.links)
        self.license_view = QPlainTextEdit()
        self.license_view.setReadOnly(True)
        self.license_view.setAccessibleName(labels["about_license_full"])
        self.license_view.setPlainText(license_text() or labels["about_license_missing"])
        layout.addWidget(self.license_view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.button(QDialogButtonBox.StandardButton.Close).setText(labels["file_close"])
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
