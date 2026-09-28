"""Real-time telemetry graph widget using pyqtgraph."""

import time
from collections import deque
from typing import Dict

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox,
    QPushButton, QComboBox, QSizePolicy
)
from PyQt6.QtCore import Qt

from spirob.gui.styles.dark_theme import COLORS

# Try to import pyqtgraph
try:
    import pyqtgraph as pg
    HAS_PYQTGRAPH = True
except ImportError:
    HAS_PYQTGRAPH = False


class TelemetryGraph(QWidget):
    """Real-time telemetry graph widget.

    Shows position history for all three tendons with different colors.
    """

    # Time window options (seconds)
    TIME_WINDOWS = [5, 30, 60]

    def __init__(self, parent=None):
        super().__init__(parent)

        self._time_window = 30  # seconds
        self._paused = False
        self._start_time = time.time()

        # Data buffers (time, value)
        self._max_points = 3000  # Max points to keep
        self._data: Dict[str, deque] = {
            'u': deque(maxlen=self._max_points),
            'v': deque(maxlen=self._max_points),
            'w': deque(maxlen=self._max_points),
        }

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        group = QGroupBox("Telemetry")
        group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(group)

        if HAS_PYQTGRAPH:
            self._setup_pyqtgraph(layout)
        else:
            # Fallback if pyqtgraph not available
            fallback_label = QLabel(
                "pyqtgraph not installed.\n"
                "Install with: pip install pyqtgraph"
            )
            fallback_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fallback_label.setStyleSheet(f"color: {COLORS['subtext0']};")
            layout.addWidget(fallback_label)

        # Controls row
        controls_row = QHBoxLayout()

        # Time window selector
        window_label = QLabel("Window:")
        window_label.setProperty("subheading", True)
        controls_row.addWidget(window_label)

        self._window_combo = QComboBox()
        for t in self.TIME_WINDOWS:
            self._window_combo.addItem(f"{t}s", t)
        self._window_combo.setCurrentIndex(1)  # 30s default
        self._window_combo.currentIndexChanged.connect(self._on_window_changed)
        controls_row.addWidget(self._window_combo)

        controls_row.addStretch()

        # Legend
        legend_layout = QHBoxLayout()
        for tendon, color in [('U', COLORS['tendon_u']),
                               ('V', COLORS['tendon_v']),
                               ('W', COLORS['tendon_w'])]:
            legend_item = QLabel(f"● {tendon}")
            legend_item.setStyleSheet(f"color: {color};")
            legend_layout.addWidget(legend_item)
        controls_row.addLayout(legend_layout)

        controls_row.addStretch()

        # Pause button
        self._pause_btn = QPushButton("⏸ Pause")
        self._pause_btn.setCheckable(True)
        self._pause_btn.setFixedWidth(80)
        self._pause_btn.clicked.connect(self._on_pause_clicked)
        controls_row.addWidget(self._pause_btn)

        # Clear button
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(60)
        self._clear_btn.clicked.connect(self._clear_data)
        controls_row.addWidget(self._clear_btn)

        layout.addLayout(controls_row)

        # Main widget layout
        widget_layout = QVBoxLayout(self)
        widget_layout.setContentsMargins(0, 0, 0, 0)
        widget_layout.addWidget(group)

    def _setup_pyqtgraph(self, layout):
        """Set up pyqtgraph plot widget."""
        # Configure pyqtgraph
        pg.setConfigOptions(antialias=True)

        # Create plot widget
        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground(COLORS['surface0'])
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self._plot_widget.setLabel('left', 'Position', '°')
        self._plot_widget.setLabel('bottom', 'Time', 's')
        self._plot_widget.setYRange(-2500, 2500)  # ±2292° range

        # Style axes
        axis_pen = pg.mkPen(color=COLORS['overlay0'])
        self._plot_widget.getAxis('left').setPen(axis_pen)
        self._plot_widget.getAxis('bottom').setPen(axis_pen)
        self._plot_widget.getAxis('left').setTextPen(COLORS['subtext0'])
        self._plot_widget.getAxis('bottom').setTextPen(COLORS['subtext0'])

        # Create plot curves
        self._curves = {
            'u': self._plot_widget.plot(pen=pg.mkPen(COLORS['tendon_u'], width=2)),
            'v': self._plot_widget.plot(pen=pg.mkPen(COLORS['tendon_v'], width=2)),
            'w': self._plot_widget.plot(pen=pg.mkPen(COLORS['tendon_w'], width=2)),
        }

        layout.addWidget(self._plot_widget)

    def _on_window_changed(self, index: int):
        """Handle time window change."""
        self._time_window = self._window_combo.currentData()
        self._update_plot()

    def _on_pause_clicked(self):
        """Handle pause button click."""
        self._paused = self._pause_btn.isChecked()
        self._pause_btn.setText("▶ Resume" if self._paused else "⏸ Pause")

    def _clear_data(self):
        """Clear all data."""
        for data in self._data.values():
            data.clear()
        self._start_time = time.time()
        self._update_plot()

    def add_data_point(self, tendon: str, position_deg: float):
        """Add a data point for a tendon.

        Args:
            tendon: Tendon name ('u', 'v', 'w')
            position_deg: Position in degrees
        """
        if self._paused:
            return

        if tendon.lower() in self._data:
            t = time.time() - self._start_time
            self._data[tendon.lower()].append((t, position_deg))

    def update_plot(self):
        """Update the plot with current data."""
        if not HAS_PYQTGRAPH or self._paused:
            return

        self._update_plot()

    def _update_plot(self):
        """Internal method to update plot."""
        if not HAS_PYQTGRAPH:
            return

        current_time = time.time() - self._start_time
        min_time = current_time - self._time_window

        for tendon, curve in self._curves.items():
            data = self._data[tendon]
            if data:
                # Filter to time window
                visible_data = [(t, v) for t, v in data if t >= min_time]
                if visible_data:
                    times, values = zip(*visible_data)
                    curve.setData(times, values)
                else:
                    curve.setData([], [])
            else:
                curve.setData([], [])

        # Update x-axis range
        self._plot_widget.setXRange(max(0, min_time), current_time)

    def auto_scale_y(self):
        """Auto-scale Y axis based on current data."""
        if not HAS_PYQTGRAPH:
            return

        all_values = []
        for data in self._data.values():
            all_values.extend([v for _, v in data])

        if all_values:
            min_val = min(all_values) - 100
            max_val = max(all_values) + 100
            self._plot_widget.setYRange(min_val, max_val)
