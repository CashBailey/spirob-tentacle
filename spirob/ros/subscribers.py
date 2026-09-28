"""ROS2 subscribers for spirob_bus node."""

import math
from typing import Callable

from rclpy.node import Node
from std_msgs.msg import Float32, Bool

# Valid tendon names (whitelist)
VALID_TENDONS = frozenset(['u', 'v', 'w'])

# Angle bounds - reject values outside this range as clearly invalid
# Servos physically cannot exceed ~2300 degrees
MAX_VALID_ANGLE = 3000.0


class SpirobSubscribers:
    """Manages all ROS2 subscribers for the spirob node."""

    def __init__(self, node: Node,
                 on_target_angle: Callable[[str, float], None],
                 on_torque_enable: Callable[[bool], None]):
        """Initialize subscribers.

        Args:
            node: ROS2 node to create subscribers on
            on_target_angle: Callback for target angle commands (tendon, angle_deg)
            on_torque_enable: Callback for torque enable commands
        """
        self._node = node
        self._on_target_angle = on_target_angle
        self._on_torque_enable = on_torque_enable

    def setup(self) -> None:
        """Create all subscribers."""
        # Target angle subscribers for each tendon
        for tendon in ['u', 'v', 'w']:
            self._node.create_subscription(
                Float32,
                f'/servo/{tendon}/target_angle',
                self._make_target_callback(tendon),
                10
            )

        # Target speed subscribers (optional)
        for tendon in ['u', 'v', 'w']:
            self._node.create_subscription(
                Float32,
                f'/servo/{tendon}/target_speed',
                self._make_speed_callback(tendon),
                10
            )

        # Global torque enable
        self._node.create_subscription(
            Bool,
            '/servo/torque_enable',
            self._on_torque_enable_msg,
            10
        )

        # Per-tendon torque enable
        for tendon in ['u', 'v', 'w']:
            self._node.create_subscription(
                Bool,
                f'/servo/{tendon}/torque_enable',
                self._make_torque_callback(tendon),
                10
            )

        self._node.get_logger().info("Subscribers initialized")

    def _make_target_callback(self, tendon: str):
        """Create callback for target angle subscription.

        Args:
            tendon: Tendon name for this callback
        """
        def callback(msg: Float32) -> None:
            angle = msg.data

            # Validate input at boundary
            if not self._is_valid_angle(angle):
                self._node.get_logger().warning(
                    f"Invalid target angle for {tendon}: {angle} (NaN/Inf/out of range)"
                )
                return

            self._on_target_angle(tendon, angle)
        return callback

    def _is_valid_angle(self, angle: float) -> bool:
        """Validate angle value is finite and within reasonable bounds.

        Args:
            angle: Angle in degrees

        Returns:
            True if valid, False if NaN, Inf, or out of bounds
        """
        if not math.isfinite(angle):
            return False
        if abs(angle) > MAX_VALID_ANGLE:
            return False
        return True

    def _make_speed_callback(self, tendon: str):
        """Create callback for target speed subscription.

        Args:
            tendon: Tendon name for this callback
        """
        def callback(msg: Float32):
            # Store speed for next position command
            # This is handled at the node level
            self._node.get_logger().debug(
                f"Speed command for {tendon}: {msg.data} deg/s"
            )
        return callback

    def _on_torque_enable_msg(self, msg: Bool):
        """Handle global torque enable message."""
        self._on_torque_enable(msg.data)

    def _make_torque_callback(self, tendon: str):
        """Create callback for per-tendon torque enable.

        Args:
            tendon: Tendon name for this callback
        """
        def callback(msg: Bool):
            # This would need a per-tendon torque callback
            # For now, log it
            self._node.get_logger().info(
                f"Torque {'enabled' if msg.data else 'disabled'} for {tendon}"
            )
        return callback
