"""ROS2 services for spirob_bus node."""

from typing import TYPE_CHECKING

from rclpy.node import Node
from std_srvs.srv import Trigger

if TYPE_CHECKING:
    from spirob.control.servo_manager import ServoManager


class SpirobServices:
    """Manages all ROS2 services for the spirob node."""

    def __init__(self, node: Node, servo_manager: 'ServoManager'):
        """Initialize services.

        Args:
            node: ROS2 node to create services on
            servo_manager: ServoManager instance for handling requests
        """
        self._node = node
        self._manager = servo_manager

    def setup(self) -> None:
        """Create all services."""
        # Zero services for each tendon
        for tendon in ['u', 'v', 'w']:
            self._node.create_service(
                Trigger,
                f'/servo/{tendon}/zero_here',
                self._make_zero_callback(tendon)
            )

        # Save parameters service
        self._node.create_service(
            Trigger,
            '/servo/save_params',
            self._handle_save_params
        )

        # Emergency stop service
        self._node.create_service(
            Trigger,
            '/servo/emergency_stop',
            self._handle_emergency_stop
        )

        # Reset emergency stop service
        self._node.create_service(
            Trigger,
            '/servo/reset_estop',
            self._handle_reset_estop
        )

        # Scan bus service
        self._node.create_service(
            Trigger,
            '/servo/scan_bus',
            self._handle_scan_bus
        )

        self._node.get_logger().info("Services initialized")

    def _make_zero_callback(self, tendon: str):
        """Create callback for zero_here service.

        Args:
            tendon: Tendon name for this callback
        """
        def callback(request: Trigger.Request,
                     response: Trigger.Response) -> Trigger.Response:
            if self._manager.zero_tendon(tendon):
                response.success = True
                response.message = f"Zeroed tendon {tendon}"
                self._node.get_logger().info(response.message)
            else:
                response.success = False
                response.message = f"Failed to zero tendon {tendon}"
                self._node.get_logger().error(response.message)
            return response

        return callback

    def _handle_save_params(self, request: Trigger.Request,
                            response: Trigger.Response) -> Trigger.Response:
        """Handle save_params service request.

        Saves current settings to servo EEPROM.
        """
        # Note: This would need implementation in the servo adapter
        # to write to EEPROM. For now, return not implemented.
        response.success = False
        response.message = "Save to EEPROM not yet implemented"
        self._node.get_logger().warning(response.message)
        return response

    def _handle_emergency_stop(self, request: Trigger.Request,
                               response: Trigger.Response) -> Trigger.Response:
        """Handle emergency_stop service request."""
        self._manager.emergency_stop()
        response.success = True
        response.message = "Emergency stop triggered"
        self._node.get_logger().warning(response.message)
        return response

    def _handle_reset_estop(self, request: Trigger.Request,
                            response: Trigger.Response) -> Trigger.Response:
        """Handle reset_estop service request."""
        self._manager.reset_estop()
        response.success = True
        response.message = "Emergency stop reset"
        self._node.get_logger().info(response.message)
        return response

    def _handle_scan_bus(self, request: Trigger.Request,
                         response: Trigger.Response) -> Trigger.Response:
        """Handle scan_bus service request."""
        try:
            found_ids = self._manager.scan_bus()
            response.success = True
            response.message = f"Found servos at IDs: {found_ids}"
            self._node.get_logger().info(response.message)
        except Exception as e:
            response.success = False
            response.message = f"Bus scan failed: {e}"
            self._node.get_logger().error(response.message)
        return response
