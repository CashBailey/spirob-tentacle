"""Controller visualization panel."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont

from spirob.gui.styles.dark_theme import COLORS


class StickVisualizer(QWidget):
    """Visual representation of an analog stick."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)

        self._label = label
        self._x = 0.0
        self._y = 0.0

        self.setMinimumSize(80, 80)
        self.setMaximumSize(120, 120)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set_position(self, x: float, y: float):
        """Set stick position (-1 to 1)."""
        self._x = max(-1, min(1, x))
        self._y = max(-1, min(1, y))
        self.update()

    def paintEvent(self, event):
        """Paint the stick visualization."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        center_x = w / 2
        center_y = h / 2
        radius = min(w, h) / 2 - 8

        # Draw outer circle (boundary)
        painter.setPen(QPen(QColor(COLORS['overlay0']), 2))
        painter.setBrush(QBrush(QColor(COLORS['surface0'])))
        painter.drawEllipse(QRectF(center_x - radius, center_y - radius,
                                   radius * 2, radius * 2))

        # Draw crosshairs
        painter.setPen(QPen(QColor(COLORS['surface1']), 1))
        painter.drawLine(int(center_x - radius), int(center_y),
                         int(center_x + radius), int(center_y))
        painter.drawLine(int(center_x), int(center_y - radius),
                         int(center_x), int(center_y + radius))

        # Draw stick position
        stick_x = center_x + self._x * (radius - 8)
        stick_y = center_y - self._y * (radius - 8)  # Invert Y for display

        painter.setPen(QPen(QColor(COLORS['blue']), 2))
        painter.setBrush(QBrush(QColor(COLORS['blue'])))
        painter.drawEllipse(QRectF(stick_x - 8, stick_y - 8, 16, 16))

        # Draw label
        painter.setPen(QPen(QColor(COLORS['subtext0'])))
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        painter.drawText(4, h - 4, self._label)


class ButtonIndicator(QWidget):
    """Visual indicator for a controller button."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)

        self._label = label
        self._pressed = False

        self.setFixedSize(50, 24)

    def set_pressed(self, pressed: bool):
        """Set button pressed state."""
        self._pressed = pressed
        self.update()

    def paintEvent(self, event):
        """Paint the button indicator."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        if self._pressed:
            color = QColor(COLORS['blue'])
            text_color = QColor(COLORS['base'])
        else:
            color = QColor(COLORS['surface1'])
            text_color = QColor(COLORS['subtext0'])

        painter.setPen(QPen(QColor(COLORS['overlay0']), 1))
        painter.setBrush(QBrush(color))
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 4, 4)

        # Label
        painter.setPen(QPen(text_color))
        font = QFont()
        font.setPointSize(9)
        font.setBold(self._pressed)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._label)


class ControllerPanel(QWidget):
    """Panel showing controller state visualization."""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        group = QGroupBox("🎮 Controller")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        main_layout = QVBoxLayout(group)

        # Status label
        self._status_label = QLabel("No controller connected")
        self._status_label.setProperty("subheading", True)
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self._status_label)

        # Sticks row
        sticks_row = QHBoxLayout()
        sticks_row.addStretch()

        # Left stick
        left_layout = QVBoxLayout()
        self._left_stick = StickVisualizer("L")
        left_layout.addWidget(self._left_stick, alignment=Qt.AlignmentFlag.AlignCenter)
        left_labels = QLabel("U: ↑↓  V: ←→")
        left_labels.setProperty("subheading", True)
        left_labels.setAlignment(Qt.AlignmentFlag.AlignCenter)
        left_layout.addWidget(left_labels)
        sticks_row.addLayout(left_layout)

        sticks_row.addSpacing(20)

        # Right stick
        right_layout = QVBoxLayout()
        self._right_stick = StickVisualizer("R")
        right_layout.addWidget(self._right_stick, alignment=Qt.AlignmentFlag.AlignCenter)
        right_labels = QLabel("W: ↑↓")
        right_labels.setProperty("subheading", True)
        right_labels.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.addWidget(right_labels)
        sticks_row.addLayout(right_layout)

        sticks_row.addStretch()
        main_layout.addLayout(sticks_row)

        # Buttons row
        buttons_row = QHBoxLayout()
        buttons_row.addStretch()

        self._btn_lb = ButtonIndicator("LB")
        buttons_row.addWidget(self._btn_lb)

        self._btn_rb = ButtonIndicator("RB")
        buttons_row.addWidget(self._btn_rb)

        buttons_row.addSpacing(10)

        self._btn_y = ButtonIndicator("Y")
        buttons_row.addWidget(self._btn_y)

        self._btn_a = ButtonIndicator("A")
        buttons_row.addWidget(self._btn_a)

        self._btn_b = ButtonIndicator("B")
        buttons_row.addWidget(self._btn_b)

        buttons_row.addStretch()
        main_layout.addLayout(buttons_row)

        # Speed mode label
        self._speed_mode_label = QLabel("Speed: NORMAL")
        self._speed_mode_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self._speed_mode_label)

        # Main widget layout
        widget_layout = QVBoxLayout(self)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        widget_layout.addWidget(group)

    def set_connected(self, connected: bool, name: str = ""):
        """Set controller connection state."""
        if connected:
            self._status_label.setText(f"Connected: {name[:20]}")
            self._status_label.setStyleSheet(f"color: {COLORS['green']};")
        else:
            self._status_label.setText("No controller connected")
            self._status_label.setStyleSheet(f"color: {COLORS['subtext0']};")
            # Reset visualizations
            self._left_stick.set_position(0, 0)
            self._right_stick.set_position(0, 0)
            self._btn_lb.set_pressed(False)
            self._btn_rb.set_pressed(False)
            self._btn_y.set_pressed(False)
            self._btn_a.set_pressed(False)
            self._btn_b.set_pressed(False)

    def update_state(self, state):
        """Update panel with controller state.

        Args:
            state: ControllerState instance
        """
        # Update sticks
        self._left_stick.set_position(state.left_x, state.left_y)
        self._right_stick.set_position(state.right_x, state.right_y)

        # Update buttons
        self._btn_lb.set_pressed(state.btn_lb)
        self._btn_rb.set_pressed(state.btn_rb)
        self._btn_y.set_pressed(state.btn_y)
        self._btn_a.set_pressed(state.btn_a)
        self._btn_b.set_pressed(state.btn_b)

        # Update speed mode
        if state.btn_lb and state.btn_rb:
            mode = "MAX (360°/s)"
        elif state.btn_rb:
            mode = "FAST (180°/s)"
        elif state.btn_lb:
            mode = "SLOW (30°/s)"
        else:
            mode = "NORMAL (90°/s)"
        self._speed_mode_label.setText(f"Speed: {mode}")
