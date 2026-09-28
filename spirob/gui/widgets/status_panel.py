"""Status panel widget showing connection and servo status."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QCheckBox, QSlider, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt, QTimer
from PyQt6.QtGui import QFont

from spirob.gui.styles.dark_theme import COLORS


class StatusIndicator(QWidget):
    """Small colored dot indicator."""

    def __init__(self, label: str, parent=None):
        super().__init__(parent)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Indicator dot
        self._dot = QLabel("●")
        self._dot.setFixedSize(20, 20)
        font = QFont()
        font.setPointSize(14)
        self._dot.setFont(font)
        layout.addWidget(self._dot)

        # Label
        self._label = QLabel(label)
        layout.addWidget(self._label)
        layout.addStretch()

        # Initial state
        self.set_status('unknown')

    def set_status(self, status: str):
        """Set indicator status.

        Args:
            status: One of 'ok', 'warning', 'error', 'unknown', 'off'
        """
        colors = {
            'ok': COLORS['green'],
            'warning': COLORS['yellow'],
            'error': COLORS['red'],
            'unknown': COLORS['overlay0'],
            'off': COLORS['surface1'],
        }
        color = colors.get(status, COLORS['overlay0'])
        self._dot.setStyleSheet(f"color: {color};")


class StatusPanel(QWidget):
    """Panel showing system status and basic controls."""

    torque_toggled = pyqtSignal(bool)
    speed_changed = pyqtSignal(float)
    scan_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self._torque_enabled = False
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)

        # === Connection Status Group ===
        conn_group = QGroupBox("Connection")
        conn_layout = QVBoxLayout(conn_group)

        self._ros_status = StatusIndicator("ROS")
        conn_layout.addWidget(self._ros_status)

        self._bus_status = StatusIndicator("Bus")
        conn_layout.addWidget(self._bus_status)

        self._controller_status = StatusIndicator("Controller")
        conn_layout.addWidget(self._controller_status)

        # Scan button
        self._scan_btn = QPushButton("Scan Bus")
        self._scan_btn.clicked.connect(self.scan_requested.emit)
        conn_layout.addWidget(self._scan_btn)

        main_layout.addWidget(conn_group)

        # === Safety Group ===
        safety_group = QGroupBox("Safety")
        safety_layout = QVBoxLayout(safety_group)

        # Torque checkbox
        self._torque_checkbox = QCheckBox("Torque Enabled")
        self._torque_checkbox.stateChanged.connect(self._on_torque_changed)
        safety_layout.addWidget(self._torque_checkbox)

        # Speed slider
        speed_label = QLabel("Speed Limit")
        speed_label.setProperty("subheading", True)
        safety_layout.addWidget(speed_label)

        speed_row = QHBoxLayout()
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setMinimum(30)
        self._speed_slider.setMaximum(360)
        self._speed_slider.setValue(180)
        self._speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self._speed_slider)

        self._speed_label = QLabel("180°/s")
        self._speed_label.setMinimumWidth(50)
        speed_row.addWidget(self._speed_label)

        safety_layout.addLayout(speed_row)

        main_layout.addWidget(safety_group)

        # === Servo Status Group ===
        servo_group = QGroupBox("Servos")
        servo_layout = QVBoxLayout(servo_group)

        self._servo_u_status = StatusIndicator("U")
        servo_layout.addWidget(self._servo_u_status)

        self._servo_v_status = StatusIndicator("V")
        servo_layout.addWidget(self._servo_v_status)

        self._servo_w_status = StatusIndicator("W")
        servo_layout.addWidget(self._servo_w_status)

        main_layout.addWidget(servo_group)

        # Stretch to push everything up
        main_layout.addStretch()

    def _on_torque_changed(self, state: int):
        """Handle torque checkbox change."""
        enabled = state == Qt.CheckState.Checked.value
        self._torque_enabled = enabled
        self.torque_toggled.emit(enabled)

    def _on_speed_changed(self, value: int):
        """Handle speed slider change."""
        self._speed_label.setText(f"{value}°/s")
        self.speed_changed.emit(float(value))

    def set_ros_status(self, connected: bool):
        """Set ROS connection status."""
        self._ros_status.set_status('ok' if connected else 'error')

    def set_bus_status(self, healthy: bool):
        """Set bus status."""
        self._bus_status.set_status('ok' if healthy else 'error')

    def set_controller_status(self, connected: bool, name: str = ""):
        """Set controller connection status."""
        if connected:
            self._controller_status.set_status('ok')
            self._controller_status._label.setText(f"🎮 {name[:15]}" if name else "🎮 Connected")
        else:
            self._controller_status.set_status('off')
            self._controller_status._label.setText("Controller")

    def set_servo_status(self, tendon: str, connected: bool, has_error: bool = False):
        """Set individual servo status.

        Args:
            tendon: Tendon name ('u', 'v', 'w')
            connected: Whether servo is connected
            has_error: Whether servo has error flags
        """
        status_widget = {
            'u': self._servo_u_status,
            'v': self._servo_v_status,
            'w': self._servo_w_status,
        }.get(tendon.lower())

        if status_widget:
            if not connected:
                status_widget.set_status('error')
            elif has_error:
                status_widget.set_status('warning')
            else:
                status_widget.set_status('ok')

    def set_torque_enabled(self, enabled: bool):
        """Set torque enabled state (from external source)."""
        self._torque_enabled = enabled
        self._torque_checkbox.blockSignals(True)
        self._torque_checkbox.setChecked(enabled)
        self._torque_checkbox.blockSignals(False)

    def toggle_torque(self):
        """Toggle torque state."""
        new_state = not self._torque_enabled
        self._torque_checkbox.setChecked(new_state)

    @property
    def torque_enabled(self) -> bool:
        """Get torque enabled state."""
        return self._torque_enabled

    @property
    def speed_limit(self) -> float:
        """Get speed limit in deg/s."""
        return float(self._speed_slider.value())
