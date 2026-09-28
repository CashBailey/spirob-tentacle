"""Configuration for ROS2 topic and service names.

Centralizes all ROS2 topic/service names to avoid hard-coded strings
scattered throughout the codebase.
"""

from dataclasses import dataclass


@dataclass
class TopicConfig:
    """Configuration for ROS2 topic and service names.

    All topic/service names are configurable to allow:
    - Namespace remapping
    - Testing with isolated topics
    - Multiple robot instances
    """

    # Subscriptions
    joint_states: str = '/servo/joint_states'
    diagnostics: str = '/servo/diagnostics'

    # Publishers (per-tendon templates)
    target_angle_template: str = '/servo/{tendon}/target_angle'
    torque_enable: str = '/servo/torque_enable'

    # Services (per-tendon templates)
    zero_here_template: str = '/servo/{tendon}/zero_here'

    # Global services
    emergency_stop: str = '/servo/emergency_stop'
    reset_estop: str = '/servo/reset_estop'
    scan_bus: str = '/servo/scan_bus'

    def target_angle(self, tendon: str) -> str:
        """Get target angle topic for a specific tendon.

        Args:
            tendon: Tendon identifier ('u', 'v', 'w')

        Returns:
            Full topic name
        """
        return self.target_angle_template.format(tendon=tendon)

    def zero_here(self, tendon: str) -> str:
        """Get zero_here service name for a specific tendon.

        Args:
            tendon: Tendon identifier ('u', 'v', 'w')

        Returns:
            Full service name
        """
        return self.zero_here_template.format(tendon=tendon)
