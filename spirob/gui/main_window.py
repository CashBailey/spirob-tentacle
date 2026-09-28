"""Main window for SpiRob control GUI."""

import os
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QStatusBar, QMenuBar, QMenu, QMessageBox, QApplication
)
from PyQt6.QtCore import Qt, QTimer, QSettings
from PyQt6.QtGui import QAction, QKeySequence, QCloseEvent

from spirob.gui.styles.dark_theme import COLORS, DarkTheme
from spirob.gui.ros_bridge import RosBridge, SystemStatus, ServoTelemetry
from spirob.gui.controller import ControllerHandler, ControllerState

from spirob.gui.widgets.tendon_control import TendonControlWidget
from spirob.gui.widgets.status_panel import StatusPanel
from spirob.gui.widgets.estop_button import EStopButton
from spirob.gui.widgets.controller_panel import ControllerPanel
from spirob.gui.widgets.telemetry_graph import TelemetryGraph
from spirob.gui.widgets.preset_panel import PresetPanel, Preset


class MainWindow(QMainWindow):
    """Main application window for SpiRob control.

    Features responsive layout that handles window resizing gracefully.
    Integrates ROS2 bridge and gamepad controller support.
    """

    # Update rates
    TELEMETRY_UPDATE_MS = 50  # 20 Hz
    GRAPH_UPDATE_MS = 100     # 10 Hz

    # Window sizing
    WINDOW_MIN_WIDTH = 900
    WINDOW_MIN_HEIGHT = 600
    DEFAULT_WINDOW_WIDTH = 1200
    DEFAULT_WINDOW_HEIGHT = 800

    # Layout constants
    LAYOUT_MARGIN = 8
    LAYOUT_SPACING = 8
    SPLITTER_HANDLE_WIDTH = 4

    # Splitter sizing
    DEFAULT_SPLITTER_SIZES = [200, 400, 300]

    # Status message durations (milliseconds)
    STATUS_MESSAGE_SHORT_MS = 3000
    STATUS_MESSAGE_LONG_MS = 5000
    STATUS_MESSAGE_PRESET_MS = 2000

    def __init__(self,
                 ros_bridge: Optional[RosBridge] = None,
                 controller: Optional[ControllerHandler] = None,
                 parent=None) -> None:
        super().__init__(parent)

        self.setWindowTitle("SpiRob Control Panel")
        self.setMinimumSize(self.WINDOW_MIN_WIDTH, self.WINDOW_MIN_HEIGHT)

        # Initialize components (injectable for testing)
        self._ros_bridge = ros_bridge or RosBridge()
        self._controller = controller or ControllerHandler()

        # Track current positions for presets and controller
        self._current_positions = {'u': 0.0, 'v': 0.0, 'w': 0.0}
        self._target_positions = {'u': 0.0, 'v': 0.0, 'w': 0.0}

        # Set up UI
        self._setup_ui()
        self._setup_menu()
        self._setup_statusbar()
        self._setup_shortcuts()
        self._connect_signals()
        self._setup_timers()

        # Apply theme
        self.setStyleSheet(DarkTheme.get_stylesheet())

        # Restore window state
        self._restore_state()

        # Start services
        self._start_services()

    def _setup_ui(self) -> None:
        """Set up the main UI layout."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main horizontal layout with splitter for resizable panels
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(
            self.LAYOUT_MARGIN, self.LAYOUT_MARGIN,
            self.LAYOUT_MARGIN, self.LAYOUT_MARGIN
        )
        main_layout.setSpacing(self.LAYOUT_SPACING)

        # Create main splitter (left | center | right)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(self.SPLITTER_HANDLE_WIDTH)
        main_splitter.setChildrenCollapsible(False)

        # === LEFT COLUMN ===
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(self.LAYOUT_SPACING)

        # Status panel (connection, servos)
        self._status_panel = StatusPanel()
        left_layout.addWidget(self._status_panel)

        # E-Stop button
        self._estop_btn = EStopButton()
        left_layout.addWidget(self._estop_btn)

        # Preset panel
        presets_path = self._get_presets_path()
        self._preset_panel = PresetPanel(config_path=presets_path)
        left_layout.addWidget(self._preset_panel, stretch=1)

        main_splitter.addWidget(left_widget)

        # === CENTER COLUMN ===
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(self.LAYOUT_SPACING)

        # Tendon controls
        self._tendon_u = TendonControlWidget("U", COLORS['tendon_u'])
        self._tendon_v = TendonControlWidget("V", COLORS['tendon_v'])
        self._tendon_w = TendonControlWidget("W", COLORS['tendon_w'])

        center_layout.addWidget(self._tendon_u)
        center_layout.addWidget(self._tendon_v)
        center_layout.addWidget(self._tendon_w)
        center_layout.addStretch()

        main_splitter.addWidget(center_widget)

        # === RIGHT COLUMN ===
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(self.LAYOUT_SPACING)

        # Controller panel
        self._controller_panel = ControllerPanel()
        right_layout.addWidget(self._controller_panel)

        # Telemetry graph
        self._telemetry_graph = TelemetryGraph()
        right_layout.addWidget(self._telemetry_graph, stretch=1)

        main_splitter.addWidget(right_widget)

        # Set initial splitter sizes (proportional)
        main_splitter.setSizes(self.DEFAULT_SPLITTER_SIZES)
        main_splitter.setStretchFactor(0, 0)  # Left: fixed
        main_splitter.setStretchFactor(1, 2)  # Center: expandable
        main_splitter.setStretchFactor(2, 1)  # Right: semi-expandable

        main_layout.addWidget(main_splitter)
        self._main_splitter = main_splitter

    def _setup_menu(self) -> None:
        """Set up the menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        exit_action = QAction("E&xit", self)
        exit_action.setShortcut(QKeySequence.StandardKey.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # View menu
        view_menu = menubar.addMenu("&View")

        reset_layout_action = QAction("&Reset Layout", self)
        reset_layout_action.triggered.connect(self._reset_layout)
        view_menu.addAction(reset_layout_action)

        # Control menu
        control_menu = menubar.addMenu("&Control")

        torque_action = QAction("Toggle &Torque", self)
        torque_action.setShortcut("T")
        torque_action.triggered.connect(self._toggle_torque)
        control_menu.addAction(torque_action)

        control_menu.addSeparator()

        zero_all_action = QAction("&Zero All", self)
        zero_all_action.setShortcut("Z")
        zero_all_action.triggered.connect(self._zero_all)
        control_menu.addAction(zero_all_action)

        control_menu.addSeparator()

        estop_action = QAction("&Emergency Stop", self)
        estop_action.setShortcut("Space")
        estop_action.triggered.connect(self._trigger_estop)
        control_menu.addAction(estop_action)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        about_action = QAction("&About", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

        controls_action = QAction("&Controller Mapping", self)
        controls_action.triggered.connect(self._show_controller_help)
        help_menu.addAction(controls_action)

    def _setup_statusbar(self) -> None:
        """Set up the status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self._statusbar.showMessage("Starting...")

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        # These are handled via menu actions, but can add more here if needed
        pass

    def _connect_signals(self) -> None:
        """Connect all signals and slots."""
        # === ROS Bridge signals ===
        self._ros_bridge.joint_states_received.connect(self._on_joint_states)
        self._ros_bridge.telemetry_received.connect(self._on_telemetry)
        self._ros_bridge.status_changed.connect(self._on_status_changed)
        self._ros_bridge.service_result.connect(self._on_service_result)
        self._ros_bridge.connection_changed.connect(self._on_ros_connection_changed)

        # === Controller signals ===
        self._controller.state_changed.connect(self._on_controller_state)
        self._controller.connected.connect(self._on_controller_connected)
        self._controller.disconnected.connect(self._on_controller_disconnected)
        self._controller.estop_pressed.connect(self._trigger_estop)
        self._controller.torque_toggle_pressed.connect(self._toggle_torque)
        self._controller.reset_estop_pressed.connect(self._reset_estop)
        self._controller.zero_all_pressed.connect(self._zero_all)
        self._controller.movement.connect(self._on_controller_movement)

        # === Tendon control signals ===
        self._tendon_u.target_changed.connect(lambda a: self._send_target('u', a))
        self._tendon_v.target_changed.connect(lambda a: self._send_target('v', a))
        self._tendon_w.target_changed.connect(lambda a: self._send_target('w', a))

        self._tendon_u.zero_requested.connect(lambda: self._ros_bridge.call_zero('u'))
        self._tendon_v.zero_requested.connect(lambda: self._ros_bridge.call_zero('v'))
        self._tendon_w.zero_requested.connect(lambda: self._ros_bridge.call_zero('w'))

        # === Status panel signals ===
        self._status_panel.torque_toggled.connect(self._ros_bridge.send_torque_enable)
        self._status_panel.scan_requested.connect(self._ros_bridge.call_scan_bus)

        # === E-Stop signals ===
        self._estop_btn.estop_triggered.connect(self._trigger_estop)
        self._estop_btn.estop_reset.connect(self._reset_estop)

        # === Preset signals ===
        self._preset_panel.preset_selected.connect(self._on_preset_selected)

    def _setup_timers(self) -> None:
        """Set up update timers."""
        # Telemetry update timer (update positions in widgets)
        self._telemetry_timer = QTimer(self)
        self._telemetry_timer.timeout.connect(self._update_telemetry_display)
        self._telemetry_timer.start(self.TELEMETRY_UPDATE_MS)

        # Graph update timer
        self._graph_timer = QTimer(self)
        self._graph_timer.timeout.connect(self._update_graphs)
        self._graph_timer.start(self.GRAPH_UPDATE_MS)

    def _start_services(self) -> None:
        """Start ROS bridge and controller."""
        # Start ROS bridge
        if self._ros_bridge.start():
            self._statusbar.showMessage("ROS bridge started", self.STATUS_MESSAGE_SHORT_MS)
        else:
            self._statusbar.showMessage("Failed to start ROS bridge", self.STATUS_MESSAGE_LONG_MS)

        # Start controller
        if self._controller.start():
            self._statusbar.showMessage("Controller support enabled", self.STATUS_MESSAGE_SHORT_MS)
        else:
            self._statusbar.showMessage("Controller not available (pygame?)", self.STATUS_MESSAGE_SHORT_MS)

    def _get_presets_path(self) -> str:
        """Get path to presets configuration file."""
        # Use ~/.spirob/presets.yaml
        config_dir = Path.home() / '.spirob'
        config_dir.mkdir(exist_ok=True)
        return str(config_dir / 'presets.yaml')

    # === Slot handlers ===

    def _on_joint_states(self, positions: dict) -> None:
        """Handle joint state updates."""
        import math
        for name, pos_rad in positions.items():
            tendon = name.replace('joint_', '')
            if tendon in self._current_positions:
                self._current_positions[tendon] = math.degrees(pos_rad)

    def _on_telemetry(self, tendon: str, telemetry: ServoTelemetry) -> None:
        """Handle telemetry updates."""
        self._current_positions[tendon] = telemetry.position_deg

        # Update status panel servo status
        self._status_panel.set_servo_status(
            tendon,
            telemetry.is_connected,
            telemetry.error_flags != 0
        )

        # Add data point to graph
        self._telemetry_graph.add_data_point(tendon, telemetry.position_deg)

    def _on_status_changed(self, status: SystemStatus) -> None:
        """Handle system status changes."""
        self._status_panel.set_bus_status(status.bus_healthy)
        self._estop_btn.set_active(status.estop_active)
        self._status_panel.set_torque_enabled(status.torque_enabled)

        # Update status bar
        if status.estop_active:
            self._statusbar.showMessage("⚠️ E-STOP ACTIVE")
            self._statusbar.setStyleSheet(f"background-color: {COLORS['red']};")
        else:
            self._statusbar.setStyleSheet("")

    def _on_service_result(self, service: str, success: bool, message: str) -> None:
        """Handle service call results."""
        if success:
            self._statusbar.showMessage(f"{service}: {message}", self.STATUS_MESSAGE_SHORT_MS)
        else:
            self._statusbar.showMessage(f"⚠️ {service} failed: {message}", self.STATUS_MESSAGE_LONG_MS)

    def _on_ros_connection_changed(self, connected: bool) -> None:
        """Handle ROS connection state changes."""
        self._status_panel.set_ros_status(connected)

    def _on_controller_state(self, state: ControllerState) -> None:
        """Handle controller state updates."""
        self._controller_panel.update_state(state)

    def _on_controller_connected(self, name: str) -> None:
        """Handle controller connection."""
        self._status_panel.set_controller_status(True, name)
        self._controller_panel.set_connected(True, name)
        self._statusbar.showMessage(f"Controller connected: {name}", self.STATUS_MESSAGE_SHORT_MS)

    def _on_controller_disconnected(self) -> None:
        """Handle controller disconnection."""
        self._status_panel.set_controller_status(False)
        self._controller_panel.set_connected(False)
        self._statusbar.showMessage("Controller disconnected", self.STATUS_MESSAGE_SHORT_MS)

    def _on_controller_movement(self, tendon: str, delta_deg: float) -> None:
        """Handle movement from controller analog sticks."""
        tendon_widget = {
            'u': self._tendon_u,
            'v': self._tendon_v,
            'w': self._tendon_w,
        }.get(tendon)

        if tendon_widget:
            tendon_widget.adjust_target(delta_deg)

    def _on_preset_selected(self, preset: Preset) -> None:
        """Handle preset selection."""
        self._send_target('u', preset.u_angle)
        self._send_target('v', preset.v_angle)
        self._send_target('w', preset.w_angle)

        self._tendon_u.set_target_position(preset.u_angle)
        self._tendon_v.set_target_position(preset.v_angle)
        self._tendon_w.set_target_position(preset.w_angle)

        self._statusbar.showMessage(f"Preset '{preset.name}' applied", self.STATUS_MESSAGE_PRESET_MS)

    # === Commands ===

    def _send_target(self, tendon: str, angle_deg: float) -> None:
        """Send target angle to a tendon."""
        self._target_positions[tendon] = angle_deg
        self._ros_bridge.send_target_angle(tendon, angle_deg)

    def _toggle_torque(self) -> None:
        """Toggle torque enable state."""
        self._status_panel.toggle_torque()

    def _zero_all(self) -> None:
        """Zero all tendons."""
        reply = QMessageBox.question(
            self, "Zero All Tendons",
            "Zero all tendons at current position?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._ros_bridge.call_zero_all()
            self._statusbar.showMessage("Zeroing all tendons...", self.STATUS_MESSAGE_PRESET_MS)

    def _trigger_estop(self) -> None:
        """Trigger emergency stop."""
        self._ros_bridge.call_emergency_stop()
        self._statusbar.showMessage("Emergency stop triggered!", self.STATUS_MESSAGE_LONG_MS)

    def _reset_estop(self) -> None:
        """Reset emergency stop."""
        self._ros_bridge.call_reset_estop()

    # === Update methods ===

    def _update_telemetry_display(self) -> None:
        """Update telemetry display in widgets."""
        self._tendon_u.set_current_position(self._current_positions['u'])
        self._tendon_v.set_current_position(self._current_positions['v'])
        self._tendon_w.set_current_position(self._current_positions['w'])

        # Update preset panel with current positions
        self._preset_panel.set_current_positions(
            self._current_positions['u'],
            self._current_positions['v'],
            self._current_positions['w']
        )

    def _update_graphs(self) -> None:
        """Update telemetry graphs."""
        self._telemetry_graph.update_plot()

    # === UI helpers ===

    def _reset_layout(self) -> None:
        """Reset layout to defaults."""
        self._main_splitter.setSizes(self.DEFAULT_SPLITTER_SIZES)
        self._statusbar.showMessage("Layout reset", self.STATUS_MESSAGE_PRESET_MS)

    def _show_about(self) -> None:
        """Show about dialog."""
        QMessageBox.about(
            self,
            "About SpiRob Control",
            "<h2>SpiRob Control Panel</h2>"
            "<p>A beautiful GUI for controlling the SpiRob 3-tendon soft robotic tentacle.</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Intuitive slider controls</li>"
            "<li>Xbox/PS5 controller support</li>"
            "<li>Real-time telemetry graphs</li>"
            "<li>Preset pose management</li>"
            "</ul>"
            "<p>Built with PyQt6 and ROS2</p>"
        )

    def _show_controller_help(self) -> None:
        """Show controller mapping help."""
        QMessageBox.information(
            self,
            "Controller Mapping",
            "<h3>Xbox/PS5 Controller Mapping</h3>"
            "<p><b>Analog Sticks:</b></p>"
            "<ul>"
            "<li>Left Stick Y: U Tendon</li>"
            "<li>Left Stick X: V Tendon</li>"
            "<li>Right Stick Y: W Tendon</li>"
            "</ul>"
            "<p><b>Buttons:</b></p>"
            "<ul>"
            "<li>Y/△: Emergency Stop</li>"
            "<li>A/✕: Toggle Torque</li>"
            "<li>B/○: Reset E-Stop</li>"
            "<li>Back/Share: Zero All</li>"
            "</ul>"
            "<p><b>Speed Modifiers:</b></p>"
            "<ul>"
            "<li>Normal: 90°/s</li>"
            "<li>LB held: 30°/s (slow)</li>"
            "<li>RB held: 180°/s (fast)</li>"
            "<li>LB+RB: 360°/s (max)</li>"
            "</ul>"
        )

    # === State persistence ===

    def _restore_state(self) -> None:
        """Restore window state from settings."""
        settings = QSettings("SpiRob", "ControlPanel")

        # Window geometry
        geometry = settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        else:
            # Default size and center on screen
            self.resize(self.DEFAULT_WINDOW_WIDTH, self.DEFAULT_WINDOW_HEIGHT)
            screen = QApplication.primaryScreen()
            if screen:
                screen_geom = screen.availableGeometry()
                self.move(
                    (screen_geom.width() - self.width()) // 2,
                    (screen_geom.height() - self.height()) // 2
                )

        # Splitter state
        splitter_state = settings.value("splitter")
        if splitter_state:
            self._main_splitter.restoreState(splitter_state)

    def _save_state(self) -> None:
        """Save window state to settings."""
        settings = QSettings("SpiRob", "ControlPanel")
        settings.setValue("geometry", self.saveGeometry())
        settings.setValue("splitter", self._main_splitter.saveState())

    def closeEvent(self, event: QCloseEvent) -> None:
        """Handle window close event."""
        # Save state
        self._save_state()

        # Stop services
        self._controller.stop()
        self._ros_bridge.stop()

        event.accept()
