"""Launch file for spirob_bus node."""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    """Generate launch description for spirob_bus node."""
    # Get package directory
    pkg_dir = get_package_share_directory('spirob')
    default_config = os.path.join(pkg_dir, 'config', 'spirob_default.yaml')

    # Declare arguments
    config_arg = DeclareLaunchArgument(
        'config_file',
        default_value=default_config,
        description='Path to configuration YAML file'
    )

    port_arg = DeclareLaunchArgument(
        'port',
        default_value='auto',
        description="Serial port ('auto' for discovery, or specific like '/dev/ttyUSB0')"
    )

    # Create node
    spirob_node = Node(
        package='spirob',
        executable='spirob_bus',
        name='spirob_bus',
        output='screen',
        parameters=[
            LaunchConfiguration('config_file'),
            {'port': LaunchConfiguration('port')}
        ],
        remappings=[
            # Add any topic remappings here if needed
        ],
    )

    return LaunchDescription([
        config_arg,
        port_arg,
        spirob_node,
    ])
