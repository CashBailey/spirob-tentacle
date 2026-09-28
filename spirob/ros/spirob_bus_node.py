"""Main ROS2 node for spirob servo control.

Implements the spirob_bus node specified in the High-Level Design Specification.
"""

import logging
import sys
from typing import Dict, List

import rclpy
from rclpy.node import Node
from rclpy.callback_groups import ReentrantCallbackGroup

from spirob.bus import ThreadSafeSerialPort, BusAdapter, PortDiscovery
from spirob.bus.servo import ServoState
from spirob.utils.exceptions import PortError
from spirob.control import ServoManager, SpoolConfig
from spirob.ros.parameters import declare_parameters, load_parameters, SpirobParameters
from spirob.ros.publishers import SpirobPublishers
from spirob.ros.subscribers import SpirobSubscribers
from spirob.ros.services import SpirobServices


def _get_default_port() -> str:
    """Get platform-appropriate default serial port."""
    if sys.platform == 'win32':
        return 'COM3'
    elif sys.platform == 'darwin':
        return '/dev/cu.usbserial-0001'
    # Linux: prefer ACM (WaveShare in WSL) over USB-serial
    import os
    for port in ['/dev/ttyACM0', '/dev/ttyUSB0']:
        if os.path.exists(port):
            return port
    return '/dev/ttyACM0'


