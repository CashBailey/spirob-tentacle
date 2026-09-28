"""ROS2 communication bridge for the SpiRob GUI.

Handles all ROS2 pub/sub/service operations in a separate thread,
communicating with the Qt GUI via signals.
"""

import copy
import logging
import math
import threading
from dataclasses import dataclass
from typing import Any, Optional, Dict

import rclpy
import rclpy.exceptions
from rclpy.node import Node
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import QoSProfile, ReliabilityPolicy

from PyQt6.QtCore import QObject, pyqtSignal

from std_msgs.msg import Float32, Bool
from std_srvs.srv import Trigger
from sensor_msgs.msg import JointState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus

from spirob.ros.topic_config import TopicConfig

logger = logging.getLogger(__name__)

# Valid tendon identifiers
VALID_TENDONS = {'u', 'v', 'w'}


@dataclass
class ServoTelemetry:
    """Telemetry data for a single servo."""
    position_deg: float = 0.0
    speed_dps: float = 0.0
    voltage: float = 0.0
    temperature: int = 0
    current_ma: float = 0.0
    is_moving: bool = False
    error_flags: int = 0
    is_connected: bool = False


@dataclass
class SystemStatus:
    """Overall system status."""
    bus_connected: bool = False
    bus_healthy: bool = False
    estop_active: bool = False
    torque_enabled: bool = False


