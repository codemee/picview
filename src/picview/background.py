"""Background color grid with the same keyboard behavior in every view."""
from PySide6.QtCore import QEvent, QPoint, Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QGridLayout, QMenu, QPushButton, QWidget, QWidgetAction


class BackgroundColorMenu(QMenu):
    def __init__(self, parent, colors, choose):
        super().__init__(parent)
        self.colors = colors
        self.modes = list(colors)
        self.panel = QWidget(self)
        grid = QGridLayout(self.panel)
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setSpacing(4)
        self.choices = {}
        self.column = 0
        for index, mode in enumerate(self.modes):
            button = QPushButton(self.panel)
            button.setCheckable(True)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.clicked.connect(lambda checked=False, mode=mode: (choose(mode), self.hide()))
            button.installEventFilter(self)
            self.choices[mode] = button
            if index == 0:
                button.setMinimumHeight(34)
                grid.addWidget(button, 0, 0, 1, 4)
            else:
                button.setFixedSize(40, 30)
                grid.addWidget(button, 1 + (index - 1) // 4, (index - 1) % 4)
        action = QWidgetAction(self)
        action.setDefaultWidget(self.panel)
        self.addAction(action)
        self.installEventFilter(self)
        self.panel.installEventFilter(self)

    def configure(self, labels, palette, current):
        self.panel.setStyleSheet(f"background:{palette['card']};")
        for mode, button in self.choices.items():
            swatch = self.colors[mode] or palette["pane"]
            text = "#ffffff" if QColor(swatch).lightness() < 128 else "#172a31"
            name = labels[f"bg_{mode}"]
            button.setText(name if mode == "default" else "")
            button.setAccessibleName(name)
            button.setToolTip(name if mode == "default" else f"{name} ({swatch})")
            button.setChecked(mode == current)
            button.setStyleSheet(
                f"QPushButton{{background:{swatch};color:{text};border:1px solid {palette['edge']};border-radius:4px;padding:3px 6px;}}"
                f"QPushButton:hover,QPushButton:checked{{border:2px solid {palette['focus']};padding:2px 5px;}}"
                f"QPushButton:focus{{border:2px dashed {text};padding:2px 5px;}}")

    def open_at(self, anchor, current, *, above=False):
        index = self.modes.index(current)
        self.column = (index - 1) % 4 if index else 0
        self.popup(anchor.mapToGlobal(QPoint(0, -self.sizeHint().height() if above else anchor.height())))
        QTimer.singleShot(0, self, lambda: self.choices[current].setFocus(Qt.FocusReason.PopupFocusReason) if self.isVisible() else None)

    def eventFilter(self, watched, event):
        keys = (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
                Qt.Key.Key_Home, Qt.Key.Key_End, Qt.Key.Key_Tab, Qt.Key.Key_Backtab,
                Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space, Qt.Key.Key_Escape)
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() in keys:
            event.accept()
            if event.type() == QEvent.Type.ShortcutOverride: return True
            focused = QApplication.focusWidget()
            index = next((i for i, mode in enumerate(self.modes) if self.choices[mode] is focused), 0)
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.hide()
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self.choices[self.modes[index]].click()
            else:
                target = index
                if key == Qt.Key.Key_Left: target = max(0, index - 1)
                elif key == Qt.Key.Key_Right: target = min(len(self.modes) - 1, index + 1)
                elif key == Qt.Key.Key_Up: target = max(0, index - 4)
                elif key == Qt.Key.Key_Down:
                    target = 1 + self.column if index == 0 else index + 4 if index + 4 < len(self.modes) else index
                elif key == Qt.Key.Key_Home: target = 0
                elif key == Qt.Key.Key_End: target = len(self.modes) - 1
                elif key in (Qt.Key.Key_Tab, Qt.Key.Key_Backtab):
                    backwards = key == Qt.Key.Key_Backtab or event.modifiers() & Qt.KeyboardModifier.ShiftModifier
                    target = (index + (-1 if backwards else 1)) % len(self.modes)
                if target: self.column = (target - 1) % 4
                self.choices[self.modes[target]].setFocus(Qt.FocusReason.TabFocusReason)
            return True
        return super().eventFilter(watched, event)
