"""ROS2 parameter handling for spirob_bus node."""

from dataclasses import dataclass, field
from typing import Dict
import logging

from rclpy.node import Node

from spirob.control.safety import SoftLimits
from spirob.control.spool_geometry import SpoolConfig
from spirob.control.load_compensation import CompensationParams

logger = logging.getLogger(__name__)


@dataclass
class SpirobParameters:
    """All parameters for the spirob_bus node."""

    # Connection parameters
    port: str = 'auto'
    baud: int = 1000000

    # ID mapping
    id_map: Dict[str, int] = field(default_factory=lambda: {'u': 1, 'v': 2, 'w': 3})

    # Telemetry
    telemetry_rate_hz: float = 50.0

    # Soft limits (per tendon)
    soft_limits: Dict[str, SoftLimits] = field(default_factory=dict)

    # Global limits
    speed_limit_dps: float = 360.0
    torque_limit_percent: float = 80.0

    # Spool geometry
    spool_config: SpoolConfig = field(default_factory=SpoolConfig)

    # Safety
    heartbeat_timeout_ms: int = 2000

    # Load compensation
    compensation_params: CompensationParams = field(default_factory=CompensationParams)


def declare_parameters(node: Node) -> None:
    """Declare all ROS2 parameters on the node.

    Args:
        node: ROS2 node to declare parameters on
    """
    # Connection
    node.declare_parameter('port', 'auto')
    node.declare_parameter('baud', 1000000)

    # ID mapping
    node.declare_parameter('id_map.u', 1)
    node.declare_parameter('id_map.v', 2)
    node.declare_parameter('id_map.w', 3)

    # Telemetry
    node.declare_parameter('telemetry_rate_hz', 50.0)

    # Soft limits for each tendon
    for tendon in ['u', 'v', 'w']:
        node.declare_parameter(f'soft_limits.{tendon}.min_deg', -2292.0)
        node.declare_parameter(f'soft_limits.{tendon}.max_deg', 2292.0)

    # Global limits
    node.declare_parameter('speed_limit_dps', 360.0)
    node.declare_parameter('torque_limit_percent', 80.0)

    # Spool geometry
    node.declare_parameter('spool.core_radius_mm', 10.0)
    node.declare_parameter('spool.tendon_diameter_mm', 1.0)
    node.declare_parameter('spool.wrap_width_mm', 15.0)
    node.declare_parameter('spool.usable_layers', 5)

    # Safety
    node.declare_parameter('heartbeat_timeout_ms', 2000)

    # Load compensation
    node.declare_parameter('compensation.base_speed_dps', 180.0)
    node.declare_parameter('compensation.base_torque_percent', 50.0)
    node.declare_parameter('compensation.stuck_threshold_deg', 1.0)
    node.declare_parameter('compensation.stuck_timeout_sec', 0.5)
    node.declare_parameter('compensation.adaptation_step_percent', 10.0)
    node.declare_parameter('compensation.max_torque_percent', 90.0)
    node.declare_parameter('compensation.max_speed_dps', 360.0)


def load_parameters(node: Node) -> SpirobParameters:
    """Load parameters from ROS2 node into dataclass.

    Args:
        node: ROS2 node with declared parameters

    Returns:
        SpirobParameters with values from node
    """
    params = SpirobParameters()

    # Connection
    params.port = node.get_parameter('port').get_parameter_value().string_value
    params.baud = node.get_parameter('baud').get_parameter_value().integer_value

    # ID mapping
    params.id_map = {
        'u': node.get_parameter('id_map.u').get_parameter_value().integer_value,
        'v': node.get_parameter('id_map.v').get_parameter_value().integer_value,
        'w': node.get_parameter('id_map.w').get_parameter_value().integer_value,
    }

    # Telemetry
    params.telemetry_rate_hz = node.get_parameter(
        'telemetry_rate_hz').get_parameter_value().double_value

    # Soft limits
    for tendon in ['u', 'v', 'w']:
        min_deg = node.get_parameter(
            f'soft_limits.{tendon}.min_deg').get_parameter_value().double_value
        max_deg = node.get_parameter(
            f'soft_limits.{tendon}.max_deg').get_parameter_value().double_value

        params.soft_limits[tendon] = SoftLimits(
            min_angle_deg=min_deg,
            max_angle_deg=max_deg,
            max_speed_dps=params.speed_limit_dps,
            max_torque_percent=params.torque_limit_percent,
        )

    # Global limits
    params.speed_limit_dps = node.get_parameter(
        'speed_limit_dps').get_parameter_value().double_value
    params.torque_limit_percent = node.get_parameter(
        'torque_limit_percent').get_parameter_value().double_value

    # Spool geometry
    params.spool_config = SpoolConfig(
        core_radius_mm=node.get_parameter(
            'spool.core_radius_mm').get_parameter_value().double_value,
        tendon_diameter_mm=node.get_parameter(
            'spool.tendon_diameter_mm').get_parameter_value().double_value,
        wrap_width_mm=node.get_parameter(
            'spool.wrap_width_mm').get_parameter_value().double_value,
        usable_layers=node.get_parameter(
            'spool.usable_layers').get_parameter_value().integer_value,
    )

    # Safety
    params.heartbeat_timeout_ms = node.get_parameter(
        'heartbeat_timeout_ms').get_parameter_value().integer_value

    # Load compensation
    params.compensation_params = CompensationParams(
        base_speed_dps=node.get_parameter(
            'compensation.base_speed_dps').get_parameter_value().double_value,
        base_torque_percent=node.get_parameter(
            'compensation.base_torque_percent').get_parameter_value().double_value,
        stuck_threshold_deg=node.get_parameter(
            'compensation.stuck_threshold_deg').get_parameter_value().double_value,
        stuck_timeout_sec=node.get_parameter(
            'compensation.stuck_timeout_sec').get_parameter_value().double_value,
        adaptation_step_percent=node.get_parameter(
            'compensation.adaptation_step_percent').get_parameter_value().double_value,
        max_torque_percent=node.get_parameter(
            'compensation.max_torque_percent').get_parameter_value().double_value,
        max_speed_dps=node.get_parameter(
            'compensation.max_speed_dps').get_parameter_value().double_value,
    )

    logger.info(f"Loaded parameters: port={params.port}, baud={params.baud}")
    logger.info(f"ID map: {params.id_map}")
    logger.info(f"Telemetry rate: {params.telemetry_rate_hz} Hz")

    return params