class RosBridge(QObject):
    """Bridge between ROS2 and Qt GUI.

    Runs ROS2 node in a separate thread and emits Qt signals
    when data is received.
    """

    # Signals for UI updates (thread-safe)
    joint_states_received = pyqtSignal(dict)  # {name: position_rad}
    telemetry_received = pyqtSignal(str, ServoTelemetry)  # (tendon, data)
    diagnostics_received = pyqtSignal(dict)  # {name: DiagnosticStatus}
    status_changed = pyqtSignal(SystemStatus)
    service_result = pyqtSignal(str, bool, str)  # (service_name, success, message)
    connection_changed = pyqtSignal(bool)  # connected state

    def __init__(self, topic_config: Optional[TopicConfig] = None):
        super().__init__()

        # Topic configuration (injectable for testing/namespacing)
        self._topics = topic_config or TopicConfig()

        self._node: Optional[Node] = None
        self._executor: Optional[SingleThreadedExecutor] = None
        self._spin_thread: Optional[threading.Thread] = None
        self._running = False

        # Publishers
        self._target_pubs: Dict[str, Any] = {}
        self._torque_pub = None

        # Service clients
        self._zero_clients: Dict[str, Any] = {}
        self._estop_client = None
        self._reset_estop_client = None
        self._scan_client = None

        # Current state (protected by lock for thread safety)
        self._state_lock = threading.Lock()
        self._status = SystemStatus()
        self._telemetry: Dict[str, ServoTelemetry] = {
            'u': ServoTelemetry(),
            'v': ServoTelemetry(),
            'w': ServoTelemetry(),
        }

    @property
    def is_connected(self) -> bool:
        """Check if ROS2 node is running."""
        return self._running and self._node is not None

    @property
    def status(self) -> SystemStatus:
        """Get current system status (thread-safe copy)."""
        with self._state_lock:
            return copy.copy(self._status)

    def get_telemetry(self, tendon: str) -> ServoTelemetry:
        """Get telemetry for a specific tendon (thread-safe copy)."""
        with self._state_lock:
            telem = self._telemetry.get(tendon)
            return copy.copy(telem) if telem else ServoTelemetry()

    def start(self) -> bool:
        """Start the ROS2 node in a background thread."""
        if self._running:
            return True

        try:
            # Initialize ROS2 if not already done
            if not rclpy.ok():
                rclpy.init()

            # Create node
            self._node = Node('spirob_gui')

            # Set up QoS
            qos = QoSProfile(depth=10)
            qos.reliability = ReliabilityPolicy.RELIABLE

            # Create subscribers
            self._node.create_subscription(
                JointState,
                self._topics.joint_states,
                self._on_joint_states,
                qos
            )

            self._node.create_subscription(
                DiagnosticArray,
                self._topics.diagnostics,
                self._on_diagnostics,
                qos
            )

            # Create publishers for target angles
            for tendon in ['u', 'v', 'w']:
                self._target_pubs[tendon] = self._node.create_publisher(
                    Float32,
                    self._topics.target_angle(tendon),
                    qos
                )

            # Global torque enable publisher
            self._torque_pub = self._node.create_publisher(
                Bool,
                self._topics.torque_enable,
                qos
            )

            # Create service clients
            for tendon in ['u', 'v', 'w']:
                self._zero_clients[tendon] = self._node.create_client(
                    Trigger,
                    self._topics.zero_here(tendon)
                )

            self._estop_client = self._node.create_client(
                Trigger,
                self._topics.emergency_stop
            )

            self._reset_estop_client = self._node.create_client(
                Trigger,
                self._topics.reset_estop
            )

            self._scan_client = self._node.create_client(
                Trigger,
                self._topics.scan_bus
            )

            # Create executor and spin thread
            self._executor = SingleThreadedExecutor()
            self._executor.add_node(self._node)

            self._running = True
            self._spin_thread = threading.Thread(
                target=self._spin_loop,
                name='ros_spin',
                daemon=True
            )
            self._spin_thread.start()

            self._node.get_logger().info('SpiRob GUI ROS bridge started')
            self.connection_changed.emit(True)
            return True

        except (rclpy.exceptions.RCLError, RuntimeError) as e:
            self._node = None
            self._running = False
            logger.error(f"Failed to start ROS bridge: {e}")
            return False

    def stop(self) -> None:
        """Stop the ROS2 node and thread."""
        self._running = False

        if self._executor:
            self._executor.shutdown()

        if self._spin_thread and self._spin_thread.is_alive():
            self._spin_thread.join(timeout=2.0)

        if self._node:
            self._node.destroy_node()
            self._node = None

        self.connection_changed.emit(False)

    def _spin_loop(self) -> None:
        """ROS2 spin loop running in background thread."""
        while self._running and rclpy.ok():
            try:
                self._executor.spin_once(timeout_sec=0.1)
            except rclpy.exceptions.RCLError as e:
                if self._running:
                    logger.warning(f"ROS spin error: {e}")

    # === Callbacks ===

    def _on_joint_states(self, msg: JointState) -> None:
        """Handle incoming joint state message."""
        positions = {}
        for i, name in enumerate(msg.name):
            if i < len(msg.position):
                positions[name] = msg.position[i]

        # Update telemetry positions (convert from radians)
        with self._state_lock:
            for name, pos_rad in positions.items():
                tendon = name.replace('joint_', '')
                if tendon in self._telemetry:
                    self._telemetry[tendon].position_deg = math.degrees(pos_rad)

        self.joint_states_received.emit(positions)

    def _apply_diagnostic_value(self, telem: ServoTelemetry, key: str, value: str) -> None:
        """Apply a single diagnostic key-value pair to telemetry.

        Args:
            telem: ServoTelemetry instance to update
            key: Diagnostic key name
            value: Diagnostic value as string
        """
        if key == 'position_deg':
            telem.position_deg = float(value)
        elif key == 'speed_dps':
            telem.speed_dps = float(value)
        elif key == 'voltage':
            telem.voltage = float(value)
        elif key == 'temperature':
            telem.temperature = int(value)
        elif key == 'current_ma':
            telem.current_ma = float(value)
        elif key == 'is_moving':
            telem.is_moving = value.lower() == 'true'
        elif key == 'error_flags':
            telem.error_flags = int(value, 16)

    def _parse_servo_diagnostic(self, status: DiagnosticStatus) -> Optional[tuple]:
        """Parse diagnostic status for a servo and update telemetry.

        Must be called with _state_lock held.

        Args:
            status: DiagnosticStatus message for a servo

        Returns:
            Tuple of (tendon, telemetry_copy) if updated, None otherwise
        """
        tendon = status.name.replace('servo_', '')
        telem = self._telemetry.get(tendon)
        if not telem:
            return None

        telem.is_connected = status.level != DiagnosticStatus.STALE

        for kv in status.values:
            self._apply_diagnostic_value(telem, kv.key, kv.value)

        return (tendon, copy.copy(telem))

    def _on_diagnostics(self, msg: DiagnosticArray) -> None:
        """Handle incoming diagnostics message."""
        diagnostics = {}
        telemetry_updates = []

        with self._state_lock:
            for status in msg.status:
                diagnostics[status.name] = status

                # Update system status
                if status.name == 'spirob_bus':
                    self._status.bus_connected = status.level != DiagnosticStatus.STALE
                    self._status.bus_healthy = status.level == DiagnosticStatus.OK

                # Update telemetry from diagnostics
                elif status.name.startswith('servo_'):
                    result = self._parse_servo_diagnostic(status)
                    if result:
                        telemetry_updates.append(result)

            # Copy status for emit
            status_copy = copy.copy(self._status)

        # Emit signals outside the lock to avoid deadlock
        for tendon, telem in telemetry_updates:
            self.telemetry_received.emit(tendon, telem)

        self.diagnostics_received.emit(diagnostics)
        self.status_changed.emit(status_copy)

    # === Commands ===

    def send_target_angle(self, tendon: str, angle_deg: float):
        """Send target angle command to a tendon.

        Args:
            tendon: Tendon name ('u', 'v', 'w')
            angle_deg: Target angle in degrees
        """
        if tendon not in VALID_TENDONS:
            logger.warning(f"Invalid tendon '{tendon}'. Must be one of {VALID_TENDONS}")
            return

        if tendon in self._target_pubs and self._running:
            msg = Float32()
            msg.data = float(angle_deg)
            self._target_pubs[tendon].publish(msg)

    def send_torque_enable(self, enable: bool) -> None:
        """Enable or disable torque on all servos.

        Args:
            enable: True to enable, False to disable
        """
        if self._torque_pub and self._running:
            msg = Bool()
            msg.data = enable
            self._torque_pub.publish(msg)
            with self._state_lock:
                self._status.torque_enabled = enable
                status_copy = copy.copy(self._status)
            self.status_changed.emit(status_copy)

    def call_zero(self, tendon: str):
        """Call zero service for a tendon.

        Args:
            tendon: Tendon name ('u', 'v', 'w')
        """
        if tendon not in self._zero_clients or not self._running:
            return

        client = self._zero_clients[tendon]
        if not client.service_is_ready():
            self.service_result.emit(f'zero_{tendon}', False, 'Service not available')
            return

        request = Trigger.Request()
        future = client.call_async(request)
        future.add_done_callback(
            lambda f: self._handle_service_response(f'zero_{tendon}', f)
        )

    def call_zero_all(self):
        """Call zero service for all tendons."""
        for tendon in ['u', 'v', 'w']:
            self.call_zero(tendon)

    def call_emergency_stop(self):
        """Trigger emergency stop."""
        if not self._estop_client or not self._running:
            return

        if not self._estop_client.service_is_ready():
            self.service_result.emit('emergency_stop', False, 'Service not available')
            return

        request = Trigger.Request()
        future = self._estop_client.call_async(request)
        future.add_done_callback(
            lambda f: self._handle_estop_response(f)
        )

    def call_reset_estop(self):
        """Reset emergency stop."""
        if not self._reset_estop_client or not self._running:
            return

        if not self._reset_estop_client.service_is_ready():
            self.service_result.emit('reset_estop', False, 'Service not available')
            return

        request = Trigger.Request()
        future = self._reset_estop_client.call_async(request)
        future.add_done_callback(
            lambda f: self._handle_reset_estop_response(f)
        )

    def call_scan_bus(self):
        """Scan bus for servos."""
        if not self._scan_client or not self._running:
            return

        if not self._scan_client.service_is_ready():
            self.service_result.emit('scan_bus', False, 'Service not available')
            return

        request = Trigger.Request()
        future = self._scan_client.call_async(request)
        future.add_done_callback(
            lambda f: self._handle_service_response('scan_bus', f)
        )

    def _handle_service_response(self, service_name: str, future):
        """Handle generic service response."""
        try:
            response = future.result()
            self.service_result.emit(service_name, response.success, response.message)
        except (rclpy.exceptions.RCLError, RuntimeError) as e:
            self.service_result.emit(service_name, False, str(e))

    def _handle_estop_response(self, future) -> None:
        """Handle E-stop service response."""
        try:
            response = future.result()
            if response.success:
                with self._state_lock:
                    self._status.estop_active = True
                    self._status.torque_enabled = False
                    status_copy = copy.copy(self._status)
                self.status_changed.emit(status_copy)
            self.service_result.emit('emergency_stop', response.success, response.message)
        except (rclpy.exceptions.RCLError, RuntimeError) as e:
            self.service_result.emit('emergency_stop', False, str(e))

    def _handle_reset_estop_response(self, future) -> None:
        """Handle reset E-stop service response."""
        try:
            response = future.result()
            if response.success:
                with self._state_lock:
                    self._status.estop_active = False
                    status_copy = copy.copy(self._status)
                self.status_changed.emit(status_copy)
            self.service_result.emit('reset_estop', response.success, response.message)
        except (rclpy.exceptions.RCLError, RuntimeError) as e:
            self.service_result.emit('reset_estop', False, str(e))