class SpirobBusNode(Node):
    """Main ROS2 node for spirob servo control.

    This node provides:
    - Topic subscriptions for target angle commands
    - Topic publications for joint states and diagnostics
    - Services for zeroing, emergency stop, etc.
    - Background telemetry polling
    """

    def __init__(self):
        """Initialize the spirob_bus node."""
        super().__init__('spirob_bus')

        # Set up logging
        self._setup_logging()

        # Declare and load parameters
        declare_parameters(self)
        self._params = load_parameters(self)

        # Initialize hardware
        self._serial: ThreadSafeSerialPort = None
        self._bus_adapter: BusAdapter = None
        self._servo_manager: ServoManager = None

        # ROS interfaces (avoid _publishers/_subscribers/_services - reserved by Node)
        self._pub_manager: SpirobPublishers = None
        self._sub_manager: SpirobSubscribers = None
        self._srv_manager: SpirobServices = None

        # Callback group for concurrent service handling
        self._callback_group = ReentrantCallbackGroup()

        # Initialize components
        self._init_hardware()
        self._init_ros_interfaces()

        # Create publish timer
        period = 1.0 / self._params.telemetry_rate_hz
        self._publish_timer = self.create_timer(
            period,
            self._publish_callback,
            callback_group=self._callback_group
        )

        # Start telemetry
        self._startup()

    def _setup_logging(self) -> None:
        """Configure Python logging to integrate with ROS2."""
        # Get the ROS logger name
        logger = logging.getLogger('spirob')
        logger.setLevel(logging.DEBUG)

        # Add handler that forwards to ROS logging
        # (ROS2 logging is handled separately)

    def _init_hardware(self) -> None:
        """Initialize hardware components."""
        # Auto-discover port if set to 'auto'
        port = self._params.port
        baud = self._params.baud

        if port.lower() == 'auto':
            self.get_logger().info("Auto-discovering servo bus port...")
            discovery = PortDiscovery()
            discovered = discovery.discover(preferred_baud=baud)

            if discovered:
                port = discovery.found_port
                baud = discovery.found_baud
                self.get_logger().info(f"Found servo bus on {port} at {baud} baud")
            else:
                default_port = _get_default_port()
                self.get_logger().warning(
                    f"Auto-discovery failed, trying default port: {default_port}"
                )
                port = default_port

        self.get_logger().info(f"Initializing hardware on {port}")

        # Create serial port
        self._serial = ThreadSafeSerialPort(
            port=port,
            baudrate=baud
        )

        # Create bus adapter
        self._bus_adapter = BusAdapter(self._serial)

        # Create servo manager
        self._servo_manager = ServoManager(
            bus_adapter=self._bus_adapter,
            id_map=self._params.id_map,
            telemetry_rate_hz=self._params.telemetry_rate_hz
        )

        # Configure safety limits
        for tendon, limits in self._params.soft_limits.items():
            self._servo_manager.configure_limits(tendon, limits)
            self.get_logger().debug(f"Configured limits for {tendon}")

        # Configure spool geometry (same for all tendons)
        for tendon in self._params.id_map.keys():
            self._servo_manager.configure_spool(tendon, self._params.spool_config)

        # Configure heartbeat timeout
        self._servo_manager.safety.set_heartbeat_timeout(
            self._params.heartbeat_timeout_ms
        )

        # Set up callbacks
        self._servo_manager.set_fault_callback(self._on_fault)

    def _init_ros_interfaces(self) -> None:
        """Initialize ROS2 publishers, subscribers, and services."""
        # Publishers
        self._pub_manager = SpirobPublishers(self)
        self._pub_manager.setup()

        # Subscribers
        self._sub_manager = SpirobSubscribers(
            self,
            on_target_angle=self._on_target_angle,
            on_torque_enable=self._on_torque_enable
        )
        self._sub_manager.setup()

        # Services
        self._srv_manager = SpirobServices(self, self._servo_manager)
        self._srv_manager.setup()

    def _startup(self) -> None:
        """Connect to bus, initialize servos, start telemetry.

        Target: <=2s startup time per spec.
        """
        self.get_logger().info("Starting spirob_bus node...")

        # Open serial port
        try:
            if not self._serial.open():
                self.get_logger().error("Failed to open serial port")
                return
        except (PortError, OSError) as e:
            self.get_logger().error(f"Serial port error: {e}")
            return

        self.get_logger().info("Serial port opened successfully")

        # Initialize servos
        if not self._servo_manager.initialize():
            self.get_logger().warning(
                "Some servos failed to initialize - continuing with available servos"
            )

        # Start telemetry thread
        self._servo_manager.start_telemetry()

        self.get_logger().info("spirob_bus node started successfully")

    # === ROS Callbacks ===

    def _on_target_angle(self, tendon: str, angle_deg: float) -> None:
        """Handle incoming target angle command.

        Args:
            tendon: Tendon name ('u', 'v', 'w')
            angle_deg: Target angle in degrees
        """
        self.get_logger().debug(f"Target angle for {tendon}: {angle_deg:.1f} deg")

        if not self._servo_manager.set_target_angle(tendon, angle_deg):
            self.get_logger().warning(f"Failed to set target for {tendon}")

    def _on_torque_enable(self, enable: bool) -> None:
        """Handle torque enable/disable command.

        Args:
            enable: True to enable, False to disable
        """
        action = "Enabling" if enable else "Disabling"
        self.get_logger().info(f"{action} torque on all servos")

        if not self._servo_manager.set_all_torque_enable(enable):
            self.get_logger().warning("Failed to set torque enable")

    def _publish_callback(self) -> None:
        """Timer callback to publish joint states and diagnostics."""
        states = self._servo_manager.get_all_states()

        if not states:
            return

        # Publish all topics
        self._pub_manager.publish_joint_states(states)
        self._pub_manager.publish_diagnostics(states, self._serial.is_open())
        self._pub_manager.publish_angles(states)

    # === ServoManager Callbacks ===

    def _on_fault(self, tendon: str, faults: List[str]) -> None:
        """Called by ServoManager when a fault is detected.

        Args:
            tendon: Tendon with fault
            faults: List of fault names
        """
        self.get_logger().warning(f"Fault on {tendon}: {', '.join(faults)}")

    # === Lifecycle ===

    def destroy_node(self) -> None:
        """Clean shutdown."""
        self.get_logger().info("Shutting down spirob_bus node...")

        # Stop telemetry
        if self._servo_manager:
            self._servo_manager.shutdown()

        # Close serial port
        if self._serial:
            self._serial.close()

        super().destroy_node()
        self.get_logger().info("spirob_bus node shutdown complete")
