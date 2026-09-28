"""Launch file for SpiRob driver with GUI."""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, TimerAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Generate launch description for SpiRob with GUI."""

    # Declare arguments
    port_arg = DeclareLaunchArgument(
        'port',
        default_value='auto',
        description="Serial port ('auto' for discovery, or specific like '/dev/ttyUSB0')"
    )

    config_arg = DeclareLaunchArgument(
        'config',
        default_value='',
        description='Path to config YAML file (optional)'
    )

    gui_delay_arg = DeclareLaunchArgument(
        'gui_delay',
        default_value='2.0',
        description='Delay before starting GUI (seconds)'
    )

    # Launch the driver node
    driver_node = Node(
        package='spirob',
        executable='spirob_bus',
        name='spirob_driver',
        parameters=[{
            'port': LaunchConfiguration('port'),
        }],
        output='screen'
    )

    # Launch the GUI after a short delay (to let driver initialize)
    gui_process = TimerAction(
        period=LaunchConfiguration('gui_delay'),
        actions=[
            ExecuteProcess(
                cmd=['ros2', 'run', 'spirob', 'spirob_gui'],
                output='screen'
            )
        ]
    )

    return LaunchDescription([
        port_arg,
        config_arg,
        gui_delay_arg,
        driver_node,
        gui_process,
    ])
