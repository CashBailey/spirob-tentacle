"""Unit conversion utilities for spirob servo control.

The servos use 4096 steps per revolution with signed 16-bit multi-turn support.
"""

import math
from spirob.protocol.constants import (
    DEGREES_PER_STEP, STEPS_PER_DEGREE, POSITION_MIN, POSITION_MAX
)


def steps_to_degrees(steps: int) -> float:
    """Convert servo steps to degrees (4096 steps/revolution, multi-turn).

    Args:
        steps: Position in steps (signed, multi-turn)

    Returns:
        Position in degrees
    """
    return steps * DEGREES_PER_STEP


def degrees_to_steps(degrees: float) -> int:
    """Convert degrees to servo steps (multi-turn, signed 16-bit).

    Args:
        degrees: Position in degrees (multi-turn, can exceed ±360)

    Returns:
        Position in steps, clamped to signed 16-bit range
    """
    steps = int(round(degrees * STEPS_PER_DEGREE))
    return max(POSITION_MIN, min(POSITION_MAX, steps))


def degrees_to_radians(degrees: float) -> float:
    """Convert degrees to radians.

    Args:
        degrees: Angle in degrees

    Returns:
        Angle in radians
    """
    return degrees * (math.pi / 180.0)


def radians_to_degrees(radians: float) -> float:
    """Convert radians to degrees.

    Args:
        radians: Angle in radians

    Returns:
        Angle in degrees
    """
    return radians * (180.0 / math.pi)


def steps_to_radians(steps: int) -> float:
    """Convert servo steps to radians.

    Args:
        steps: Position in steps

    Returns:
        Position in radians
    """
    return degrees_to_radians(steps_to_degrees(steps))


def radians_to_steps(radians: float) -> int:
    """Convert radians to servo steps.

    Args:
        radians: Position in radians

    Returns:
        Position in steps
    """
    return degrees_to_steps(radians_to_degrees(radians))


def normalize_angle(degrees: float) -> float:
    """Normalize angle to 0-360 range.

    Args:
        degrees: Angle in degrees (any value)

    Returns:
        Angle normalized to [0, 360)
    """
    degrees = degrees % 360.0
    if degrees < 0:
        degrees += 360.0
    return degrees


def voltage_raw_to_volts(raw: int) -> float:
    """Convert raw voltage reading to volts.

    The servo reports voltage in 0.1V units.

    Args:
        raw: Raw voltage value from servo

    Returns:
        Voltage in volts
    """
    return raw * 0.1


def current_raw_to_ma(raw: int) -> float:
    """Convert raw current reading to milliamps.

    The servo reports current in 6.5mA units.

    Args:
        raw: Raw current value from servo

    Returns:
        Current in milliamps
    """
    return raw * 6.5


def torque_percent_to_raw(percent: float) -> int:
    """Convert torque percentage to raw servo value.

    Args:
        percent: Torque as percentage (0-100)

    Returns:
        Raw torque value (0-1000)
    """
    return max(0, min(1000, int(percent * 10)))


def torque_raw_to_percent(raw: int) -> float:
    """Convert raw torque value to percentage.

    Args:
        raw: Raw torque value (0-1000)

    Returns:
        Torque as percentage (0-100)
    """
    return raw / 10.0


def speed_dps_to_raw(degrees_per_sec: float) -> int:
    """Convert speed in degrees/second to raw servo value.

    Args:
        degrees_per_sec: Speed in degrees per second

    Returns:
        Raw speed value (steps per second)
    """
    return max(0, min(4095, int(degrees_per_sec * STEPS_PER_DEGREE)))


def speed_raw_to_dps(raw: int) -> float:
    """Convert raw speed value to degrees/second.

    Args:
        raw: Raw speed value (steps per second)

    Returns:
        Speed in degrees per second
    """
    return raw * DEGREES_PER_STEP
