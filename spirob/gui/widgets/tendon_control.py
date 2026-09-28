"""Tendon control widget with slider and input field."""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QDoubleSpinBox, QGroupBox, QSizePolicy
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QFont

from spirob.gui.styles.dark_theme import COLORS, DarkTheme


class TendonControlWidget(QWidget):
    """Control widget for a single tendon.

    Features:
    - Horizontal slider for position control
    - Input field for direct angle entry
    - Zero button for calibration
    - Current position display
    """

    target_changed = pyqtSignal(float)  # Emits target angle in degrees
    zero_requested = pyqtSignal()

    # Min/max angle range (based on spool geometry)
    MIN_ANGLE = -2292.0
    MAX_ANGLE = 2292.0

    def __init__(self, tendon_name: str, color: str, parent=None):
        """Initialize tendon control.

        Args:
            tendon_name: Name of the tendon (e.g., 'U', 'V', 'W')
            color: Color for this tendon (hex string)
            parent: Parent widget
        """
        super().__init__(parent)

        self._tendon_name = tendon_name
        self._color = color
        self._current_position = 0.0
        self._target_position = 0.0
        self._is_moving = False

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        # Main group box
        group = QGroupBox(f"{self._tendon_name} Tendon")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # === Top row: Current position and Zero button ===
        top_row = QHBoxLayout()

        # Current position label
        current_label = QLabel("Current:")
        current_label.setProperty("subheading", True)
        top_row.addWidget(current_label)

        self._current_display = QLabel("0.0°")
        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        self._current_display.setFont(font)
        self._current_display.setStyleSheet(f"color: {self._color};")
        self._current_display.setMinimumWidth(100)
        top_row.addWidget(self._current_display)

        top_row.addStretch()

        # Zero button
        self._zero_btn = QPushButton("Zero")
        self._zero_btn.setFixedWidth(60)
        self._zero_btn.clicked.connect(self.zero_requested.emit)
        top_row.addWidget(self._zero_btn)

        layout.addLayout(top_row)

        # === Slider ===
        self._slider = QSlider(Qt.Orientation.Horizontal)
        self._slider.setMinimum(int(self.MIN_ANGLE * 10))  # 0.1 degree resolution
        self._slider.setMaximum(int(self.MAX_ANGLE * 10))
        self._slider.setValue(0)
        self._slider.setStyleSheet(DarkTheme.get_tendon_slider_style(self._color))
        self._slider.valueChanged.connect(self._on_slider_changed)
        self._slider.sliderReleased.connect(self._on_slider_released)
        layout.addWidget(self._slider)

        # === Slider labels ===
        labels_row = QHBoxLayout()
        min_label = QLabel(f"{self.MIN_ANGLE:.0f}°")
        min_label.setProperty("subheading", True)
        labels_row.addWidget(min_label)
        labels_row.addStretch()
        max_label = QLabel(f"{self.MAX_ANGLE:.0f}°")
        max_label.setProperty("subheading", True)
        labels_row.addWidget(max_label)
        layout.addLayout(labels_row)

        # === Bottom row: Target input and Go button ===
        bottom_row = QHBoxLayout()

        target_label = QLabel("Target:")
        target_label.setProperty("subheading", True)
        bottom_row.addWidget(target_label)

        self._target_input = QDoubleSpinBox()
        self._target_input.setRange(self.MIN_ANGLE, self.MAX_ANGLE)
        self._target_input.setValue(0.0)
        self._target_input.setDecimals(1)
        self._target_input.setSuffix("°")
        self._target_input.setMinimumWidth(100)
        self._target_input.editingFinished.connect(self._on_input_finished)
        bottom_row.addWidget(self._target_input)

        self._go_btn = QPushButton("Go")
        self._go_btn.setProperty("accent", True)
        self._go_btn.setFixedWidth(50)
        self._go_btn.clicked.connect(self._on_go_clicked)
        bottom_row.addWidget(self._go_btn)

        bottom_row.addStretch()

        layout.addLayout(bottom_row)

        # === Main layout ===
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(group)

    def _on_slider_changed(self, value: int):
        """Handle slider value change."""
        angle = value / 10.0
        self._target_position = angle
        self._target_input.blockSignals(True)
        self._target_input.setValue(angle)
        self._target_input.blockSignals(False)

    def _on_slider_released(self):
        """Handle slider release - send command."""
        self.target_changed.emit(self._target_position)

    def _on_input_finished(self):
        """Handle input field editing finished."""
        angle = self._target_input.value()
        self._target_position = angle
        self._slider.blockSignals(True)
        self._slider.setValue(int(angle * 10))
        self._slider.blockSignals(False)

    def _on_go_clicked(self):
        """Handle Go button click."""
        self._target_position = self._target_input.value()
        self._slider.blockSignals(True)
        self._slider.setValue(int(self._target_position * 10))
        self._slider.blockSignals(False)
        self.target_changed.emit(self._target_position)

    def set_current_position(self, angle_deg: float):
        """Update the current position display.

        Args:
            angle_deg: Current position in degrees
        """
        self._current_position = angle_deg
        self._current_display.setText(f"{angle_deg:.1f}°")

    def set_target_position(self, angle_deg: float):
        """Set the target position (from external source like controller).

        Args:
            angle_deg: Target position in degrees
        """
        self._target_position = max(self.MIN_ANGLE, min(self.MAX_ANGLE, angle_deg))

        self._slider.blockSignals(True)
        self._slider.setValue(int(self._target_position * 10))
        self._slider.blockSignals(False)

        self._target_input.blockSignals(True)
        self._target_input.setValue(self._target_position)
        self._target_input.blockSignals(False)

    def adjust_target(self, delta_deg: float):
        """Adjust target by a delta amount.

        Args:
            delta_deg: Amount to adjust in degrees
        """
        new_target = self._target_position + delta_deg
        new_target = max(self.MIN_ANGLE, min(self.MAX_ANGLE, new_target))
        self.set_target_position(new_target)
        self.target_changed.emit(new_target)

    def set_moving(self, moving: bool):
        """Set the moving indicator state.

        Args:
            moving: True if servo is currently moving
        """
        self._is_moving = moving
        # Could add visual feedback here (glow effect, etc.)

    @property
    def current_position(self) -> float:
        """Get current position."""
        return self._current_position

    @property
    def target_position(self) -> float:
        """Get target position."""
        return self._target_position

    @property
    def tendon_name(self) -> str:
        """Get tendon name."""
        return self._tendon_name
