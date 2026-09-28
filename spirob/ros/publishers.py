"""ROS2 publishers for spirob_bus node."""

import math
from typing import Dict

from rclpy.node import Node
from rclpy.publisher import Publisher
from sensor_msgs.msg import JointState
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from std_msgs.msg import Float32

from spirob.bus.servo import ServoState


class SpirobPublishers:
    """Manages all ROS2 publishers for the spirob node."""

    def __init__(self, node: Node):
        """Initialize publishers.

        Args:
            node: ROS2 node to create publishers on
        """
        self._node = node
        self._joint_state_pub: Publisher = None
        self._diagnostics_pub: Publisher = None
        self._angle_pubs: Dict[str, Publisher] = {}

    def setup(self) -> None:
        """Create all publishers."""
        # Joint states (standard ROS message for robot state)
        self._joint_state_pub = self._node.create_publisher(
            JointState,
            '/servo/joint_states',
            10
        )

        # Diagnostics (standard ROS message for component health)
        self._diagnostics_pub = self._node.create_publisher(
            DiagnosticArray,
            '/servo/diagnostics',
            10
        )

        # Individual angle publishers (convenience topics)
        for tendon in ['u', 'v', 'w']:
            self._angle_pubs[tendon] = self._node.create_publisher(
                Float32,
                f'/servo/{tendon}/angle_deg',
                10
            )

        self._node.get_logger().info("Publishers initialized")

    def publish_joint_states(self, states: Dict[str, ServoState]) -> None:
        """Publish JointState message with all servo positions.

        Args:
            states: Dictionary mapping tendon names to ServoState
        """
        msg = JointState()
        msg.header.stamp = self._node.get_clock().now().to_msg()

        # Use standardized joint names
        joint_names = ['joint_u', 'joint_v', 'joint_w']
        tendon_order = ['u', 'v', 'w']

        msg.name = []
        msg.position = []
        msg.velocity = []
        msg.effort = []

        for tendon, joint_name in zip(tendon_order, joint_names):
            if tendon in states:
                state = states[tendon]
                msg.name.append(joint_name)
                # Position in radians (ROS convention)
                msg.position.append(state.position_rad)
                # Velocity in rad/s
                vel_rad_s = math.radians(state.speed_dps)
                msg.velocity.append(vel_rad_s)
                # Effort (using load as proxy)
                msg.effort.append(float(state.load))

        self._joint_state_pub.publish(msg)

    def publish_diagnostics(self, states: Dict[str, ServoState],
                            bus_healthy: bool) -> None:
        """Publish DiagnosticArray with per-servo status.

        Args:
            states: Dictionary mapping tendon names to ServoState
            bus_healthy: Whether bus communication is healthy
        """
        msg = DiagnosticArray()
        msg.header.stamp = self._node.get_clock().now().to_msg()

        # Overall bus health
        bus_status = DiagnosticStatus()
        bus_status.name = "spirob_bus"
        bus_status.hardware_id = "serial_bus"
        if bus_healthy:
            bus_status.level = DiagnosticStatus.OK
            bus_status.message = "Bus communication OK"
        else:
            bus_status.level = DiagnosticStatus.ERROR
            bus_status.message = "Bus communication error"
        msg.status.append(bus_status)

        # Per-servo status
        for tendon in ['u', 'v', 'w']:
            status = DiagnosticStatus()
            status.name = f"servo_{tendon}"
            status.hardware_id = f"servo_{tendon}"

            if tendon not in states:
                status.level = DiagnosticStatus.STALE
                status.message = "No data"
                msg.status.append(status)
                continue

            state = states[tendon]

            # Determine status level
            if not state.is_connected:
                status.level = DiagnosticStatus.ERROR
                status.message = "Disconnected"
            elif state.has_error:
                status.level = DiagnosticStatus.WARN
                status.message = f"Errors: {', '.join(state.get_error_names())}"
            elif state.temperature > 60:
                status.level = DiagnosticStatus.WARN
                status.message = f"High temperature: {state.temperature}C"
            else:
                status.level = DiagnosticStatus.OK
                status.message = "OK"

            # Add key-value pairs for details
            status.values = [
                KeyValue(key="position_deg", value=f"{state.position_deg:.2f}"),
                KeyValue(key="speed_dps", value=f"{state.speed_dps:.2f}"),
                KeyValue(key="voltage", value=f"{state.voltage:.2f}"),
                KeyValue(key="temperature", value=f"{state.temperature}"),
                KeyValue(key="current_ma", value=f"{state.current_ma:.1f}"),
                KeyValue(key="is_moving", value=str(state.is_moving)),
                KeyValue(key="error_flags", value=f"0x{state.error_flags:02x}"),
            ]

            msg.status.append(status)

        self._diagnostics_pub.publish(msg)

    def publish_angles(self, states: Dict[str, ServoState]) -> None:
        """Publish individual angle topics in degrees.

        Args:
            states: Dictionary mapping tendon names to ServoState
        """
        for tendon, pub in self._angle_pubs.items():
            if tendon in states:
                msg = Float32()
                msg.data = states[tendon].position_deg
                pub.publish(msg)
