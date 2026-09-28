"""Emergency stop button widget."""

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QVBoxLayout, QMessageBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, QTimer, Qt
from PyQt6.QtGui import QFont

from spirob.gui.styles.dark_theme import COLORS


class EStopButton(QWidget):
    """Large emergency stop button with visual feedback.

    Shows a prominent red button that triggers E-stop when clicked.
    Pulses when E-stop is active. Click again to reset (with confirmation).
    """

    estop_triggered = pyqtSignal()
    estop_reset = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._is_active = False
        self._pulse_state = False

        self._setup_ui()
        self._setup_animation()

    def _setup_ui(self):
        """Set up the UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create large E-stop button
        self._button = QPushButton("🛑 E-STOP")
        self._button.setMinimumSize(120, 80)
        self._button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._button.clicked.connect(self._on_click)

        # Set font
        font = QFont()
        font.setPointSize(16)
        font.setBold(True)
        self._button.setFont(font)

        # Initial style (inactive)
        self._update_style()

        layout.addWidget(self._button)

    def _setup_animation(self):
        """Set up the pulsing animation timer."""
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._pulse)
        self._pulse_timer.setInterval(500)  # 500ms pulse

    def _update_style(self):
        """Update button style based on state."""
        if self._is_active:
            # Active E-stop: bright red with pulse
            if self._pulse_state:
                bg_color = COLORS['red']
                border_color = COLORS['maroon']
            else:
                bg_color = COLORS['maroon']
                border_color = COLORS['red']

            self._button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {bg_color};
                    color: {COLORS['base']};
                    border: 4px solid {border_color};
                    border-radius: 12px;
                    font-size: 18px;
                    font-weight: bold;
                }}
            """)
            self._button.setText("⚠️ RESET E-STOP")
        else:
            # Inactive: ready to trigger
            self._button.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLORS['surface1']};
                    color: {COLORS['red']};
                    border: 3px solid {COLORS['red']};
                    border-radius: 12px;
                    font-size: 18px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {COLORS['red']};
                    color: {COLORS['base']};
                }}
                QPushButton:pressed {{
                    background-color: {COLORS['maroon']};
                }}
            """)
            self._button.setText("🛑 E-STOP")

    def _pulse(self):
        """Toggle pulse state for animation."""
        self._pulse_state = not self._pulse_state
        self._update_style()

    def _on_click(self):
        """Handle button click."""
        if self._is_active:
            # Show confirmation dialog
            reply = QMessageBox.question(
                self,
                "Reset Emergency Stop",
                "Are you sure you want to reset the emergency stop?\n\n"
                "Make sure the system is safe before proceeding.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.estop_reset.emit()
        else:
            # Trigger E-stop immediately
            self.estop_triggered.emit()

    def set_active(self, active: bool):
        """Set the E-stop active state.

        Args:
            active: True if E-stop is active
        """
        self._is_active = active
        self._pulse_state = False

        if active:
            self._pulse_timer.start()
        else:
            self._pulse_timer.stop()

        self._update_style()

    @property
    def is_active(self) -> bool:
        """Check if E-stop is active."""
        return self._is_active
