"""Entry point for spirob_bus ROS2 node."""

import rclpy
from rclpy.executors import MultiThreadedExecutor

from spirob.ros.spirob_bus_node import SpirobBusNode


def main(args=None):
    """Main entry point for the spirob_bus node.

    Uses MultiThreadedExecutor for concurrent callback handling.
    """
    rclpy.init(args=args)

    node = SpirobBusNode()

    # Use MultiThreadedExecutor for concurrent service handling
    # This allows services to be called while telemetry is running
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    try:
        executor.spin()
    except KeyboardInterrupt:
        node.get_logger().info("Keyboard interrupt, shutting down...")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
